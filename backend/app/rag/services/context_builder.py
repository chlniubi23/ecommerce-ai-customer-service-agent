"""
Context Builder - 上下文感知检索 Query 构建器

职责：
- 结合最近对话历史 + 当前问题构建增强检索 Query
- 解决代词指代问题（如"还能退吗？"→ 结合历史"耳机坏了"）
- 控制上下文长度，避免 Query 过长影响检索精度

设计理念：
- 提取最近 N 条用户消息作为上下文
- 拼接为一条完整的检索 Query
- 短问题（如指代性追问）从历史中补充语义

架构位置：
- rag/services/ 层
- 被 rag_pipeline.py 和 agent.py 调用

示例：
    history = [
        {"role": "user", "content": "耳机坏了"},
        {"role": "assistant", "content": "很抱歉听到..."},
    ]
    current = "还能退吗？"
    →  build_retrieval_query() = "耳机坏了 还能退吗？"
"""

import logging

logger = logging.getLogger(__name__)

# 最大上下文消息数（只取最近 N 条用户消息）
MAX_CONTEXT_MESSAGES = 3
# 短问题阈值（低于此长度视为可能有指代，需补充上下文）
SHORT_QUESTION_THRESHOLD = 10
# 检索 Query 最大长度
MAX_QUERY_LENGTH = 200


def build_retrieval_query(
    current_question: str,
    history: list[dict] | None = None,
    max_context: int = MAX_CONTEXT_MESSAGES,
) -> str:
    """
    构建上下文感知的检索 Query

    策略：
    1. 如果当前问题足够长（≥10字），且不包含指代词 → 直接使用
    2. 如果当前问题短或包含指代词 → 拼接最近用户消息

    Args:
        current_question: 当前用户问题
        history: 对话历史 [{"role": "user"/"assistant", "content": "..."}]
        max_context: 最多取几条历史用户消息

    Returns:
        str: 增强后的检索 Query
    """
    if not history:
        logger.debug(f"[ContextBuilder] 无历史，直接使用: '{current_question[:50]}'")
        return current_question

    # 提取历史中的用户消息（按时间顺序）
    user_messages = [
        msg["content"] for msg in history
        if msg.get("role") == "user" and msg.get("content")
    ]

    if not user_messages:
        return current_question

    # 判断是否需要上下文增强
    needs_context = _needs_context_augmentation(current_question)

    if not needs_context:
        logger.debug(f"[ContextBuilder] 问题自身完整，直接使用: '{current_question[:50]}'")
        return current_question

    # 取最近 N 条用户消息
    recent_user = user_messages[-max_context:]

    # 拼接：历史用户消息 + 当前问题
    context_parts = recent_user + [current_question]
    # 去重（当前问题可能已在历史中）
    seen = set()
    unique_parts = []
    for part in context_parts:
        if part not in seen:
            seen.add(part)
            unique_parts.append(part)

    combined = " ".join(unique_parts)

    # 截断过长 Query
    if len(combined) > MAX_QUERY_LENGTH:
        combined = combined[-MAX_QUERY_LENGTH:]

    logger.info(
        f"[ContextBuilder] 上下文增强检索: "
        f"原始='{current_question[:30]}' → 增强='{combined[:60]}'"
    )
    return combined


def _needs_context_augmentation(question: str) -> bool:
    """
    判断问题是否需要上下文增强

    条件（满足任一）：
    1. 问题过短（可能是追问/省略主语）
    2. 包含指代词（这个、那个、它、还能...）
    3. 以动词/助词开头（无主语）
    """
    # 条件1: 短问题
    if len(question) <= SHORT_QUESTION_THRESHOLD:
        return True

    # 条件2: 包含指代词
    REFERENCE_WORDS = [
        "这个", "那个", "它", "这", "那",
        "还能", "还可以", "怎么办",
        "多久", "多少", "什么时候",
        "上面", "刚才", "之前",
    ]
    for word in REFERENCE_WORDS:
        if word in question:
            return True

    # 条件3: 以特定动词/助词开头（无主语）
    VERB_PREFIXES = ["能", "可以", "要", "想", "怎么", "为什么", "是不是"]
    for prefix in VERB_PREFIXES:
        if question.startswith(prefix):
            return True

    return False


def get_context_messages(
    history: list[dict] | None,
    max_messages: int = 6,
) -> list[dict]:
    """
    获取最近 N 条对话消息（用于 Prompt 注入）

    Args:
        history: 完整历史
        max_messages: 最多保留几条

    Returns:
        最近 N 条消息 [{"role": ..., "content": ...}]
    """
    if not history:
        return []
    return history[-max_messages:]


class ContextBuilder:
    """Context Builder 类包装器，提供面向对象接口"""

    def build_query(
        self,
        current_input: str,
        history: list[dict] | None = None,
        max_context: int = MAX_CONTEXT_MESSAGES,
    ) -> str:
        """
        构建上下文感知的检索 Query

        Args:
            current_input: 当前用户输入
            history: 对话历史
            max_context: 最大上下文消息数

        Returns:
            str: 增强后的检索 Query
        """
        return build_retrieval_query(current_input, history, max_context)

    def get_context(
        self,
        history: list[dict] | None,
        max_messages: int = 6,
    ) -> list[dict]:
        """
        获取最近的对话消息

        Args:
            history: 完整历史
            max_messages: 最多保留几条

        Returns:
            最近的消息列表
        """
        return get_context_messages(history, max_messages)


# 创建单例实例
context_builder = ContextBuilder()
