# -*- coding: utf-8 -*-
"""
离线测试替身：本机没有网络、也装不上真实 streamlit / openai，
所以这里用行为等价的替身模块来跑通 app 的完整流程。

替身尽量还原真实 Streamlit 的关键语义：
1. session_state 跨 rerun 保持，且支持属性式读写、in、get、setdefault
2. 未加 key 的 text_input / text_area，其“控件标识”由 (label, value) 决定，
   所以当 value 变化时会当成新控件、直接显示新默认值 —— 这正是
   “导入分析后自动覆盖昵称/性格输入框”能生效的机制
3. 按钮只在被点击的那一次 rerun 返回 True
4. st.rerun() 抛出异常，由 AppRunner 捕获并重新执行脚本
"""
import os
import sys
import types


class RerunRequested(Exception):
    """模拟 st.rerun()"""


class SessionState(dict):
    """支持 st.session_state.foo 与 st.session_state["foo"] 两种写法"""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        try:
            del self[name]
        except KeyError:
            raise AttributeError(name)


class FakeUploadedFile:
    """模拟 streamlit 的 UploadedFile"""

    def __init__(self, name, data):
        self.name = name
        self._data = data
        self.size = len(data)
        self.type = "text/plain"

    def getvalue(self):
        return self._data


class _Ctx:
    """通用上下文管理器（sidebar / columns / expander / spinner / empty / chat_message）"""

    def __init__(self, fs, kind):
        self.fs = fs
        self.kind = kind

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, *args, **kwargs):
        self.fs.events.append((f"write:{self.kind}", str(args[0]) if args else ""))

    def markdown(self, *args, **kwargs):
        self.write(*args)

    def chat_message(self, role):
        return _Ctx(self.fs, f"chat:{role}")


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = SessionState()
        self.sidebar = _Ctx(self, "sidebar")
        self.events = []            # 所有文案类调用的记录
        self.widgets = []           # 控件调用记录：(类型, label, 传入的value, 返回值)
        self.uploaded_file = None
        self.chat_prompts = []      # 待消费的用户输入队列
        self.typed = {}             # 模拟用户手动输入：{(label, value): 用户输入}
        self.selectbox_choice = {}  # 模拟用户切换下拉框：{label: 选择值}
        self.buttons_clicked = set()

    # ---------- 文案与布局 ----------
    def set_page_config(self, **kwargs):
        self.events.append(("set_page_config", ""))

    def title(self, text, **kwargs):
        self.events.append(("title", str(text)))

    def text(self, text, **kwargs):
        self.events.append(("text", str(text)))

    def subheader(self, text, **kwargs):
        self.events.append(("subheader", str(text)))

    def caption(self, text, **kwargs):
        self.events.append(("caption", str(text)))

    def divider(self):
        self.events.append(("divider", ""))

    def write(self, *args, **kwargs):
        self.events.append(("write", str(args[0]) if args else ""))

    def success(self, text, **kwargs):
        self.events.append(("success", str(text)))

    def warning(self, text, **kwargs):
        self.events.append(("warning", str(text)))

    def error(self, text, **kwargs):
        self.events.append(("error", str(text)))

    def info(self, text, **kwargs):
        self.events.append(("info", str(text)))

    def toast(self, text, icon=None, **kwargs):
        self.events.append(("toast", str(text)))

    def chat_message(self, role):
        return _Ctx(self, f"chat:{role}")

    def empty(self):
        return _Ctx(self, "empty")

    def spinner(self, *args, **kwargs):
        return _Ctx(self, "spinner")

    def expander(self, label, expanded=False, **kwargs):
        return _Ctx(self, "expander")

    def columns(self, spec, **kwargs):
        count = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
        return [_Ctx(self, f"column{i}") for i in range(count)]

    # ---------- 控件 ----------
    def button(self, label, key=None, width=None, icon=None, type=None, help=None, **kwargs):
        ident = key if key else f"{icon}|{label}"
        clicked = ident in self.buttons_clicked
        self.widgets.append(("button", str(label), ident, clicked))
        return clicked

    def text_input(self, label, value="", placeholder=None, key=None, help=None, **kwargs):
        ident = (label, value)
        returned = self.typed.get(ident, value)
        self.widgets.append(("text_input", label, value, returned))
        return returned

    def text_area(self, label, value="", placeholder=None, key=None, help=None, **kwargs):
        ident = (label, value)
        returned = self.typed.get(ident, value)
        self.widgets.append(("text_area", label, value, returned))
        return returned

    def selectbox(self, label, options, index=0, key=None, help=None, **kwargs):
        opts = list(options)
        if label in self.selectbox_choice and self.selectbox_choice[label] in opts:
            return self.selectbox_choice[label]
        return opts[index] if opts else None

    def file_uploader(self, label, type=None, key=None, help=None, **kwargs):
        return self.uploaded_file

    def chat_input(self, placeholder=None, **kwargs):
        return self.chat_prompts.pop(0) if self.chat_prompts else None

    def rerun(self):
        raise RerunRequested()

    # ---------- 断言辅助 ----------
    def texts(self, kind):
        return [t for k, t in self.events if k == kind]

    def chat_texts(self, role):
        return [t for k, t in self.events if k == f"write:chat:{role}"]

    def widget_value(self, kind, label):
        """返回某控件最后一次收到的“传入默认值”（= 控件当前应显示的内容）"""
        values = [v for (k, lbl, v, _r) in self.widgets if k == kind and lbl == label]
        return values[-1] if values else None

    def widget_returned(self, kind, label):
        """返回某控件最后一次“实际返回给应用的值”（= 用户看到/输入的最终内容）"""
        values = [r for (k, lbl, _v, r) in self.widgets if k == kind and lbl == label]
        return values[-1] if values else None

    def begin_run(self):
        self.events = []
        self.widgets = []


class APITimeoutError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class _Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeOpenAISettings:
    def __init__(self):
        self.require_api_key = True     # 模拟真实客户端：没有 key 时构造即失败
        self.analysis_error = None      # 非 None 时分析调用直接抛这个异常
        self.analysis_payload = None    # 分析调用返回的内容
        self.stream_text = "在的呀～我在呢 🥰"
        self.include_empty_chunk = True  # 模拟深度思考返回 choices 为空的 chunk
        self.last_api_key = None
        self.last_analysis_prompt = None
        self.calls = []

    def reset(self):
        self.__init__()


settings = FakeOpenAISettings()


class _Completions:
    def create(self, **kwargs):
        settings.calls.append(kwargs)
        if kwargs.get("stream"):
            text = settings.stream_text

            def generator():
                if settings.include_empty_chunk:
                    yield _Obj(choices=[])          # 真实场景里会出现这种 chunk
                for char in text:
                    yield _Obj(choices=[_Obj(delta=_Obj(content=char))])

            return generator()

        # 非流式调用 = 聊天记录风格分析
        if settings.analysis_error is not None:
            raise settings.analysis_error
        settings.last_analysis_prompt = kwargs.get("messages")
        return _Obj(choices=[_Obj(message=_Obj(content=settings.analysis_payload))])


class _Chat:
    def __init__(self):
        self.completions = _Completions()


class FakeOpenAI:
    def __init__(self, api_key=None, base_url=None, **kwargs):
        settings.last_api_key = api_key
        if settings.require_api_key and not api_key:
            raise RuntimeError("The api_key client option must be set")
        self.chat = _Chat()


class AppRunner:
    """反复执行 app 源码，模拟 streamlit 的 rerun 行为"""

    def __init__(self, app_path, fake_st):
        self.app_path = app_path
        self.fs = fake_st
        with open(app_path, encoding="utf-8") as handle:
            self.source = handle.read()
        self.module = types.ModuleType("app_under_test")

    def run(self, max_reruns=8):
        for attempt in range(max_reruns):
            if attempt > 0:
                self.fs.buttons_clicked = set()   # rerun 之后按钮点击状态消失
            self.fs.begin_run()
            try:
                # 注意：每次 rerun 都重新执行整个脚本，函数会被重新定义，这与 Streamlit 一致
                exec(compile(self.source, self.app_path, "exec"), self.module.__dict__)
                return self.module
            except RerunRequested:
                continue
        raise AssertionError("rerun 次数超过上限，可能存在死循环")


def find_app_path():
    """定位项目主程序（项目文件改名过，这里自动适配，避免测试写死文件名）"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    preferred = os.path.join(root, "ai_communication.py")
    if os.path.exists(preferred):
        return preferred
    for name in sorted(os.listdir(root)):
        if name.endswith(".py"):
            return os.path.join(root, name)
    raise FileNotFoundError("在项目根目录找不到主程序 .py 文件")


def install_fakes():
    """把替身注册进 sys.modules，让 app 里的 import 拿到替身"""
    fake_st = FakeStreamlit()
    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = FakeOpenAI
    fake_openai.APITimeoutError = APITimeoutError
    fake_openai.APIConnectionError = APIConnectionError
    sys.modules["streamlit"] = fake_st
    sys.modules["openai"] = fake_openai
    return fake_st, fake_openai


# ---------------- 测试用聊天记录样本 ----------------

WECHAT_SAMPLE = """2024-03-01 21:03:12 小桃
在干嘛呀～
2024-03-01 21:03:40 我
刚下班，在路上
2024-03-01 21:04:02 小桃
辛苦啦！记得吃饭哦 🥰
2024-03-01 21:04:30 小桃
[图片]
2024-03-01 21:05:00 小桃
好哒，那我等你呀
2024-03-01 21:20:11 我
好，马上到家
2024-03-01 21:21:03 小桃
嘿嘿，那我先看剧啦
2024-03-01 21:22:45 小桃
你到了跟我说一声嘛
2024-03-01 21:40:02 我
到家了
2024-03-01 21:40:30 小桃
好耶！快去洗澡呀 ✨
2024-03-01 21:41:00 小桃
洗完早点休息哦
2024-03-01 21:41:20 小桃
[表情]
2024-03-02 09:10:00 小桃
早呀 ☀️
2024-03-02 09:11:00 我
早
2024-03-02 09:12:00 小桃
今天也要加油鸭！
2024-03-02 09:13:00 小桃
晚上一起吃饭吗～
"""

QQ_SAMPLE = """=========================================
消息记录（此消息记录为文本格式，不支持重新导入）
=========================================
消息对象:阿哲
=========================================
2024-03-02 10:00:01 阿哲(10001)
早啊兄弟
2024-03-02 10:01:00 我(10002)
早
2024-03-02 10:02:00 阿哲(10001)
今天上班不
2024-03-02 10:03:00 我(10002)
上啊
2024-03-02 10:04:00 阿哲(10001)
行吧 那晚上开黑
"""

COLON_SAMPLE = """小桃: 在干嘛呀～
我: 刚下班
小桃: 辛苦啦！
我: 还好
小桃: 记得吃饭哦
"""

PLAIN_SAMPLE = """今天天气不错
记得带伞
哈哈哈
晚上吃什么
"""
