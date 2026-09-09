"""
RAG Answer Pipeline - 检索增强回答管线

职责：
- 编排完整的 RAG 回答流程
- User Question → Context Build → Retrieval → Prompt Injection → LLM → Answer
- 支持上下文感知检索（结合历史消息构建 query）
- 支持 Memory-augmented Prompt（历史对话注入）
- Fallback: 无相关上下文时返回固定提示
- 输出调试日志

架构位置：
- rag/pipelines/ 层
- 被 agents/agent.py 调用

数据流（Phase 5.3 增强）：
  用户问题 + 对话历史
  → ContextBuilder.build_retrieval_query() (上下文增强检索 Query)
  → RetrievalService.query_knowledge()
  → build_rag_prompt(chunks, history) 注入上下文+记忆
  → call_llm() 生成回答
  → RAGResult (answer + retrieval_debug + retrieval_query)
"""

import time
import logging
from dataclasses import dataclass, field
from app.rag.services.retrieval_service import retrieval_service, RetrievalResult
from app.rag.services.context_builder import build_retrieval_query, get_context_messages
from app.rag.prompts import build_rag_prompt, NO_CONTEXT_RESPONSE
from app.services.llm import call_llm

logger = logging.getLogger(__name__)

DEPRECATION_METADATA = {
    "classification": "Deprecated",
    "deprecated": True,
    "production_reachable": False,
    "replacement": "KnowledgeAgent -> knowledge_search -> RetrievalService",
    "removal_candidate": True,
    "note": "Legacy direct RAG answer pipeline is isolated from production chat.",
}


@dataclass
class RAGResult:
    """
    RAG 回答结果

    Attributes:
        answer: LLM 生成的回答
        used_rag: 是否实际使用了 RAG 上下文
        retrieval: 检索结果 (含调试信息)
        prompt_length: 最终 Prompt 字符长度
        duration_ms: 总耗时 (ms)
        retrieval_query: 实际用于检索的增强 Query
        memory_count: 注入 Prompt 的历史消息数
    """
    answer: str
    used_rag: bool = False
    retrieval: RetrievalResult | None = None
    prompt_length: int = 0
    duration_ms: float = 0
    retrieval_query: str = ""
    memory_count: int = 0


async def rag_answer(
    question: str,
    history: list[dict] | None = None,
    top_k: int = 5,
    min_score: float = 0.3,
) -> RAGResult:
    """
    执行 RAG 回答管线（上下文感知版）

    流程:
    1. 构建上下文增强检索 Query (结合历史消息)
    2. 检索知识库 (similarity search)
    3. 如果有相关结果 → 注入上下文+历史 → 调用 LLM
    4. 如果无相关结果 → 返回 Fallback 回复

    Args:
        question: 用户当前问题
        history: 对话历史
        top_k: 检索 top_k
        min_score: 最低相关度阈值

    Returns:
        RAGResult
    """
    start = time.perf_counter()

    logger.info(f"[RAG] 开始 RAG 回答: '{question[:50]}'")

    # Step 1: 构建上下文感知检索 Query
    retrieval_query = build_retrieval_query(question, history)
    if retrieval_query != question:
        logger.info(f"[RAG] 上下文增强检索: '{retrieval_query[:80]}'")

    # Step 2: 检索
    retrieval_result = retrieval_service.query_knowledge(
        question=retrieval_query,
        top_k=top_k,
        min_score=min_score,
    )

    # Step 3: 判断是否有相关上下文
    if not retrieval_result.has_relevant:
        logger.info("[RAG] 无相关上下文 → 返回 Fallback")
        duration = (time.perf_counter() - start) * 1000
        return RAGResult(
            answer=NO_CONTEXT_RESPONSE,
            used_rag=False,
            retrieval=retrieval_result,
            prompt_length=0,
            duration_ms=round(duration, 2),
            retrieval_query=retrieval_query,
            memory_count=0,
        )

    # Step 4: 获取最近对话历史 (用于 Prompt 注入)
    context_messages = get_context_messages(history, max_messages=6)
    memory_count = len(context_messages)

    # Step 5: 构建 RAG Prompt (知识库 + 历史对话)
    rag_prompt = build_rag_prompt(retrieval_result.chunks, context_messages)
    prompt_length = len(rag_prompt)

    logger.info(
        f"[RAG] Prompt 构建: {len(retrieval_result.chunks)} chunks, "
        f"{memory_count} 条历史, Prompt={prompt_length} 字符"
    )

    # Step 6: 调用 LLM
    try:
        answer = await call_llm(
            system_prompt=rag_prompt,
            user_message=question,
            history=context_messages,
            temperature=0.3,
            max_tokens=1000,
        )
    except Exception as e:
        logger.error(f"[RAG] LLM 调用失败: {e}")
        answer = "抱歉，系统处理遇到问题，请稍后重试。"

    duration = (time.perf_counter() - start) * 1000

    # 调试日志
    sources = set(
        c.get("metadata", {}).get("file_name", "?")
        for c in retrieval_result.chunks
    )
    logger.info(
        f"[RAG] 回答完成: 来源={', '.join(sources)}, "
        f"chunks={len(retrieval_result.chunks)}, memory={memory_count}, "
        f"检索Query='{retrieval_query[:50]}', 耗时={duration:.0f}ms"
    )

    return RAGResult(
        answer=answer,
        used_rag=True,
        retrieval=retrieval_result,
        prompt_length=prompt_length,
        duration_ms=round(duration, 2),
        retrieval_query=retrieval_query,
        memory_count=memory_count,
    )


class RAGPipeline:
    """RAG Pipeline 类包装器，提供面向对象接口"""

    async def answer(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> RAGResult:
        """
        回答用户问题（使用RAG）

        Args:
            query: 用户问题
            history: 对话历史

        Returns:
            RAGResult: RAG结果
        """
        return await answer_question(query, history)


# 创建单例实例
rag_pipeline = RAGPipeline()
