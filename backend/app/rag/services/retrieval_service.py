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
from app.rag.constants.config import RETRIEVAL_MIN_SCORE
from app.rag.vectorstore import chroma_store

logger = logging.getLogger(__name__)

# 默认参数
DEFAULT_TOP_K = 5
# 低于此阈值的结果视为不相关（读 Settings.retrieval_min_score，黄金问题校准后回填）
MIN_RELEVANCE_SCORE = RETRIEVAL_MIN_SCORE


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

    def query_knowledge_fused(
        self,
        question: str,
        keyword_terms: list[str] | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> RetrievalResult:
        """
        多路检索与融合（修 D6 前半，任务 B2）

        - 路 1（语义）：向量检索原问题（消解后的自然语言 query）；
        - 路 2（关键词）：对核心词表（原问题词 + 查询理解正式术语 + 商品型号）
          在 payload 上做包含匹配——expanded_query 的正式术语天然适合字面匹配；
        - 融合：RRF（Reciprocal Rank Fusion, k=60）合并排序，替代单一分数序；
          按 chunk_id 去重取最高 rank（多查询合并）。

        关键词命中不套用向量分阈值（字面匹配精度高）；向量命中沿用 min_score 过滤。

        Returns:
            RetrievalResult: chunks 每项含 retrieval_routes / rrf_score（新增字段，向后兼容）
        """
        k = top_k or self.top_k
        threshold = min_score or self.min_score

        total_count = chroma_store.count()
        if total_count == 0:
            return RetrievalResult(
                query=question,
                has_relevant=False,
                debug_info={"total_in_store": 0, "message": "向量库为空"},
            )

        # 路 1：语义向量检索（原问题）
        vector_result = self.query_knowledge(question, top_k=k, min_score=threshold)
        vector_hits = vector_result.chunks

        # 路 2：关键词检索（核心词表：原问题词 + 查询理解正式术语 + 商品型号）
        keyword_hits: list[dict] = []
        if keyword_terms:
            keyword_hits = chroma_store.keyword_search(terms=keyword_terms, top_k=k)

        # RRF 融合（k=60），按 chunk_id 去重取最高 rank
        fused = _rrf_fuse([("vector", vector_hits), ("keyword", keyword_hits)], k=60)

        debug_info = {
            **vector_result.debug_info,
            "total_in_store": total_count,
            "fusion": "rrf(k=60)",
            "routes": {
                "vector": {
                    "count": len(vector_hits),
                    "top_score": vector_hits[0]["relevance_score"] if vector_hits else 0.0,
                },
                "keyword": {
                    "count": len(keyword_hits),
                    "terms": list(keyword_terms or []),
                    "top_score": keyword_hits[0]["relevance_score"] if keyword_hits else 0.0,
                },
            },
        }

        if fused:
            logger.info(
                "[RETRIEVAL] 融合检索: 语义路 %d 条 + 关键词路 %d 条 → 融合 %d 条, "
                "top1 routes=%s score=%.4f",
                len(vector_hits), len(keyword_hits), len(fused),
                fused[0].get("retrieval_routes"), fused[0].get("relevance_score", 0.0),
            )
        else:
            logger.info("[RETRIEVAL] 融合检索无结果 (两路均未命中)")

        return RetrievalResult(
            query=question,
            chunks=fused,
            has_relevant=len(fused) > 0,
            debug_info=debug_info,
        )


def _rrf_fuse(route_lists: list[tuple[str, list[dict]]], k: int = 60) -> list[dict]:
    """RRF 融合多路检索结果，按 chunk_id 去重取最高 rank。

    同 chunk 同时命中多路时：relevance_score 以向量分为准（引用/阈值语义不变），
    仅关键词命中时用关键词匹配比例作为分数，并标注来源路由。
    """
    entries: dict[str, dict] = {}
    for route_name, items in route_lists:
        for rank, item in enumerate(items, start=1):
            chunk_id = item.get("chunk_id")
            if not chunk_id:
                continue
            entry = entries.setdefault(chunk_id, {
                "chunk_id": chunk_id,
                "content": item.get("content", ""),
                "metadata": item.get("metadata", {}),
                "distance": item.get("distance", 1.0),
                "relevance_score": item.get("relevance_score", 0.0),
                "retrieval_routes": [],
                "rrf_score": 0.0,
            })
            entry["rrf_score"] += 1.0 / (k + rank)
            if route_name not in entry["retrieval_routes"]:
                entry["retrieval_routes"].append(route_name)
            if route_name == "vector":
                # 向量分优先（阈值/引用语义与基线一致）
                entry["relevance_score"] = item.get("relevance_score", entry["relevance_score"])
                entry["distance"] = item.get("distance", entry["distance"])
            elif entry["retrieval_routes"] == ["keyword"]:
                entry["distance"] = item.get("distance", entry["distance"])

    fused = sorted(entries.values(), key=lambda e: e["rrf_score"], reverse=True)
    for entry in fused:
        entry["rrf_score"] = round(entry["rrf_score"], 6)
    return fused


# 全局单例
retrieval_service = RetrievalService()
