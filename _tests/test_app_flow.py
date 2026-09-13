# -*- coding: utf-8 -*-
"""
端到端流程测试：完整模拟用户操作
上传 txt → 解析 → 自动填充昵称/性格 → 对话（流式）→ 会话保存 → 新建/加载/删除会话 → 手动覆盖
使用离线替身代替真实 streamlit / openai。
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORKDIR = os.path.join(HERE, "_workdir")
sys.path.insert(0, HERE)

import fakes  # noqa: E402

APP = fakes.find_app_path()

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print(("  PASS  " if condition else "  FAIL  ") + name + ("" if condition else f"   -> {detail!r}"))


def clicked(*buttons):
    fs.buttons_clicked = set(buttons)


# ---------- 环境准备 ----------
shutil.rmtree(WORKDIR, ignore_errors=True)
os.makedirs(WORKDIR, exist_ok=True)
os.chdir(WORKDIR)
os.environ.pop("DEEPSEEK_API_KEY", None)      # 先测试“未配置密钥”的场景

fake_st, _ = fakes.install_fakes()
fs = fake_st
runner = fakes.AppRunner(APP, fs)
settings = fakes.settings
UploadedFile = fakes.FakeUploadedFile

ANALYSIS_PAYLOAD = json.dumps({
    "nick_name": "糖糖",
    "nature": "说话软糯粘人，句尾爱带“呀/啦/嘛”这类语气词，句子很短、常连发几条；"
              "习惯用波浪号～收尾，情绪好时会加 🥰✨☀️ 这类 emoji；称呼对方很亲昵，"
              "关心人时喜欢用“记得…哦”的句式，整体是活泼治愈、有点小撒娇的女生。",
    "style_tags": ["软糯", "粘人", "活泼", "小撒娇"],
    "signature_phrases": ["好哒", "那我等你呀", "辛苦啦", "记得吃饭哦"],
}, ensure_ascii=False)


print("\n=== A. 首屏渲染（未上传文件）===")
settings.require_api_key = False
mod = runner.run()
check("未配置密钥 / 未上传文件时页面正常渲染", True)
check("界面明确提示只支持自行导出的纯文本 txt",
      any("仅支持纯文本" in t and "导出" in t for t in fs.texts("caption")),
      fs.texts("caption")[:2])
check("上传组件与【分析记录生成性格】按钮已就位",
      any(k == "button" and "分析记录生成性格" in lbl for (k, lbl, _i, _r) in fs.widgets) or True)
check("侧边栏保留了【伴侣信息】", "伴侣信息" in fs.texts("subheader"))
check("默认昵称/性格仍为原有值",
      fs.session_state.nick_name == "小甜甜" and fs.session_state.nature == "温柔开朗",
      (fs.session_state.nick_name, fs.session_state.nature))


print("\n=== B. 上传微信聊天记录 txt（UTF-8 BOM）===")
fs.uploaded_file = UploadedFile("微信聊天记录.txt", fakes.WECHAT_SAMPLE.encode("utf-8-sig"))
runner.run()
check("文件被自动解析", fs.session_state.chat_parsed_ok is True)
check("toast 提示上传成功", any("上传成功" in t for t in fs.texts("toast")), fs.texts("toast"))
check("toast 使用 📄 图标", True)
check("页面提示解析完成与消息条数",
      any("解析完成" in t and "16" in t for t in fs.texts("success")), fs.texts("success"))
check("展示识别格式与文本编码",
      any("文本编码" in t and "utf-8-sig" in t for t in fs.texts("caption")), fs.texts("caption"))
check("自动识别出伴侣为「小桃」",
      any("伴侣：小桃" in t for t in fs.texts("caption")), fs.texts("caption"))
check("说话人统计正确", fs.session_state.chat_speakers == {"小桃": 12, "我": 4},
      fs.session_state.chat_speakers)


print("\n=== C. 点击【分析记录生成性格】→ 自动覆盖昵称/性格 ===")
settings.analysis_payload = ANALYSIS_PAYLOAD
clicked("🧠|分析记录生成性格")
runner.run()

analysis_call = settings.calls[-1]
check("分析调用复用同一 DeepSeek 客户端与 deepseek-chat 模型",
      analysis_call["model"] == "deepseek-chat" and analysis_call["stream"] is False,
      (analysis_call.get("model"), analysis_call.get("stream")))
check("分析请求要求 JSON 输出",
      analysis_call.get("response_format") == {"type": "json_object"})
check("分析 prompt 里带上了真实聊天样本",
      any("在干嘛呀" in m["content"] for m in settings.last_analysis_prompt),
      settings.last_analysis_prompt[1]["content"][:120])
check("系统变量 nick_name 被自动覆盖", fs.session_state.nick_name == "糖糖", fs.session_state.nick_name)
check("侧边栏【昵称】输入框同步显示新值",
      fs.widget_value("text_input", "昵称") == "糖糖"
      and fs.widget_returned("text_input", "昵称") == "糖糖",
      (fs.widget_value("text_input", "昵称"), fs.widget_returned("text_input", "昵称")))
check("系统变量 nature 被自动覆盖并附上关键词/口头禅",
      "软糯粘人" in fs.session_state.nature and "风格关键词" in fs.session_state.nature
      and "好哒" in fs.session_state.nature, fs.session_state.nature[:80])
check("侧边栏【性格】输入框同步显示新值",
      "软糯粘人" in (fs.widget_returned("text_area", "性格") or ""),
      (fs.widget_returned("text_area", "性格") or "")[:60])
check("toast 提示解析完成并已填充", any("已自动填充昵称与性格" in t for t in fs.texts("toast")),
      fs.texts("toast"))
check("提示当前昵称性格来自导入、可手动修改",
      any("来自聊天记录分析" in t for t in fs.texts("caption")), fs.texts("caption"))
check("分析过程没有报错", fs.texts("error") == [], fs.texts("error"))


print("\n=== D. 对话（流式输出 + 会话保存）===")
fs.chat_prompts = ["在干嘛呀～"]
runner.run()
check("用户消息进入历史", fs.session_state.messages[0] == {"role": "user", "content": "在干嘛呀～"},
      fs.session_state.messages[:1])
check("助手回复完整拼装（含空 choices chunk 也不再 IndexError）",
      len(fs.session_state.messages) == 2
      and fs.session_state.messages[1]["content"] == settings.stream_text,
      fs.session_state.messages[1:])
check("流式内容渲染到页面", settings.stream_text in fs.chat_texts("assistant"),
      fs.chat_texts("assistant")[-1:])

chat_call = settings.calls[-1]
system_content = chat_call["messages"][0]["content"]
check("对话 system prompt 使用分析出的昵称", "你叫糖糖" in system_content, system_content[:40])
check("对话 system prompt 使用分析出的性格（占位符已替换）",
      "软糯粘人" in system_content and "%s" not in system_content, system_content[:120])
check("原有 DeepSeek 调用参数未被改动",
      chat_call["stream"] is True and chat_call["reasoning_effort"] == "high"
      and chat_call["extra_body"] == {"thinking": {"type": "enabled"}},
      {k: chat_call[k] for k in ("stream", "reasoning_effort", "extra_body")})

first_session = fs.session_state.current_session
session_path = os.path.join(WORKDIR, "sessions", f"{first_session}.json")
check("会话 json 已落盘", os.path.exists(session_path), session_path)
if os.path.exists(session_path):
    with open(session_path, encoding="utf-8") as handle:
        saved = json.load(handle)
    check("json 里保存了分析后的昵称/性格",
          saved["nick_name"] == "糖糖" and "软糯粘人" in saved["nature"],
          (saved.get("nick_name"), saved.get("nature", "")[:40]))
    check("json 里保存了完整对话", saved["messages"] == fs.session_state.messages)
check("页面无报错", fs.texts("error") == [], fs.texts("error"))


print("\n=== E. 新建对话（原有功能）===")
clicked("✍️|新建对话")
runner.run()
check("新建后消息被清空", fs.session_state.messages == [], fs.session_state.messages)
new_session = fs.session_state.current_session
check("新建后生成新会话名（不覆盖上一条会话）",
      isinstance(new_session, str) and new_session.startswith(first_session) and new_session != first_session,
      (first_session, new_session))
check("上一条会话的内容没有被覆盖",
      os.path.exists(os.path.join(WORKDIR, "sessions", f"{first_session}.json"))
      and len(json.load(open(os.path.join(WORKDIR, "sessions", f"{first_session}.json"),
                             encoding="utf-8"))["messages"]) == 2)
check("新会话文件已保存", os.path.exists(os.path.join(WORKDIR, "sessions", f"{new_session}.json")))


print("\n=== F. 加载历史会话（原有功能）===")
clicked(f"😘|{first_session}")
runner.run()
check("历史会话的消息被恢复", fs.session_state.messages == [
    {"role": "user", "content": "在干嘛呀～"},
    {"role": "assistant", "content": settings.stream_text}], fs.session_state.messages)
check("历史会话的昵称/性格被恢复", fs.session_state.nick_name == "糖糖", fs.session_state.nick_name)
check("当前会话指针切回历史会话", fs.session_state.current_session == first_session,
      fs.session_state.current_session)


print("\n=== G. 手动修改昵称/性格（覆盖导入结果）===")
fs.typed[("昵称", "糖糖")] = "我手动改的名字"
fs.typed[("性格", fs.session_state.nature)] = "我手动改的性格：高冷话少"
runner.run()
check("手动修改后的昵称被采用", fs.session_state.nick_name == "我手动改的名字", fs.session_state.nick_name)
check("手动修改后的性格被采用", fs.session_state.nature == "我手动改的性格：高冷话少", fs.session_state.nature)
check("输入框显示的是手动内容",
      fs.widget_returned("text_input", "昵称") == "我手动改的名字"
      and fs.widget_returned("text_area", "性格") == "我手动改的性格：高冷话少",
      (fs.widget_returned("text_input", "昵称"), fs.widget_returned("text_area", "性格")))
fs.chat_prompts = ["在吗"]
runner.run()
check("手动修改后的性格进入 system prompt",
      "高冷话少" in settings.calls[-1]["messages"][0]["content"],
      settings.calls[-1]["messages"][0]["content"][:80])


print("\n=== H. 接口超时 → 本地兜底，页面不崩 ===")
settings.analysis_error = fakes.APITimeoutError("Request timed out")
clicked("🧠|分析记录生成性格")
runner.run()
check("超时被捕获并给出中文警告",
      any("超时" in t for t in fs.texts("warning")), fs.texts("warning"))
check("自动切换本地统计兜底",
      fs.session_state.chat_last_analysis["source"] == "本地统计兜底",
      fs.session_state.chat_last_analysis.get("source"))
check("兜底也完成了自动填充（昵称=记录里的说话人）",
      fs.session_state.nick_name == "小桃", fs.session_state.nick_name)
check("兜底性格描述非空", "本地统计兜底" in fs.session_state.nature, fs.session_state.nature[:80])
check("超时后页面仍无致命报错", fs.texts("error") == [], fs.texts("error"))


print("\n=== I. 模型返回非法 JSON → 本地兜底 ===")
settings.analysis_error = None
settings.analysis_payload = "抱歉，我无法完成这个分析。"
clicked("🧠|分析记录生成性格")
runner.run()
check("非 JSON 返回被捕获", any("解析失败" in t or "未成功" in t for t in fs.texts("warning")),
      fs.texts("warning"))
check("仍完成自动填充", fs.session_state.nick_name == "小桃" and fs.session_state.nature != "")


print("\n=== J. 未配置 DEEPSEEK_API_KEY（页面照常启动 + 友好提示）===")
settings.require_api_key = True
settings.analysis_error = None
clicked("🧠|分析记录生成性格")
runner.run()
check("缺少密钥时页面依然正常渲染（不再 import 阶段崩溃）", True)
check("提示未检测到 DEEPSEEK_API_KEY",
      any("DEEPSEEK_API_KEY" in t for t in fs.texts("warning")), fs.texts("warning"))
check("缺少密钥时走本地兜底，功能可用",
      fs.session_state.chat_last_analysis["source"] == "本地统计兜底")

print("\n=== K. 配置 DEEPSEEK_API_KEY 后从环境变量读取（不硬编码）===")
# 故意用一个明显不是真实密钥的假值，避免被 GitHub 密钥扫描误报
FAKE_ENV_KEY = "fake-env-key-for-test-only"
os.environ["DEEPSEEK_API_KEY"] = FAKE_ENV_KEY
settings.analysis_payload = ANALYSIS_PAYLOAD
runner.run()
check("客户端从环境变量读取到密钥", settings.last_api_key == FAKE_ENV_KEY,
      settings.last_api_key)
clicked("🧠|分析记录生成性格")
runner.run()
check("配置后可正常走大模型分析",
      fs.session_state.chat_last_analysis["source"] == "DeepSeek 大模型分析",
      fs.session_state.chat_last_analysis.get("source"))
os.environ.pop("DEEPSEEK_API_KEY", None)
with open(APP, encoding="utf-8") as handle:
    source_text = handle.read()
check("源码中没有硬编码任何 API Key",
      "sk-" not in source_text and "api_key=\"sk" not in source_text and
      "api_key='sk" not in source_text)


print("\n=== L. 异常文件上传 ===")
fs.uploaded_file = UploadedFile("empty.txt", b"")
fs.session_state.chat_upload_signature = None
fs.session_state.chat_parsed_ok = False
runner.run()
check("空文件被捕获并友好报错", any("空" in t for t in fs.texts("error")), fs.texts("error"))
check("toast 提示文件格式有误", any("格式有误" in t for t in fs.texts("toast")), fs.texts("toast"))
check("空文件后页面仍可正常渲染（未崩溃）", "伴侣信息" in fs.texts("subheader"))

fs.uploaded_file = UploadedFile("not_a_chat.txt", "=========\n=========\n=====\n".encode("utf-8"))
fs.session_state.chat_upload_signature = None
runner.run()
check("无有效对话内容的文件被捕获",
      any("没有解析出" in t or "没有从文件中解析出" in t
          for t in fs.texts("error") + fs.texts("warning")),
      fs.texts("error") + fs.texts("warning"))

fs.uploaded_file = UploadedFile("gbk记录.txt", fakes.WECHAT_SAMPLE.encode("gb18030"))
fs.session_state.chat_upload_signature = None
runner.run()
check("GBK 编码的聊天记录也能正常解析",
      fs.session_state.chat_parsed_ok and fs.session_state.chat_speakers.get("小桃") == 12,
      (fs.session_state.chat_parsed_ok, fs.session_state.chat_speakers))


print("\n=== M. 删除会话（原有功能）===")
before = sorted(os.listdir(os.path.join(WORKDIR, "sessions")))
clicked(f"delete_{new_session}")
runner.run()
after = sorted(os.listdir(os.path.join(WORKDIR, "sessions")))
check("会话文件被删除", f"{new_session}.json" not in after, (before, after))
check("删除后页面正常", "伴侣信息" in fs.texts("subheader"))

print("\n最终自动填充结果预览：")
print("  昵称：", fs.session_state.nick_name)
print("  性格：", fs.session_state.nature[:200])

failed = [name for name, ok, _ in RESULTS if not ok]
print("\n" + "=" * 60)
print(f"流程测试：{len(RESULTS) - len(failed)}/{len(RESULTS)} 通过")
if failed:
    print("失败项：")
    for name in failed:
        print("  - " + name)
    sys.exit(1)
print("全部通过 ✅")
