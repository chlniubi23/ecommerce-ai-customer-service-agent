"""
RAG Prompt 模板

职责：
- 定义 RAG 增强回答的 System Prompt
- 将检索到的 chunks 注入 Prompt
- 注入最近对话历史（上下文记忆）
- 定义无上下文时的 Fallback 回复

架构位置：
- rag/prompts/ 层
- 被 rag/pipelines/rag_pipeline.py 调用

Phase 5.3 增强：
- 新增 {history_section}，将最近对话历史注入 Prompt
- 让 LLM 理解多轮上下文语境（指代消解等）
"""

RAG_SYSTEM_PROMPT = """# 你的身份

你是电商平台的智能客服"小助"，拥有企业知识库的支持。

---

# 核心规则

1. **优先依据知识库**：回答必须基于下方提供的知识库内容
2. **禁止编造**：不编造任何知识库中没有的信息
3. **坦诚告知**：如果知识库没有相关内容，明确说"根据目前的知识库信息，暂时没有找到相关内容"
4. **自然流畅**：回答要自然、友好，像真人客服一样
5. **简洁明了**：控制在 3-5 句话，不啰嗦
6. **上下文理解**：结合历史对话理解用户意图，注意指代关系

---

{history_section}

# 知识库内容

{context}

---

# 回答要求

- 直接回答用户问题，不要说"根据知识库"这样的前缀
- 如果多个文档都有相关内容，综合回答
- 结合对话历史理解用户当前问题的完整含义
- 保持亲切友好的语气"""


NO_CONTEXT_RESPONSE = (
    "抱歉，关于这个问题，我目前的知识库中暂时没有找到相关信息。"
    "您可以尝试换个方式描述，或者我可以帮您转接人工客服～"
)


def build_rag_prompt(
    chunks: list[dict],
    history: list[dict] | None = None,
) -> str:
    """
    将检索到的 chunks + 对话历史 拼接为 RAG System Prompt

    Args:
        chunks: 检索结果列表 (含 content, metadata, relevance_score)
        history: 最近对话历史 [{"role": ..., "content": ...}]

    Returns:
        str: 完整的 System Prompt (含注入的知识库上下文和历史对话)
    """
    # 构建知识库上下文
    if not chunks:
        context = "（无相关知识库内容）"
    else:
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("metadata", {}).get("file_name", "未知来源")
            score = chunk.get("relevance_score", 0)
            content = chunk["content"]
            context_parts.append(
                f"[文档{i}] 来源: {source} (相关度: {score:.2f})\n{content}"
            )
        context = "\n\n---\n\n".join(context_parts)

    # 构建历史对话段落
    history_section = _build_history_section(history)

    prompt = RAG_SYSTEM_PROMPT.replace("{context}", context)
    prompt = prompt.replace("{history_section}", history_section)
    return prompt


def _build_history_section(history: list[dict] | None) -> str:
    """
    构建历史对话 Prompt 段落

    最近 6 条消息注入 Prompt，帮助 LLM 理解上下文。
    """
    if not history:
        return ""

    # 最多取最近 6 条
    recent = history[-6:]

    lines = ["# 最近对话历史\n"]
    for msg in recent:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"用户：{content}")
        elif role == "assistant":
            lines.append(f"客服：{content}")
    lines.append("\n---\n")
    return "\n".join(lines)
