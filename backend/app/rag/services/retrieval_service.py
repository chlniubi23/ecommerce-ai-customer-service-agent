"""
RetrievalService - 知识库检索服务

职责：
- 接收用户问题
- 查询 ChromaDB 做相似度检索
- 返回 top_k 最相关 chunks
- 提供 relevance score 过滤
- 输出结构化调试信息

架构位置：
- rag/services/ 层
- 被 rag/pipelines/rag_pipeline.py 调用

扩展规划：
- Phase 5.3: 支持 rerank (cross-encoder)
- Phase 5.4: 支持 hybrid search (BM25 + vector)
"""

import logging
from dataclasses import dataclass, field
from app.rag.vectorstore import chroma_store

logger = logging.getLogger(__name__)

# 默认参数
DEFAULT_TOP_K = 5
MIN_RELEVANCE_SCORE = 0.01  # 低于此阈值的结果视为不相关 (N-gram Hash Embedding 分数较低)


@dataclass
class RetrievalResult:
    """
    检索结果

    Attributes:
        query: 原始查询
        chunks: 检索到的 chunks (已按相关度排序)
        has_relevant: 是否有相关结果
        debug_info: 调试信息
    """
    query: str
    chunks: list[dict] = field(default_factory=list)
    has_relevant: bool = False
    debug_info: dict = field(default_factory=dict)


class RetrievalService:
    """知识库检索服务"""

    def __init__(self, top_k: int = DEFAULT_TOP_K, min_score: float = MIN_RELEVANCE_SCORE):
        self.top_k = top_k
        self.min_score = min_score

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> RetrievalResult:
        """
        检索知识库（别名方法，与query_knowledge功能相同）

        Args:
            query: 查询文本
            top_k: 返回数量
            min_score: 最低相关度

        Returns:
            RetrievalResult
        """
        return self.query_knowledge(query, top_k, min_score)

    def query_knowledge(
        self,
        question: str,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> RetrievalResult:
        """
        查询知识库

        流程:
        1. 向 ChromaDB 发送查询 (自动 embedding)
        2. 过滤低相关度结果
        3. 返回结构化结果 + 调试信息

        Args:
            question: 用户问题
            top_k: 返回数量 (覆盖默认值)
            min_score: 最低相关度 (覆盖默认值)

        Returns:
            RetrievalResult
        """
        k = top_k or self.top_k
        threshold = min_score or self.min_score

        logger.info(f"[RETRIEVAL] 查询: '{question[:50]}...', top_k={k}, min_score={threshold}")

        # 检查向量库是否有数据
        total_count = chroma_store.count()
        if total_count == 0:
            logger.warning("[RETRIEVAL] 向量库为空，无法检索")
            return RetrievalResult(
                query=question,
                has_relevant=False,
                debug_info={"total_in_store": 0, "message": "向量库为空"},
            )

        # 执行检索
        raw_results = chroma_store.query(query_text=question, top_k=k)

        # 过滤低相关度
        relevant = [r for r in raw_results if r["relevance_score"] >= threshold]

        # 构建调试信息
        debug_info = {
            "total_in_store": total_count,
            "raw_results_count": len(raw_results),
            "filtered_count": len(relevant),
            "top_k": k,
            "min_score": threshold,
            "scores": [
                {
                    "chunk_id": r["chunk_id"],
                    "relevance_score": r["relevance_score"],
                    "source": r["metadata"].get("file_name", "unknown"),
                    "content_preview": r["content"][:60],
                }
                for r in raw_results
            ],
        }

        # 日志
        if relevant:
            sources = set(r["metadata"].get("file_name", "?") for r in relevant)
            logger.info(
                f"[RETRIEVAL] 命中 {len(relevant)} 个相关 chunks, "
                f"来源: {', '.join(sources)}, "
                f"最高分: {relevant[0]['relevance_score']:.4f}"
            )
        else:
            logger.info(
                f"[RETRIEVAL] 无相关结果 (最高分: "
                f"{raw_results[0]['relevance_score']:.4f})" if raw_results else
                "[RETRIEVAL] 无结果"
            )

        return RetrievalResult(
            query=question,
            chunks=relevant,
            has_relevant=len(relevant) > 0,
            debug_info=debug_info,
        )


# 全局单例
retrieval_service = RetrievalService()
