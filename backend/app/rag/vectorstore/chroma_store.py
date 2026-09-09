"""
向量存储 - 纯 Python 实现

职责：
- 提供 add_chunks() 存入向量
- 提供 query() 余弦相似度检索
- N-gram Hash Embedding (纯 Python，无需 torch/onnxruntime/chromadb 原生依赖)
- JSON 文件持久化

架构位置：
- rag/vectorstore/ 层
- 被 pipeline (存储) 和 retrieval_service (检索) 调用

扩展规划：
- Phase 5.3: 替换为 ChromaDB + SentenceTransformer (需修复本地 DLL 环境)
- Phase 5.4: 切换 embedding 模型 (OpenAI / BGE)
"""

import os
import re
import json
import math
import hashlib
import logging
import threading
from collections import Counter
from app.rag.schemas.document import Chunk

logger = logging.getLogger(__name__)

# ===== Embedding 维度 =====
EMBEDDING_DIM = 384


def embed_text(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """
    N-gram Hash Embedding

    纯 Python 实现，无需 torch / onnxruntime。
    使用字符 n-gram (2,3,4) + 词 n-gram 的哈希映射到固定维度向量。
    适用于中英文混合文本的相似度计算。
    """
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)

    ngrams: list[str] = []
    for n in range(2, 5):
        for i in range(len(text) - n + 1):
            ngrams.append(text[i:i + n])

    words = text.split()
    ngrams.extend(words)
    for i in range(len(words) - 1):
        ngrams.append(f"{words[i]} {words[i+1]}")

    if not ngrams:
        return [0.0] * dim

    vec = [0.0] * dim
    counts = Counter(ngrams)
    for gram, count in counts.items():
        h = int(hashlib.md5(gram.encode('utf-8')).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign * math.log1p(count)

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# 持久化目录
STORE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "vector_store"
)


class VectorStore:
    """
    纯 Python 向量存储

    使用 N-gram Hash Embedding + 余弦相似度检索。
    JSON 文件持久化，线程安全。

    Usage:
        store = VectorStore()
        store.add_chunks(chunks)
        results = store.query("问题", top_k=5)
    """

    def __init__(self, store_dir: str = STORE_DIR):
        self.store_dir = store_dir
        self._store_file = os.path.join(store_dir, "vectors.json")
        self._lock = threading.Lock()

        os.makedirs(store_dir, exist_ok=True)

        # 内存数据: list[{id, content, metadata, embedding}]
        self._data: list[dict] = []
        self._load()

        logger.info(
            f"[VECTORSTORE] 初始化: dir={store_dir}, count={len(self._data)}"
        )

    def _load(self) -> None:
        """从 JSON 加载"""
        if os.path.exists(self._store_file):
            try:
                with open(self._store_file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"[VECTORSTORE] 加载 {len(self._data)} 条记录")
            except Exception as e:
                logger.error(f"[VECTORSTORE] 加载失败: {e}")
                self._data = []

    def _save(self) -> None:
        """持久化到 JSON"""
        try:
            with open(self._store_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[VECTORSTORE] 持久化失败: {e}")

    def add_chunks(self, chunks: list[Chunk]) -> int:
        """
        将 Chunk 列表存入向量库

        Args:
            chunks: Chunk 列表

        Returns:
            int: 成功存入的数量
        """
        if not chunks:
            return 0

        with self._lock:
            existing_ids = {d["id"] for d in self._data}

            added = 0
            for chunk in chunks:
                if chunk.chunk_id in existing_ids:
                    continue

                embedding = embed_text(chunk.content)
                self._data.append({
                    "id": chunk.chunk_id,
                    "content": chunk.content,
                    "metadata": chunk.metadata,
                    "embedding": embedding,
                })
                added += 1

            self._save()

        logger.info(
            f"[VECTORSTORE] 存入 {added} 个 chunks, "
            f"总量: {len(self._data)}"
        )
        return added

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """
        余弦相似度检索

        Args:
            query_text: 查询文本
            top_k: 返回前 k 个最相关结果
            where: 可选的 metadata 过滤 (key=value 精确匹配)

        Returns:
            list[dict]: 检索结果列表
        """
        if not self._data:
            return []

        query_embedding = embed_text(query_text)

        # 计算相似度
        scored = []
        for item in self._data:
            # metadata 过滤
            if where:
                match = all(
                    item.get("metadata", {}).get(k) == v
                    for k, v in where.items()
                )
                if not match:
                    continue

            sim = _cosine_similarity(query_embedding, item["embedding"])
            # cosine similarity → distance (for compatibility)
            distance = 1.0 - sim
            scored.append({
                "chunk_id": item["id"],
                "content": item["content"],
                "metadata": item.get("metadata", {}),
                "distance": round(distance, 4),
                "relevance_score": round(max(0.0, sim), 4),
            })

        # 按相关度降序排列
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        results = scored[:top_k]

        if results:
            logger.info(
                f"[VECTORSTORE] 检索 top_{top_k}: "
                f"找到 {len(results)} 个结果, "
                f"最高相关度: {results[0]['relevance_score']:.4f}"
            )
        else:
            logger.info("[VECTORSTORE] 无结果")

        return results

    def count(self) -> int:
        """返回向量库中的文档数量"""
        return len(self._data)

    def delete_by_file_id(self, file_id: str) -> None:
        """按 file_id 删除所有相关 chunks"""
        with self._lock:
            before = len(self._data)
            self._data = [
                d for d in self._data
                if d.get("metadata", {}).get("file_id") != file_id
            ]
            removed = before - len(self._data)
            self._save()
        logger.info(f"[VECTORSTORE] 删除 file_id={file_id} 的 {removed} 个 chunks")


# 全局单例
chroma_store = VectorStore()
