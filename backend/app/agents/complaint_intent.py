"""投诉动作意图识别（纯函数，无副作用）

集中处理与"创建投诉"相关的三类用户意图判定，供分类器、协调器、
TicketFlow 和 Agent 确认闸门复用，避免各处正则不一致导致误建投诉。

三类判定：
- is_explicit_create_request: 用户是否明确要"创建/提交/发起"投诉
- is_confirmation: 在等待确认时，用户是否同意提交
- is_denial: 在等待确认时，用户是否拒绝/取消

设计要点：
- 查询/跟进/总结类（"跟进投诉""查询投诉""投诉进度""投诉情况"）
  绝不能被判为创建请求 —— 这是历史 bug 的根因。
"""

from __future__ import annotations

import re

SYSTEM_CONTEXT_MARKER = "[系统补充上下文"

# 只读动作：出现这些词时，即使句子里有"投诉/工单"也不算创建
_QUERY_VERBS = (
    "跟进", "查询", "查看", "查一下", "看看", "看一下", "进度", "情况",
    "记录", "状态", "怎么样", "处理到", "到哪", "总结", "汇总", "说明",
    "是否需要升级", "有没有",
)

# 明确的创建动作词
_CREATE_VERBS = ("创建", "提交", "发起", "新建", "立案", "我要", "我想", "帮我", "需要", "给我")

# 创建动作的目标名词
_COMPLAINT_NOUNS = ("投诉", "工单", "客诉")

# 投诉/工单编号（跟进时用户可能给投诉号 CMP... 或工单号 TKT...）。
# 注意：不能用 \b —— 编号紧贴中文时（"工单CMP_DEMO_D01的进度"）\b 不成立，
# 改用字母数字负向环视做边界。
_TICKET_REF_PATTERN = re.compile(
    r'(?<![A-Za-z0-9])((?:CMP|TKT)[A-Za-z0-9_\-]{2,40})(?![A-Za-z0-9])'
)

# 跟进/查询进度类提示词
_FOLLOWUP_HINTS = (
    "跟进", "进度", "处理到", "状态", "怎么样了", "是否需要升级",
    "查一下", "查询", "查看",
)


def user_visible_input(text: str) -> str:
    """去掉前端附加的系统上下文，只保留用户可见话术。"""
    return text.split(SYSTEM_CONTEXT_MARKER, 1)[0].strip()


def extract_complaint_id(text: str) -> str | None:
    """从用户可见话术中提取投诉/工单编号（CMP.../TKT...），没有则返回 None。"""
    match = _TICKET_REF_PATTERN.search(user_visible_input(text))
    return match.group(1) if match else None


def is_followup_request(text: str) -> bool:
    """用户是否在跟进某个已有投诉（带编号 + 投诉名词 + 跟进动作）。

    跟进是只读动作：命中后必须路由到读取真实投诉记录的分支，
    绝不能落入创建投诉或知识库检索。
    """
    visible = user_visible_input(text)
    if not visible:
        return False
    has_ref = _TICKET_REF_PATTERN.search(visible) is not None
    mentions_complaint = any(noun in visible for noun in _COMPLAINT_NOUNS)
    has_followup = any(hint in visible for hint in _FOLLOWUP_HINTS)
    return has_ref and mentions_complaint and has_followup


def _has_query_verb(text: str) -> bool:
    return any(verb in text for verb in _QUERY_VERBS)


def is_explicit_create_request(text: str) -> bool:
    """用户是否明确要创建/提交投诉（排除查询/跟进类）。"""
    visible = user_visible_input(text)
    if not visible:
        return False

    # 只读动作优先：跟进/查询/总结投诉一律不算创建
    if _has_query_verb(visible):
        return False

    has_noun = any(noun in visible for noun in _COMPLAINT_NOUNS)
    if not has_noun:
        return False

    return any(verb in visible for verb in _CREATE_VERBS)


_CONFIRM_PATTERNS = (
    "确认", "确定", "提交吧", "提交", "可以", "好的", "好", "行", "嗯",
    "是的", "是", "对", "同意", "没问题", "就这样", "麻烦了", "拜托",
)

_DENY_PATTERNS = (
    "不用", "不要", "先不", "算了", "取消", "再想想", "再考虑", "不提交",
    "不了", "暂时不", "别", "no",
)


def is_denial(text: str) -> bool:
    """在等待确认时，用户是否拒绝/取消提交。"""
    visible = user_visible_input(text).strip().lower()
    if not visible:
        return False
    return any(p in visible for p in _DENY_PATTERNS)


def is_confirmation(text: str) -> bool:
    """在等待确认时，用户是否同意提交。

    先判否定，否定优先（"不用了""先不要"含"要/用"但应判为拒绝）。
    """
    visible = user_visible_input(text).strip().lower()
    if not visible:
        return False
    if is_denial(visible):
        return False
    return any(p in visible for p in _CONFIRM_PATTERNS)


def resolve_complaint_gate(has_pending: bool, user_input: str) -> str:
    """决定投诉创建闸门下一步动作（纯函数，便于测试）。

    Args:
        has_pending: 当前会话是否已有"待确认投诉"
        user_input: 用户本轮输入

    Returns:
        - "create"     有待确认投诉 + 用户确认 → 真正创建
        - "cancel"     有待确认投诉 + 用户拒绝 → 丢弃
        - "ask_again"  有待确认投诉 + 回答不明确 → 再次询问
        - "ask_confirm" 无待确认 + 用户明确要创建 → 先生成确认问句并暂存
        - "none"       无待确认 + 非创建请求（查询/跟进等）→ 不进入创建流程
    """
    if has_pending:
        if is_confirmation(user_input):
            return "create"
        if is_denial(user_input):
            return "cancel"
        return "ask_again"

    if is_explicit_create_request(user_input):
        return "ask_confirm"
    return "none"
