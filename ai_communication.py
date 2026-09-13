import streamlit as st
import os
import re
import json
import datetime
from collections import Counter
from openai import OpenAI

# ============================================================
# 【修复】原写法在缺少 DEEPSEEK_API_KEY 时会在 import 阶段直接抛异常，
# 导致整个页面打不开。这里包一层 try：缺密钥时页面照常启动，
# 只有真正要调用模型时才给出友好提示。
# API Key 依然只从环境变量 DEEPSEEK_API_KEY 读取，绝不硬编码，由使用者自行管理。
# ============================================================
try:
    client = OpenAI(
        api_key=os.environ.get('DEEPSEEK_API_KEY'),
        base_url="https://api.deepseek.com")
    CLIENT_INIT_ERROR = ""
except Exception as _client_error:
    client = None
    CLIENT_INIT_ERROR = str(_client_error)
st.set_page_config(
    page_title="AI智能伴侣",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={}
)

#保存会话函数
def save_session():
    if st.session_state.current_session:
        session_data = {
            "nick_name": st.session_state.nick_name,
            "nature": st.session_state.nature,
            "current_session": st.session_state.current_session,
            "messages": st.session_state.messages
        }
        if not os.path.exists("sessions"):
            os.makedirs("sessions", exist_ok=True)   # 修复：并发/已存在时 os.mkdir 会抛异常

        with open(f"sessions/{st.session_state.current_session}.json", "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)


#生成会话标志
def generate_session_name():
    """生成会话标志。
    【修复】同一秒内连续新建会话时，原来会生成同名会话并覆盖掉上一条记录，
    这里检测到重名就自动加 _2、_3 后缀，避免聊天记录被覆盖。"""
    name = datetime.datetime.now().strftime("%Y-%m-%d %H_%M_%S")
    if not os.path.exists(f"sessions/{name}.json"):
        return name
    suffix = 2
    while os.path.exists(f"sessions/{name}_{suffix}.json"):
        suffix += 1
    return f"{name}_{suffix}"
#加载会话列表
def load_sessions():
    session_list = []
    if os.path.exists("sessions"):
        file_list = os.listdir("sessions")
        for filename in file_list:
            if filename.endswith(".json"):
                session_list.append(filename[:-5])
    session_list.sort(reverse=True)
    return session_list
def load_session(session_name):
    try:
        if os.path.exists(f"sessions/{session_name}.json"):
            with open(f"sessions/{session_name}.json", "r", encoding="utf-8") as f:
                session_data = json.load(f)
                st.session_state.nick_name = session_data["nick_name"]
                st.session_state.nature = session_data["nature"]
                st.session_state.current_session = session_name
                st.session_state.messages = session_data["messages"]
    except Exception as e:
        st.error("加载会话失败")

def delete_session(session_name):
    try:
        if os.path.exists(f"sessions/{session_name}.json"):
            os.remove(f"sessions/{session_name}.json")
            if session_name == st.session_state.current_session:
                st.session_state.messages = []
                st.session_state.current_session = generate_session_name()


    except Exception as e:
        st.error("删除会话失败")


# ==============================================================================
# 【新增模块】微信 / QQ 聊天记录导入 + 说话风格分析
#   仅支持“用户自行导出的纯文本 .txt 聊天记录”，
#   不支持微信数据库文件、加密文件、图片/语音等媒体文件。
#   流程：上传 txt → 自动解码 → 解析对话 → 本地统计风格 → 调用 DeepSeek 生成性格
#        → 自动覆盖侧边栏【伴侣信息】的 nick_name / nature（用户仍可手动改）
# ==============================================================================

MAX_UPLOAD_BYTES = 20 * 1024 * 1024   # 上传文件大小上限，防止超大文件把页面拖死
MAX_RECORD_CHARS = 300_000            # 解析文本长度上限（长文本保护）
MAX_SAMPLE_CHARS = 6000               # 送给大模型的风格样本字符上限
MAX_SAMPLE_TURNS = 400                # 送给大模型的风格样本条数上限
ANALYSIS_TIMEOUT = 60                 # 分析接口超时时间（秒）

# 微信 / QQ 导出的 txt 常见编码，按“最可能正确”的顺序尝试（修复中文乱码问题）
_CANDIDATE_ENCODINGS = ("utf-8-sig", "gb18030", "big5")

# 时间戳形态：2024-03-01 21:03 / 2024/3/1 21:03:12 / 2024年3月1日 21:03
_TIMESTAMP = r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?\s+\d{1,2}:\d{2}(?::\d{2})?"
# 格式一：时间在前、昵称在后（微信、QQ 文本导出的主流格式）
TS_FIRST_RE = re.compile(rf"^(?P<time>{_TIMESTAMP})\s+(?P<name>.{{1,40}}?)\s*$")
# 格式二：昵称在前、时间在后
NAME_FIRST_RE = re.compile(rf"^(?P<name>.{{1,40}}?)\s+(?P<time>{_TIMESTAMP})\s*$")
# 格式三：昵称: 内容
COLON_RE = re.compile(r"^(?P<name>[^:：\[\]<>]{1,24})[:：][ \t]?(?P<content>.*)$")
# QQ 导出里的 “昵称(123456)” 尾巴
QQ_NUMBER_RE = re.compile(r"[\(（]\d{4,12}[\)）]\s*$")
# QQ 导出头部会声明“消息对象”，可以用来直接判断谁是伴侣
DECLARED_PARTNER_RE = re.compile(
    r"(?:消息对象|聊天对象|对方昵称|好友昵称|联系人|对方)\s*[:：]\s*([^\n\r]{1,32})")
SEPARATOR_RE = re.compile(r"^[=\-*_~\s]{3,}$")

# 这些名字说明说话人就是“用户本人”，自动从伴侣候选里排除
SELF_NAME_HINTS = {"我", "自己", "本人", "我自己", "me", "self", "myself", "对方"}

# Emoji 基础字符（不含变体选择符，避免 ☀️ 被拆成 ☀ 和一个不可见字符）
_EMOJI_BASE = ("[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF\u2190-\u21FF"
               "\u2600-\u27BF\u2B00-\u2BFF]")
# Emoji / 符号表情（允许紧跟一个变体选择符或零宽连接符）
EMOJI_RE = re.compile(_EMOJI_BASE + r"[\uFE0F\u200D]?")
# 微信文字表情，如 [微笑] [捂脸]
TEXT_FACE_RE = re.compile(r"\[([\u4e00-\u9fa5A-Za-z]{1,6})\]")
# 媒体 / 通话类标记（不是说话风格，统计与取样时都要排除）
_MEDIA_WORDS = ("图片", "照片", "表情", "动画表情", "语音", "视频", "文件", "位置", "链接", "转账",
                "红包", "音乐", "分享", "卡券", "名片", "聊天记录", "视频通话", "语音通话",
                "GIF", "image", "video", "file", "voice", "link", "sticker")
_MEDIA_LOWER = {word.lower() for word in _MEDIA_WORDS}
# 纯媒体 / 通话标记
MEDIA_MARKER_RE = re.compile(
    r"^[\s\[\(（【]*(?:" + "|".join(_MEDIA_WORDS) + r")[\s\]\)）】]*$", re.IGNORECASE)
# 中文高频语气词，用于判断语气风格
TONE_PARTICLES = ["呀", "啦", "嘛", "呢", "哦", "噢", "喔", "哈", "嘿", "哎", "诶",
                  "呐", "嗷", "唔", "嗯", "噻", "滴", "嘞", "惹"]


class ChatImportError(Exception):
    """聊天记录导入 / 分析过程中的可预期错误，用于在页面上给出友好提示"""


def describe_api_error(exc):
    """把底层异常翻译成用户看得懂的中文提示（超时、断网、密钥无效等）"""
    name = type(exc).__name__
    text = str(exc)
    low = text.lower()
    if "timeout" in name.lower() or "timeout" in low or "timed out" in low:
        return f"接口请求超时（{ANALYSIS_TIMEOUT} 秒未响应），请稍后重试。"
    if "connection" in name.lower() or "connect" in low:
        return "无法连接 DeepSeek 接口，请检查网络或代理设置后重试。"
    if "authentication" in name.lower() or "401" in text or "invalid api key" in low:
        return "DEEPSEEK_API_KEY 无效或未生效，请检查环境变量配置。"
    if "ratelimit" in name.lower() or "429" in text or "rate limit" in low:
        return "触发接口频率限制，请稍等片刻再试。"
    if "insufficient" in low or "402" in text or "balance" in low:
        return "DeepSeek 账户余额不足，请充值后重试。"
    return f"接口调用失败（{name}）：{text[:200]}"


def get_client():
    """取得 DeepSeek 客户端（延迟校验，避免缺少密钥时整个页面启动即崩溃）"""
    if client is None:
        raise ChatImportError(
            "没有检测到环境变量 DEEPSEEK_API_KEY，请先配置你自己的 DeepSeek API Key。"
            + (f"（初始化信息：{CLIENT_INIT_ERROR[:120]}）" if CLIENT_INIT_ERROR else ""))
    return client


def decode_uploaded_file(uploaded_file):
    """
    【修复编码问题】按多种编码尝试解码上传的聊天记录文件。
    返回 (文本, 实际使用的编码名)。解码全部失败时也不会中断页面。
    """
    try:
        raw = uploaded_file.getvalue()
    except Exception as exc:
        raise ChatImportError(f"文件读取失败：{exc}") from exc
    if not raw or not raw.strip():
        raise ChatImportError("上传的文件是空的，没有可分析的内容，请重新导出聊天记录后再上传。")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ChatImportError(
            f"文件太大（{len(raw) / 1024 / 1024:.1f} MB），请拆分后再导入（上限 20 MB）。")

    # 带 BOM 的 UTF-16 文件（部分导出工具会生成）
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass

    for encoding in _CANDIDATE_ENCODINGS:
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if _looks_like_text(text):
            return text, encoding

    # 兜底：忽略无法解码的字符，保证页面不崩（同时提示用户）
    return raw.decode("utf-8", errors="replace"), "utf-8(容错模式)"


def _looks_like_text(text, sample_size=4000):
    """粗略判断解码结果是否像正常文本（乱码时替换符/控制符比例会很高）"""
    chunk = text[:sample_size]
    if not chunk:
        return False
    bad = sum(1 for ch in chunk
              if ch == "\ufffd" or (ord(ch) < 32 and ch not in "\r\n\t"))
    return bad / len(chunk) < 0.05


def _clean_speaker(name):
    """清理说话人名称：去掉 QQ 号尾巴、首尾空格和杂符号"""
    name = QQ_NUMBER_RE.sub("", (name or "").strip())
    name = name.strip(" \t:：-|")
    return name or "未知"


def _is_noise_line(line):
    """判断是否是导出文件里的系统噪音行（分隔线、消息对象声明等）"""
    text = line.strip()
    if not text:
        return True
    if SEPARATOR_RE.match(text):
        return True
    # 只有“xxx:yyy”这种头部声明才算噪音，避免误删正常的聊天内容
    if len(text) < 40:
        for keyword in ("消息对象", "消息分组", "消息记录", "导出时间", "聊天对象", "好友昵称"):
            if text.startswith(keyword):
                return True
        if (":" in text[:12] or "：" in text[:12]) and text.startswith("日期"):
            return True
    return False


def _append_turn(turns, speaker, when, buffer):
    """把缓存的多行内容合成一条消息（合并多行发言）"""
    content = "\n".join(buffer).strip()
    if content:
        turns.append({"speaker": speaker, "time": when, "content": content})


def _parse_timestamp_lines(lines, time_first=True):
    """
    格式一/二：以“时间戳 + 昵称”作为一条消息的开头，
    其后的所有非时间戳行都属于这条消息（兼容多行消息与 [图片] 之类的标记）。
    """
    header_re = TS_FIRST_RE if time_first else NAME_FIRST_RE
    turns = []
    current_speaker = None
    current_time = ""
    buffer = []
    for line in lines:
        match = header_re.match(line.strip())
        if match:
            if current_speaker is not None:
                _append_turn(turns, current_speaker, current_time, buffer)
            current_speaker = _clean_speaker(match.group("name"))
            current_time = match.group("time").strip()
            buffer = []
        elif current_speaker is not None and not _is_noise_line(line):
            buffer.append(line.strip())
    if current_speaker is not None:
        _append_turn(turns, current_speaker, current_time, buffer)
    label = "微信/QQ 时间戳格式（时间+昵称）" if time_first else "时间戳格式（昵称+时间）"
    return turns, label


def _parse_colon_lines(lines):
    """格式三：昵称: 内容（同一说话人连续发言自动合并）"""
    turns = []
    non_empty = 0
    for line in lines:
        text = line.strip()
        if not text:
            continue
        non_empty += 1
        if _is_noise_line(text):
            continue
        match = COLON_RE.match(text)
        if not match:
            continue
        name = _clean_speaker(match.group("name"))
        content = match.group("content").strip()
        if not name or len(name) > 16 or not content:
            continue
        if turns and turns[-1]["speaker"] == name:
            turns[-1]["content"] += "\n" + content
        else:
            turns.append({"speaker": name, "time": "", "content": content})
    # 校验：条数太少或覆盖率太低，说明不是“昵称: 内容”格式，交给逐行兜底
    speaker_count = len({t["speaker"] for t in turns})
    if len(turns) < 2 or speaker_count > 12 or len(turns) < non_empty * 0.4:
        return [], ""
    return turns, "昵称: 内容 格式"


def _parse_plain_lines(lines):
    """兜底：无法识别说话人时，按“一行一条消息”解析"""
    turns = [{"speaker": "未知", "time": "", "content": line.strip()}
             for line in lines if not _is_noise_line(line)]
    if not turns:
        return [], ""
    return turns, "纯文本逐行格式（未识别到说话人）"


def parse_chat_records(raw_text):
    """
    解析聊天记录文本，自动兼容多种导出格式。
    返回 {"turns": [...], "speaker_counts": {...}, "format": "..."}
    """
    if not raw_text or not raw_text.strip():
        raise ChatImportError("文件内容为空，没有可解析的聊天记录。")
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > MAX_RECORD_CHARS:          # 长文本保护：避免超长文本拖垮页面
        text = text[:MAX_RECORD_CHARS]
    lines = text.split("\n")

    turns, fmt = _parse_timestamp_lines(lines, time_first=True)
    if not turns:
        turns, fmt = _parse_timestamp_lines(lines, time_first=False)
    if not turns:
        turns, fmt = _parse_colon_lines(lines)
    if not turns:
        turns, fmt = _parse_plain_lines(lines)
    if not turns:
        raise ChatImportError("没有从文件中解析出对话内容，请确认导出的是纯文本聊天记录。")

    return {"turns": turns,
            "speaker_counts": dict(Counter(t["speaker"] for t in turns)),
            "format": fmt}


def extract_declared_partner(raw_text):
    """从导出文件的头部提取“消息对象/聊天对象”，作为判断伴侣的强线索"""
    head = (raw_text or "")[:3000]
    match = DECLARED_PARTNER_RE.search(head)
    return _clean_speaker(match.group(1)) if match else ""


def detect_partner(speaker_counts):
    """推断哪些说话人可能是“伴侣”（对方），按消息量从多到少排序"""
    speakers = [s for s in speaker_counts if s and s.lower() not in SELF_NAME_HINTS]
    if not speakers:
        speakers = list(speaker_counts)
    speakers.sort(key=lambda s: speaker_counts.get(s, 0), reverse=True)
    return speakers


def choose_default_partner(candidates, declared=""):
    """选择默认伴侣：优先用文件头部声明的“消息对象”，否则取消息最多的一位"""
    if declared:
        for name in candidates:
            if declared == name or declared in name or name in declared:
                return name
    return candidates[0] if candidates else ""


def build_style_stats(messages):
    """
    本地统计说话风格特征：平均句长、短句占比、常用 emoji、口头禅、语气词、标点习惯。
    既用于增强大模型 prompt，也用于接口异常时的本地兜底分析。
    """
    cleaned = [m.strip() for m in messages if m and m.strip()]
    stats = {"count": len(cleaned), "avg_len": 0.0, "short_ratio": 0.0, "emoji_top": [],
             "phrase_top": [], "particle_top": [], "mark_top": [], "examples": []}
    if not cleaned:
        return stats

    lengths = [len(m) for m in cleaned]
    stats["avg_len"] = round(sum(lengths) / len(lengths), 1)
    stats["short_ratio"] = round(sum(1 for n in lengths if n <= 6) / len(lengths) * 100, 1)

    emoji_counter = Counter()
    for message in cleaned:
        emoji_counter.update(EMOJI_RE.findall(message))
        # [图片]/[表情] 这类媒体标记不算说话风格，直接排除
        emoji_counter.update(f"[{face}]" for face in TEXT_FACE_RE.findall(message)
                             if face.lower() not in _MEDIA_LOWER)
    stats["emoji_top"] = [e for e, _ in emoji_counter.most_common(8)]

    phrase_counter = Counter()
    for message in cleaned:
        for segment in re.split(r"[，。！？!?~～\s,、.…；;：:]+", message):
            segment = segment.strip()
            if 1 < len(segment) <= 6:
                phrase_counter[segment] += 1
    stats["phrase_top"] = [p for p, c in phrase_counter.most_common(30) if c >= 2][:8]

    stats["particle_top"] = [p for p in TONE_PARTICLES
                             if any(p in message for message in cleaned)][:10]

    mark_counter = Counter()
    for message in cleaned:
        for char in message:
            if char in "～~！!？?。.…，,、":
                mark_counter[char] += 1
    stats["mark_top"] = [m for m, _ in mark_counter.most_common(5)]

    # 均匀取几条原话做示例（跳过纯媒体标记）
    spoken = [m for m in cleaned if not MEDIA_MARKER_RE.match(m)] or cleaned
    step = max(1, len(spoken) // 5)
    stats["examples"] = spoken[::step][:5]
    return stats


def build_style_sample(messages, max_chars=MAX_SAMPLE_CHARS, max_turns=MAX_SAMPLE_TURNS):
    """
    把对方的消息整理成风格样本：先清理纯媒体标记，再做均匀抽样，
    防止长聊天记录把 prompt 撑爆导致接口异常或费用过高。
    返回 (样本文本, 实际使用条数, 是否做了截断)
    """
    cleaned = []
    for message in messages:
        text = re.sub(r"\s+", " ", message or "").strip()
        if not text or MEDIA_MARKER_RE.match(text):
            continue
        cleaned.append(text)
    if not cleaned:      # 全是 [图片]/[表情] 之类，退回原始内容
        cleaned = [re.sub(r"\s+", " ", m).strip() for m in messages if m and m.strip()]
    if not cleaned:
        return "", 0, False

    truncated = False
    if len(cleaned) > max_turns:
        step = len(cleaned) / max_turns
        cleaned = [cleaned[int(i * step)] for i in range(max_turns)]
        truncated = True

    lines, used_chars = [], 0
    for text in cleaned:
        if used_chars + len(text) + 3 > max_chars:
            truncated = True
            break
        lines.append("- " + text)
        used_chars += len(text) + 3
    if not lines:        # 单条消息就超长：硬截断，保证还能分析
        lines = ["- " + cleaned[0][:max_chars]]
        truncated = True
    return "\n".join(lines), len(lines), truncated


# 分析用的系统提示词：要求模型输出严格 JSON，便于回填昵称/性格
ANALYSIS_SYSTEM_PROMPT = """你是一位资深的中文聊天风格分析师。
用户会给你某个人的真实微信/QQ聊天片段，请提炼这个人的说话风格，只输出 JSON，不要输出任何解释、不要用 markdown 代码块。
JSON 格式如下：
{
  "nick_name": "贴合其聊天风格的昵称，2-6 个汉字，不要加引号",
  "nature": "120-200 字的中文性格与说话风格描述",
  "style_tags": ["3-6 个风格关键词"],
  "signature_phrases": ["3-8 条他最常用的原话短句"]
}
要求：
1. nature 必须写得具体可执行，包含：语气词与口头禅、常用 emoji、句子长短、标点习惯、称呼方式、情绪表达方式、聊天节奏。
2. nick_name 与 nature 都必须严格来自聊天片段中体现出的真实风格，不要凭空美化，不要写成通用人设。
3. 全部使用中文。"""


def _extract_json(text):
    """从模型返回里稳健地取出 JSON（修复长文本/markdown 包裹导致的解析异常）"""
    if not text or not text.strip():
        raise ChatImportError("模型没有返回内容，请稍后重试。")
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(),
                     flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        # strict=False：容忍字符串里出现裸换行等控制字符（长文本性格描述很常见）
        return json.loads(cleaned, strict=False)
    except (json.JSONDecodeError, ValueError):
        pass
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ChatImportError("分析结果解析失败：返回内容里找不到 JSON，请重试。")
    raw = match.group(0)
    try:
        return json.loads(raw, strict=False)
    except (json.JSONDecodeError, ValueError):
        fixed = re.sub(r",\s*([}\]])", r"\1", raw)   # 去掉多余逗号后再试一次
        try:
            return json.loads(fixed, strict=False)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ChatImportError("分析结果解析失败：返回的不是合法 JSON，请重试。") from exc


def analyze_style_with_llm(partner_name, messages, stats):
    """
    调用 DeepSeek 分析说话风格（复用同一个 API / 同一个环境变量 DEEPSEEK_API_KEY）。
    返回 {"nick_name", "nature", "style_tags", "signature_phrases", "source", ...}
    """
    api_client = get_client()
    sample_text, used_turns, truncated = build_style_sample(messages)
    if not sample_text:
        raise ChatImportError("这位说话人没有可用于分析的文本内容。")

    user_prompt = f"""以下是聊天记录中【{partner_name}】发出的真实消息。

【统计特征】
- 样本条数：{used_turns}
- 平均每条字数：{stats['avg_len']}
- 短句（≤6字）占比：{stats['short_ratio']}%
- 高频 emoji：{' '.join(stats['emoji_top']) or '无'}
- 高频口头禅：{'、'.join(stats['phrase_top']) or '无'}
- 高频语气词：{'、'.join(stats['particle_top']) or '无'}
- 常用标点：{' '.join(stats['mark_top']) or '无'}

【真实消息样本】
{sample_text}

请输出 JSON。"""

    try:
        response = api_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            temperature=0.6,
            max_tokens=900,
            timeout=ANALYSIS_TIMEOUT,
            response_format={"type": "json_object"},
        )
    except Exception as exc:      # 超时 / 断网 / 密钥错误 / 余额不足 / 服务异常统一处理
        raise ChatImportError(describe_api_error(exc)) from exc

    try:
        content = response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError):
        raise ChatImportError("分析接口返回结构异常，请重试。")

    data = _extract_json(content)
    if not isinstance(data, dict):
        raise ChatImportError("分析结果解析失败：返回的不是 JSON 对象，请重试。")

    nick_name = str(data.get("nick_name") or "").strip().strip('"').strip("“”")[:20]
    nature = str(data.get("nature") or "").strip()
    if not nick_name or not nature:
        raise ChatImportError("分析结果不完整（昵称或性格为空），请重试。")

    def _as_list(value, limit):
        if isinstance(value, str):
            value = re.split(r"[，,、;；/|]", value)
        if not isinstance(value, (list, tuple)):
            return []
        return [str(v).strip() for v in value if str(v).strip()][:limit]

    return {
        "nick_name": nick_name,
        "nature": nature,
        "style_tags": _as_list(data.get("style_tags"), 6),
        "signature_phrases": _as_list(data.get("signature_phrases"), 8),
        "source": "DeepSeek 大模型分析",
        "sample_turns": used_turns,
        "truncated": truncated,
    }


def analyze_style_locally(partner_name, stats, messages):
    """
    本地兜底分析：未配置 API Key 或接口异常时使用（纯离线启发式规则），
    保证“导入 → 自动填充昵称性格”这条主流程在任何情况下都能走通。
    """
    nick_name = (partner_name or "").strip()[:20] or "小伴侣"
    parts = [f"{nick_name}的聊天风格由真实聊天记录统计得出："]
    parts.append(f"平均每条消息约 {stats['avg_len']} 字，"
                 f"短句（≤6字）占比 {stats['short_ratio']}%，"
                 + ("聊天节奏很快、偏短句连发。" if stats["short_ratio"] >= 50
                    else "表达相对完整，句子偏长。"))
    if stats["particle_top"]:
        parts.append("常用语气词：" + "、".join(stats["particle_top"]) + "。")
    if stats["emoji_top"]:
        parts.append("常用表情/emoji：" + " ".join(stats["emoji_top"]) + "。")
    if stats["phrase_top"]:
        parts.append("高频口头禅：" + "、".join(f"「{p}」" for p in stats["phrase_top"]) + "。")
    if stats["mark_top"]:
        parts.append("标点习惯：" + " ".join(stats["mark_top"]) + "。")
    if stats["examples"]:
        parts.append("原话示例：" + " / ".join(stats["examples"][:3]) + "。")
    parts.append("（本描述为本地统计兜底结果；配置 DEEPSEEK_API_KEY 后可获得更细腻的大模型风格分析。）")
    return {
        "nick_name": nick_name,
        "nature": "".join(parts),
        "style_tags": [],
        "signature_phrases": stats["phrase_top"][:5],
        "source": "本地统计兜底",
        "sample_turns": stats["count"],
        "truncated": False,
    }


def compose_nature_text(result):
    """
    把分析结果拼成最终写入 nature 的文本：
    性格描述 + 风格关键词 + 口头禅，让原有 system_prompt 直接就能用。
    """
    nature = (result.get("nature") or "").strip()
    tags = [t for t in result.get("style_tags") or [] if t]
    phrases = [p for p in result.get("signature_phrases") or [] if p]
    if tags:
        nature += "；风格关键词：" + "、".join(tags)
    if phrases:
        nature += "；常用原话：" + "、".join(f"「{p}」" for p in phrases[:6])
    return nature


def run_chat_style_analysis(partner_name):
    """
    点击【分析记录生成性格】后的完整流程：
    取该说话人的消息 → 风格统计 → 调用 DeepSeek（失败则本地兜底）→ 覆盖昵称与性格。
    """
    turns = st.session_state.get("chat_turns") or []
    messages = [t["content"] for t in turns if t.get("speaker") == partner_name]
    if not messages:
        st.error(f"「{partner_name}」没有可分析的消息，请换一位说话人再试。")
        st.toast("没有可分析的消息", icon="⚠️")
        return

    stats = build_style_stats(messages)
    with st.spinner("正在分析说话风格，请稍候…"):
        try:
            result = analyze_style_with_llm(partner_name, messages, stats)
        except ChatImportError as exc:
            # API 超时 / 未配置密钥 / 解析失败 → 本地统计兜底，保证功能可用
            st.warning(f"⚠️ 大模型分析未成功：{exc}")
            result = analyze_style_locally(partner_name, stats, messages)
            st.info("已自动改用本地统计兜底生成性格描述，功能可正常使用。")
            st.toast("大模型分析失败，已用本地统计兜底", icon="⚠️")
        except Exception as exc:      # 兜底：任何意外都不让页面崩溃
            st.warning(f"⚠️ 分析出现异常：{describe_api_error(exc)}")
            result = analyze_style_locally(partner_name, stats, messages)

    # ---- 自动覆盖侧边栏【伴侣信息】的两个系统变量（用户之后仍可手动修改）----
    st.session_state.nick_name = result["nick_name"]
    st.session_state.nature = compose_nature_text(result)
    st.session_state.chat_last_analysis = result

    st.toast("解析完成，已自动填充昵称与性格", icon="🧠")
    st.success(f"分析完成：伴侣昵称已更新为「{result['nick_name']}」，性格已写入侧边栏【伴侣信息】")
    st.caption(f"分析来源：{result['source']}；样本条数：{result['sample_turns']}"
               + ("（长文本已抽样截断）" if result.get("truncated") else ""))
    with st.expander("查看完整分析结果", expanded=False):
        st.write(st.session_state.nature)
        if result.get("signature_phrases"):
            st.caption("常用原话：" + "、".join(f"「{p}」" for p in result["signature_phrases"]))


def render_chat_import_panel():
    """
    侧边栏【导入聊天记录】模块（位于【伴侣信息】上方）：
    文件上传 → 解析 → 选择伴侣 → 一键分析生成性格。
    """
    st.subheader("导入聊天记录")
    st.caption(
        "⚠️ 仅支持纯文本：请先在微信/QQ 里自行把聊天记录导出为 .txt 文本文件，再上传到这里。"
        "不支持微信数据库文件、加密文件、图片/语音等媒体文件。")

    uploaded = st.file_uploader(
        "上传微信/QQ聊天记录（txt）",
        type=["txt"],
        key="chat_record_uploader",
        help="微信：聊天窗口 → 右上角 … → 导出聊天记录，或用电脑版备份工具导出为 txt。"
             "QQ：消息管理器 → 选中会话 → 右键导出消息记录，选择 txt 文本格式。")

    if uploaded is None:
        # 用户清空上传后，同步清掉旧的解析缓存，避免误用上一次的记录
        if st.session_state.get("chat_upload_signature"):
            st.session_state.chat_upload_signature = None
            st.session_state.chat_upload_name = ""
            st.session_state.chat_turns = []
            st.session_state.chat_speakers = {}
            st.session_state.chat_format = ""
        st.session_state.chat_parsed_ok = False
        return

    identifier = f"{uploaded.name}|{getattr(uploaded, 'size', '')}"
    if identifier != st.session_state.get("chat_upload_signature"):
        # 新文件：解码 + 解析（全部异常都在这里兜住）
        try:
            raw_text, encoding = decode_uploaded_file(uploaded)
            parsed = parse_chat_records(raw_text)
        except ChatImportError as exc:
            st.session_state.chat_upload_signature = None
            st.session_state.chat_parsed_ok = False
            st.session_state.chat_turns = []
            st.error(f"❌ {exc}")
            st.toast("文件格式有误，解析失败", icon="⚠️")
            st.caption("请确认：文件是 .txt 纯文本、由微信/QQ 直接导出、且内容不为空。")
            return
        except Exception as exc:      # 兜底：任何意外都不让页面崩
            st.session_state.chat_upload_signature = None
            st.session_state.chat_parsed_ok = False
            st.session_state.chat_turns = []
            st.error(f"❌ 文件读取失败：{exc}")
            st.toast("文件读取失败", icon="⚠️")
            return

        st.session_state.chat_upload_signature = identifier
        st.session_state.chat_upload_name = uploaded.name
        st.session_state.chat_encoding = encoding
        st.session_state.chat_turns = parsed["turns"]
        st.session_state.chat_speakers = parsed["speaker_counts"]
        st.session_state.chat_format = parsed["format"]
        st.session_state.chat_declared_partner = extract_declared_partner(raw_text)
        st.session_state.chat_parsed_ok = True
        st.toast(f"上传成功：{uploaded.name}", icon="📄")
        st.caption(f"文件 {uploaded.name} 上传成功，已开始解析。")

    if not st.session_state.get("chat_parsed_ok"):
        st.warning("这个文件没有解析出聊天记录，请换一个导出的 txt 再试。")
        return

    turns = st.session_state.get("chat_turns") or []
    speakers = st.session_state.get("chat_speakers") or {}
    st.success(f"解析完成：共 {len(turns)} 条消息，识别到 {len(speakers)} 位说话人")
    st.caption(f"识别格式：{st.session_state.get('chat_format')}"
               f"｜文本编码：{st.session_state.get('chat_encoding')}")

    candidates = detect_partner(speakers)
    if not candidates:
        st.error("❌ 没有识别到任何说话人，无法分析。")
        return

    default_partner = choose_default_partner(
        candidates, st.session_state.get("chat_declared_partner", ""))
    if len(candidates) > 1:
        partner = st.selectbox(
            "记录里哪一方是伴侣（对方）？",
            options=candidates,
            index=candidates.index(default_partner),
            key="chat_partner_choice",
            help="已自动判断，若判断错了可以在这里切换，再点下面的分析按钮。")
    else:
        partner = candidates[0]
        st.caption(f"只识别到一位说话人，已将「{partner}」作为伴侣。")

    st.caption(f"伴侣：{partner}（{speakers.get(partner, 0)} 条消息）")

    if st.button("分析记录生成性格", icon="🧠", width="stretch"):
        run_chat_style_analysis(partner)






st.title("AI智能伴侣")
if "messages" not in st.session_state:
    st.session_state.messages = []


if "nick_name" not in st.session_state:
    st.session_state.nick_name = "小甜甜"

if "nature" not in st.session_state:
    st.session_state.nature = "温柔开朗"


if "current_session" not in st.session_state:

    st.session_state.current_session = generate_session_name()


# 【新增】聊天记录导入模块所需的会话状态初始化
if "chat_turns" not in st.session_state:
    st.session_state.chat_turns = []            # 解析出来的对话列表
if "chat_speakers" not in st.session_state:
    st.session_state.chat_speakers = {}         # 说话人 → 消息条数
if "chat_upload_signature" not in st.session_state:
    st.session_state.chat_upload_signature = None   # 已解析文件的指纹，避免重复解析
if "chat_parsed_ok" not in st.session_state:
    st.session_state.chat_parsed_ok = False
if "chat_last_analysis" not in st.session_state:
    st.session_state.chat_last_analysis = None  # 最近一次风格分析结果


st.text(f"会话名称：{st.session_state.current_session}")


#侧边栏
for message in st.session_state.messages:
    st.chat_message(message["role"]).write(message["content"])
    # if message["role"] == "user":
    #     st.chat_message("user").write(message["content"])
    # elif message["role"] == "assistant":
    #     st.chat_message("assistant").write(message["content"])1``
with st.sidebar:
    st.subheader("ai控制面板")

    if st.button("新建对话",width="stretch",icon="✍️" ):
        #保存信息
        save_session()
        #新建会话
        if st.session_state.messages:
            st.session_state.messages = []
            st.session_state.current_session = generate_session_name()
            save_session()
            st.rerun()
        else:
            st.toast("没有会话可以新建")


    st.text("会话历史")
    session_list = load_sessions()
    for session in session_list:
        # st.button(session,width="stretch",icon="😘")
        col1,col2 = st.columns([4,1])

        with col1 :
            if st.button(session,width="stretch",icon="😘",type="primary" if session == st.session_state.current_session else "secondary"):
                load_session(session)
                st.rerun()
        with col2:
            if st.button("",icon="❌",key=f"delete_{session}"):
                delete_session(session)
                st.rerun()


#分割
    st.divider()

    # 【新增】聊天记录导入模块（按需求放在【伴侣信息】上方）
    render_chat_import_panel()

    st.divider()

    st.subheader("伴侣信息")
    nick_name = st.text_input("昵称",placeholder="请输入名称",value=st.session_state.nick_name)
    if nick_name:
        st.session_state.nick_name = nick_name
    nature = st.text_area("性格",placeholder="请输入性格",value=st.session_state.nature)
    if nature:
        st.session_state.nature = nature

    # 【新增】提示当前昵称/性格的来源，用户依然可以随时手动修改覆盖
    if st.session_state.get("chat_last_analysis"):
        st.caption("以上昵称与性格来自聊天记录分析，可直接手动修改覆盖。")




system_prompt ="""
你叫%s,是用户的伴侣
1. 每次只输出 1 条消息
2.要体现%s的性格
3. 和用户说话语气对齐
4. 回复简短，模仿微信聊天，不要大段长文
5. 可以适度加 ❤✨这类 emoji
6. 说话符合情侣身份
7. 性格描述里提到的语气词、口头禅、常用 emoji、句子长短和标点习惯，都要在回复里真实体现出来
8. 严禁书面语和客服腔，像真人发微信一样自然聊天
"""

prompt = st.chat_input("请输入您的消息")
if prompt:
    st.chat_message("user").write(prompt)
    print("------------> 调用大模型，提示词：", prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    print([
            {"role": "system", "content": system_prompt},
            *st.session_state.messages
        ])
    # 【新增】异常捕获：接口超时 / 断网 / 密钥无效等都不再让页面崩溃
    try:
        response = get_client().chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt % (st.session_state.nick_name, st.session_state.nature)},
                *st.session_state.messages
            ],
            stream=True,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}}
        )


        #非流式输出方式
        # print("<------------ 大模型返回结果：", response.choices[0].message.content)
        # st.chat_message("assistant").write(response.choices[0].message.content)
        #流式输出
        response_message = st.empty()
        full_response = ""
        for chunk in response:
            # 【修复】开启深度思考后可能返回 choices 为空的 chunk，原写法会 IndexError
            if chunk.choices and chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                full_response += content
                response_message.chat_message("assistant").write(full_response)


        st.session_state.messages.append({"role": "assistant", "content":full_response})

        #保存会话信息
        save_session()
    except ChatImportError as exc:
        st.error(f"❌ 无法调用模型：{exc}")
    except Exception as exc:
        st.error(f"❌ 对话请求失败：{describe_api_error(exc)}")



