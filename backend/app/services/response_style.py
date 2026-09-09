"""AI 助手回复风格处理 - 口语化 + 去符号 + 控制长度

为什么需要这一层：
- 前端聊天框是纯文本渲染，LLM 产出的 markdown 符号（**、##、- 列表、--- 等）
  会原样暴露给用户，体验很差。
- 默认 LLM 回复偏长偏书面，不符合淘宝/抖音/拼多多客服、以及主流 AI 助手
  那种"短、口语、直给结论"的风格。

双保险设计：
1. 风格指令（STYLE_DIRECTIVE）：注入到 system prompt 末尾，从源头引导 LLM
   产出短的、口语化的、无符号的回复。
2. 输出清洗（sanitize_reply）：作为兜底，把 LLM 偶尔残留的 markdown 符号
   清掉，保证到前端的一定是干净纯文本。

架构位置：
- services/ 层，被 llm.py 的 call_llm / get_chat_response 统一调用
- 所有 Flow / Agent 的回复都会经过这里，无需逐个改造
"""

from __future__ import annotations

import re


# ============================================================
# 风格指令：注入 system prompt，引导 LLM 产出口语化短回复
# ============================================================
STYLE_DIRECTIVE = """

---

# 回复风格要求（最高优先级，必须遵守）

你是在一个手机聊天框里跟用户对话，就像淘宝、抖音、拼多多的在线客服那样。

1. 纯文本，绝对不要用任何 Markdown 符号
   - 不要用 ** 加粗、## 标题、` 代码符号、--- 分割线
   - 不要用 1. 2. 3. 或 - 这种列表符号
   - 需要分点时用自然语言："首先…然后…"，或直接分成短句

2. 简短口语，像真人发微信
   - 正常情况 1 到 3 句话说完，不超过 80 字
   - 信息确实多时，也尽量控制在 5 句以内，挑最关键的说
   - 先给结论或答案，再补一句关键信息或下一步

3. 自然亲切，不要书面腔
   - 用"你"不用"您"也可以，语气放松
   - 不要念规则手册，不要长篇大论
   - 可以适度用一个表情或语气词，但不要堆砌

4. 订单号、单号、金额等关键信息可以直接说出来，但不要加任何符号包裹
"""


# ============================================================
# 输出清洗：去除残留 markdown 符号（兜底）
# ============================================================

# 行首列表/标题/引用标记
_LINE_PREFIX_RE = re.compile(r"^[\s　]*(?:#{1,6}\s*|>\s*|[-*+]\s+|\d+[.、)]\s+)")
# 加粗 / 斜体 **text** *text* __text__ _text_
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_BOLD2_RE = re.compile(r"__(.+?)__", re.S)
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", re.S)
_ITALIC2_RE = re.compile(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", re.S)
# 行内代码 `code`
_CODE_RE = re.compile(r"`([^`]+?)`")
# 代码块 ```...```
_CODE_BLOCK_RE = re.compile(r"```[\w]*\n?(.*?)```", re.S)
# 分割线整行
_HR_RE = re.compile(r"^[\s　]*([-*_=]{3,})[\s　]*$", re.M)
# markdown 链接 [text](url) -> text
_LINK_RE = re.compile(r"\[([^\]]+?)\]\((?:[^)]+)\)")
# 多余空行（3+ 连续换行压成 2 个）
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
# 残留的成对星号 / 井号
_STRAY_SYMBOL_RE = re.compile(r"[*#`]+")


def strip_markdown(text: str) -> str:
    """把 markdown 符号清理为纯文本，尽量保留内容与可读性"""
    if not text:
        return ""

    out = text

    # 代码块：保留内容，去掉围栏
    out = _CODE_BLOCK_RE.sub(lambda m: m.group(1).strip(), out)
    # 链接：保留显示文字
    out = _LINK_RE.sub(r"\1", out)
    # 加粗 / 斜体：保留内容
    out = _BOLD_RE.sub(r"\1", out)
    out = _BOLD2_RE.sub(r"\1", out)
    out = _ITALIC_RE.sub(r"\1", out)
    out = _ITALIC2_RE.sub(r"\1", out)
    # 行内代码：保留内容
    out = _CODE_RE.sub(r"\1", out)
    # 分割线整行：删除
    out = _HR_RE.sub("", out)

    # 逐行去掉行首的 # / > / 列表标记
    lines = []
    for line in out.split("\n"):
        cleaned = _LINE_PREFIX_RE.sub("", line)
        lines.append(cleaned)
    out = "\n".join(lines)

    # 清掉任何残留的零散 * # ` 符号
    out = _STRAY_SYMBOL_RE.sub("", out)

    # 压缩多余空行和行尾空白
    out = _MULTI_NEWLINE_RE.sub("\n\n", out)
    out = "\n".join(line.rstrip() for line in out.split("\n"))
    return out.strip()


def sanitize_reply(text: str) -> str:
    """对外的统一清洗入口：去符号 + 收尾整理"""
    return strip_markdown(text)


def with_style_directive(system_prompt: str) -> str:
    """把风格指令拼接到 system prompt 末尾"""
    if not system_prompt:
        return STYLE_DIRECTIVE.strip()
    if "回复风格要求" in system_prompt:
        # 已包含（避免重复注入）
        return system_prompt
    return f"{system_prompt}{STYLE_DIRECTIVE}"
