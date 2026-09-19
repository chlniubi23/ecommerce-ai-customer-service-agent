"""
向量存储 - 真实 Embedding + 本地向量数据库持久化

⚠️ 存储底座回退说明（重要，写入交付报告）：
- 首选方案为 ChromaDB PersistentClient，但在本项目 Windows 环境验证失败：
  * chromadb 1.5.9：Rust 绑定在 upsert 时触发 Windows fatal exception: access violation；
  * chromadb 1.0.15：启动即 pyo3_runtime.PanicException；
  * chromadb 0.5.x：依赖 chroma-hnswlib，Python 3.12 无预编译轮子且本机无 C++ 构建环境。
- 按《开发 Prompt》第四节回退方案，改用 qdrant-client 本地模式（纯 Python 实现），
  VectorStore 对外接口与返回结构保持不变。此决策同步写入 README 与提交说明。

职责：
- 提供 add_chunks() 存入向量（真实 Embedding + upsert 幂等）
- 提供 query() cosine 语义检索（支持 metadata where 过滤）
- qdrant-client 本地模式持久化（目录 backend/vector_store/qdrant/）
- Embedding 由 embedding_provider 工厂按配置提供（local BGE / openai 兼容 API）

架构位置：
- rag/vectorstore/ 层
- 被 pipeline (存储) 和 retrieval_service (检索) 调用

对外契约（保持不变）：
- add_chunks(chunks) -> int
- query(query_text, top_k, where) -> list[{chunk_id, content, metadata, distance, relevance_score}]
- count() -> int
- delete_by_file_id(file_id) -> None
- 新增: get_by_file_name(file_name) -> list[dict]（同源扩展用）
- 新增: clear() -> int（rebuild --force / 诊断脚本清空 collection 用，返回清除前数量）

历史：
- 最初实现为 N-gram Hash Embedding + JSON 持久化（vectors.json），已替换；
  旧 vectors.json 文件保留在磁盘作为备份，不再读取。
"""

import logging
import threading
import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models

from app.core.config import BACKEND_ROOT, get_settings
from app.rag.schemas.document import Chunk
from app.rag.vectorstore.embedding_provider import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)

# 持久化目录（默认 backend/vector_store/qdrant，可用 QDRANT_PERSIST_DIR 覆盖）
STORE_DIR = str((BACKEND_ROOT / get_settings().qdrant_persist_dir).resolve())

# qdrant 点 ID 只接受 uint / UUID：用 uuid5 把字符串 chunk_id 确定性映射为 UUID，
# 保证 upsert 幂等（同 chunk_id 覆盖同一条记录）
_POINT_NS = uuid.UUID("b16f3b2a-0f5e-4c2d-9a7e-6d3c8f1a4b52")


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_POINT_NS, chunk_id))


def _to_filter(where: dict | None) -> models.Filter | None:
    """沿用旧语义：{key: value} 精确匹配 → qdrant payload 过滤条件"""
    if not where:
        return None
    return models.Filter(
        must=[
            models.FieldCondition(key=key, match=models.MatchValue(value=value))
            for key, value in where.items()
        ]
    )


class VectorStore:
    """
    本地向量存储（qdrant-client local mode）

    cosine 距离 + payload 过滤，持久化到磁盘目录，单进程内线程安全
    （qdrant 本地模式内部持锁，此锁仅保护批量写序列）。

    Usage:
        store = VectorStore()
        store.add_chunks(chunks)
        results = store.query("问题", top_k=5)
    """

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str | None = None,
        provider: EmbeddingProvider | None = None,
    ):
        settings = get_settings()
        self.store_dir = persist_dir or str((BACKEND_ROOT / settings.qdrant_persist_dir).resolve())
        self.collection_name = collection_name or settings.qdrant_collection
        self._provider = provider
        self._lock = threading.Lock()

        Path(self.store_dir).mkdir(parents=True, exist_ok=True)
        self._client = QdrantClient(path=self.store_dir)
        if not self._client.collection_exists(self.collection_name):
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.dimension,
                    distance=models.Distance.COSINE,
                ),
            )

        logger.info(
            "[VECTORSTORE] 初始化 qdrant local: dir=%s, collection=%s, count=%d",
            self.store_dir, self.collection_name, self.count(),
        )

    # -------------------- 内部 --------------------

    @property
    def dimension(self) -> int:
        """当前 Embedding 维度"""
        return self._get_provider().dimension

    def _get_provider(self) -> EmbeddingProvider:
        if self._provider is None:
            self._provider = get_embedding_provider()
        return self._provider

    # -------------------- 对外接口 --------------------

    def add_chunks(self, chunks: list[Chunk]) -> int:
        """
        将 Chunk 列表存入向量库（upsert 语义）

        同 chunk_id 重复入库覆盖旧记录（修复旧实现"重复运行 rebuild
        脚本静默跳过、内容更新不生效"的问题）。

        Args:
            chunks: Chunk 列表

        Returns:
            int: 成功存入的数量
        """
        if not chunks:
            return 0

        provider = self._get_provider()
        embeddings = provider.embed_documents([chunk.content for chunk in chunks])
        points = [
            models.PointStruct(
                id=_point_id(chunk.chunk_id),
                vector=embedding,
                payload={"chunk_id": chunk.chunk_id, "content": chunk.content, **(chunk.metadata or {})},
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]

        with self._lock:
            self._client.upsert(collection_name=self.collection_name, points=points)

        logger.info(
            "[VECTORSTORE] upsert %d 个 chunks, 向量库总量: %d",
            len(points), self.count(),
        )
        return len(points)

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """
        语义向量检索（cosine 相似度）

        Args:
            query_text: 查询文本
            top_k: 返回前 k 个最相关结果
            where: 可选的 metadata 过滤 (key=value 精确匹配)

        Returns:
            list[dict]: [{chunk_id, content, metadata, distance, relevance_score}]
        """
        total = self.count()
        if total == 0:
            return []

        provider = self._get_provider()
        query_embedding = provider.embed_query(query_text)

        response = self._client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=max(1, min(int(top_k), total)),
            query_filter=_to_filter(where),
            with_payload=True,
        )

        results: list[dict] = []
        for point in response.points:
            payload = point.payload or {}
            score = float(point.score or 0.0)
            results.append({
                "chunk_id": payload.get("chunk_id", str(point.id)),
                "content": payload.get("content", ""),
                "metadata": {
                    key: value for key, value in payload.items()
                    if key not in ("chunk_id", "content")
                },
                "distance": round(max(0.0, 1.0 - score), 4),
                "relevance_score": round(max(0.0, score), 4),
            })

        if results:
            logger.info(
                "[VECTORSTORE] 检索 top_%d: 找到 %d 个结果, 最高相关度: %.4f",
                top_k, len(results), results[0]["relevance_score"],
            )
        else:
            logger.info("[VECTORSTORE] 无结果")
        return results

    def count(self) -> int:
        """返回向量库中的文档数量"""
        return self._client.count(collection_name=self.collection_name, exact=True).count

    def delete_by_file_id(self, file_id: str) -> None:
        """按 file_id 删除所有相关 chunks"""
        with self._lock:
            before = self.count()
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[models.FieldCondition(key="file_id", match=models.MatchValue(value=file_id))]
                    )
                ),
            )
            removed = before - self.count()
        logger.info("[VECTORSTORE] 删除 file_id=%s 的 %d 个 chunks", file_id, removed)

    def get_by_file_name(self, file_name: str) -> list[dict]:
        """
        按文件名取出全部同源 chunks（无需向量计算）

        供 knowledge_search_tool 的同源扩展使用。

        Returns:
            list[dict]: [{chunk_id, content, metadata}]
        """
        if not file_name:
            return []
        points, _offset = self._client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="file_name", match=models.MatchValue(value=file_name))]
            ),
            limit=1000,
            with_payload=True,
        )
        items: list[dict] = []
        for point in points:
            payload = point.payload or {}
            items.append({
                "chunk_id": payload.get("chunk_id", str(point.id)),
                "content": payload.get("content", ""),
                "metadata": {
                    key: value for key, value in payload.items()
                    if key not in ("chunk_id", "content")
                },
            })
        return items

    def clear(self) -> int:
        """清空整个 collection（rebuild --force / 诊断脚本使用），返回清除前数量"""
        with self._lock:
            before = self.count()
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=models.Filter(must=[])),
            )
        logger.warning("[VECTORSTORE] collection 已清空 (原 %d 条)", before)
        return before


# 全局单例
chroma_store = VectorStore()
