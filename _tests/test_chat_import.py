# -*- coding: utf-8 -*-
"""纯函数单元测试：解码 / 解析 / 风格统计 / JSON 容错（离线，不依赖真实 streamlit）"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fakes  # noqa: E402

APP = fakes.find_app_path()

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print(("  PASS  " if condition else "  FAIL  ") + name + ("" if condition else f"   -> {detail!r}"))


def raises(exc_types, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_types as exc:
        return exc
    except Exception as exc:  # noqa: BLE001
        return ("WRONG_EXC", exc)
    return None


fake_st, _ = fakes.install_fakes()
runner = fakes.AppRunner(APP, fake_st)
mod = runner.run()
ChatImportError = mod.ChatImportError
UploadedFile = fakes.FakeUploadedFile


print("\n=== 1. 文件解码（编码问题修复） ===")
text, enc = mod.decode_uploaded_file(UploadedFile("a.txt", fakes.WECHAT_SAMPLE.encode("utf-8-sig")))
check("UTF-8 BOM 文件解码成功", enc == "utf-8-sig" and "小桃" in text, (enc, text[:20]))

text, enc = mod.decode_uploaded_file(UploadedFile("b.txt", fakes.WECHAT_SAMPLE.encode("utf-8")))
check("UTF-8 无 BOM 文件解码成功", "小桃" in text and enc in ("utf-8", "utf-8-sig"), (enc, text[:20]))

text, enc = mod.decode_uploaded_file(UploadedFile("c.txt", fakes.WECHAT_SAMPLE.encode("gb18030")))
check("GBK/GB18030 文件解码不乱码", "小桃" in text and "辛苦啦" in text, (enc, text[:30]))

text, enc = mod.decode_uploaded_file(UploadedFile("d.txt", fakes.WECHAT_SAMPLE.encode("utf-16")))
check("UTF-16 BOM 文件解码成功", "小桃" in text, (enc, text[:20]))

exc = raises(ChatImportError, mod.decode_uploaded_file, UploadedFile("empty.txt", b""))
check("空文件被捕获并给出友好提示", isinstance(exc, ChatImportError) and "空" in str(exc), exc)

exc = raises(ChatImportError, mod.decode_uploaded_file, UploadedFile("blank.txt", b"   \n  \t "))
check("纯空白文件被捕获", isinstance(exc, ChatImportError), exc)

try:
    result = mod.decode_uploaded_file(UploadedFile("bin.txt", bytes(range(256)) * 20))
    check("二进制乱码文件不崩溃", isinstance(result[0], str), type(result))
except ChatImportError as exc:
    check("二进制乱码文件不崩溃", True, f"以友好异常返回: {exc}")
except Exception as exc:  # noqa: BLE001
    check("二进制乱码文件不崩溃", False, f"抛出了未预期的异常 {type(exc).__name__}: {exc}")

exc = raises(ChatImportError, mod.decode_uploaded_file, UploadedFile("big.txt", b"a" * (21 * 1024 * 1024)))
check("超大文件被拒绝并提示", isinstance(exc, ChatImportError) and "太大" in str(exc), exc)


print("\n=== 2. 聊天记录解析 ===")
parsed = mod.parse_chat_records(fakes.WECHAT_SAMPLE)
check("微信时间戳格式解析成功", parsed["speaker_counts"] == {"小桃": 12, "我": 4}, parsed["speaker_counts"])
check("多行/[图片] 内容被并入上一条消息",
      any("[图片]" in t["content"] for t in parsed["turns"]),
      [t["content"] for t in parsed["turns"] if "[图片]" in t["content"]])
check("时间戳被记录", parsed["turns"][0]["time"] == "2024-03-01 21:03:12", parsed["turns"][0])

parsed_qq = mod.parse_chat_records(fakes.QQ_SAMPLE)
check("QQ 格式解析并去掉 (QQ号) 尾巴",
      set(parsed_qq["speaker_counts"]) == {"阿哲", "我"}, parsed_qq["speaker_counts"])
declared = mod.extract_declared_partner(fakes.QQ_SAMPLE)
check("从头部识别出“消息对象:阿哲”", declared == "阿哲", declared)
candidates = mod.detect_partner(parsed_qq["speaker_counts"])
check("‘我’ 被排除在伴侣候选之外", "我" not in candidates and "阿哲" in candidates, candidates)
check("默认伴侣取声明的消息对象", mod.choose_default_partner(candidates, declared) == "阿哲")

parsed_colon = mod.parse_chat_records(fakes.COLON_SAMPLE)
check("昵称: 内容 格式解析成功", parsed_colon["speaker_counts"] == {"小桃": 3, "我": 2}, parsed_colon["speaker_counts"])

parsed_plain = mod.parse_chat_records(fakes.PLAIN_SAMPLE)
check("无说话人时按逐行兜底（说话人=未知）", parsed_plain["speaker_counts"] == {"未知": 4}, parsed_plain["speaker_counts"])

exc = raises(ChatImportError, mod.parse_chat_records, "")
check("空文本解析被捕获", isinstance(exc, ChatImportError), exc)
exc = raises(ChatImportError, mod.parse_chat_records, "\n\n   \n")
check("纯空白文本解析被捕获", isinstance(exc, ChatImportError), exc)

huge_text = fakes.WECHAT_SAMPLE * 5000          # 约 50 万字符
parsed_huge = mod.parse_chat_records(huge_text)
check("超长文本（50万字符）解析不异常", len(parsed_huge["turns"]) > 0, len(parsed_huge["turns"]))
check("超长文本被截断到上限内",
      len(huge_text) > mod.MAX_RECORD_CHARS and sum(len(t["content"]) for t in parsed_huge["turns"]) < mod.MAX_RECORD_CHARS * 1.2)

single_long = "2024-03-01 21:03:12 小桃\n" + ("啊" * 50000)
parsed_single = mod.parse_chat_records(single_long)
check("单条超长消息解析不异常", len(parsed_single["turns"]) == 1, parsed_single["speaker_counts"])


print("\n=== 3. 风格统计与样本裁剪 ===")
messages = [t["content"] for t in parsed["turns"] if t["speaker"] == "小桃"]
stats = mod.build_style_stats(messages)
check("统计条数正确", stats["count"] == len(messages), (stats["count"], len(messages)))
check("识别出常用 emoji 🥰/✨", any("🥰" in e or "✨" in e for e in stats["emoji_top"]), stats["emoji_top"])
check("识别出高频语气词 呀/啦/嘛", set(stats["particle_top"]) & {"呀", "啦", "嘛", "哦"}, stats["particle_top"])
check("识别出标点习惯（～ ! 等）", bool(stats["mark_top"]), stats["mark_top"])
check("短句占比在合理区间", 0 <= stats["short_ratio"] <= 100, stats["short_ratio"])

sample, used, truncated = mod.build_style_sample(messages)
check("风格样本非空且带前缀", sample.startswith("- ") and used > 0, (used, truncated))
check("纯媒体消息([图片]/[表情])被过滤", "[图片]" not in sample and "[表情]" not in sample, sample[:80])

sample2, used2, truncated2 = mod.build_style_sample(["啊" * 50000])
check("单条超长消息样本被硬截断", truncated2 and len(sample2) <= mod.MAX_SAMPLE_CHARS + 4, (len(sample2), truncated2))

sample3, used3, _ = mod.build_style_sample([" [图片] ", "[表情]"])
check("全是媒体标记时不崩溃（退回原文）", isinstance(sample3, str), sample3)

sample4, used4, truncated4 = mod.build_style_sample(messages, max_chars=30, max_turns=2)
check("max_chars 限制生效", len(sample4) <= 40 and truncated4, (len(sample4), truncated4))


print("\n=== 4. 本地兜底分析 / 结果拼接 ===")
local = mod.analyze_style_locally("小桃", stats, messages)
check("兜底昵称使用记录里的名字", local["nick_name"] == "小桃", local["nick_name"])
check("兜底性格描述非空且提到昵称", "小桃" in local["nature"] and len(local["nature"]) > 40, local["nature"][:60])
check("兜底结果标记来源", local["source"] == "本地统计兜底", local["source"])

composed = mod.compose_nature_text({"nature": "语气活泼", "style_tags": ["活泼", "粘人"],
                                    "signature_phrases": ["好哒", "那我等你呀"]})
check("性格拼接包含关键词与口头禅",
      "活泼" in composed and "好哒" in composed and "语气活泼" in composed, composed)


print("\n=== 5. 模型返回 JSON 容错 ===")
check("标准 JSON 解析", mod._extract_json('{"nick_name":"糖糖"}')["nick_name"] == "糖糖")
check("```json 包裹也能解析", mod._extract_json('```json\n{"a":1}\n```') == {"a": 1})
check("多余逗号能被修复", mod._extract_json('前言 {"nick_name":"x",} 后语')["nick_name"] == "x")
check("多行 JSON 能被提取", mod._extract_json('{"nature":"第一行\n第二行"}')["nature"] == "第一行\n第二行")
exc = raises(ChatImportError, mod._extract_json, "这里完全没有 JSON")
check("非 JSON 内容抛出可捕获错误", isinstance(exc, ChatImportError), exc)
exc = raises(ChatImportError, mod._extract_json, "")
check("空返回抛出可捕获错误", isinstance(exc, ChatImportError), exc)


print("\n=== 6. 异常文案翻译 ===")
check("超时异常翻译成中文提示",
      "超时" in mod.describe_api_error(fakes.APITimeoutError("Request timed out")),
      mod.describe_api_error(fakes.APITimeoutError("Request timed out")))
check("密钥无效翻译成中文提示",
      "DEEPSEEK_API_KEY" in mod.describe_api_error(RuntimeError("Error code: 401 invalid api key")),
      mod.describe_api_error(RuntimeError("Error code: 401 invalid api key")))
check("连接异常翻译成中文提示",
      "无法连接" in mod.describe_api_error(fakes.APIConnectionError("connection error")),
      mod.describe_api_error(fakes.APIConnectionError("connection error")))

failed = [name for name, ok, _ in RESULTS if not ok]
print("\n" + "=" * 60)
print(f"单元测试：{len(RESULTS) - len(failed)}/{len(RESULTS)} 通过")
if failed:
    print("失败项：")
    for name in failed:
        print("  - " + name)
    sys.exit(1)
print("全部通过 ✅")
