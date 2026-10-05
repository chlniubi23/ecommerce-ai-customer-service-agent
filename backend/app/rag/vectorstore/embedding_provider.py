"""
Embedding Provider 抽象层

职责：
- 定义统一的 Embedding 协议（embed_documents / embed_query / dimension）
- LocalBGEProvider: sentence-transformers + BAAI/bge-small-zh-v1.5 本地推理（懒加载）
- OpenAICompatProvider: OpenAI 兼容 Embedding API（独立 base_url/key，批量 + 重试）
- 工厂 get_embedding_provider() 按 Settings.embedding_provider 返回单例，
  支持测试注入覆盖（set_embedding_provider / reset_embedding_provider）

架构位置：
- rag/vectorstore/ 层，被 chroma_store (VectorStore) 调用

注意：
- LocalBGEProvider 必须懒加载模型——模块导入发生在多个测试与 API 启动路径上，
  若在模块级加载 torch 模型会拖慢所有单测。
- bge 查询侧使用官方推荐的 query instruction 前缀，入库侧不加。
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# bge 官方推荐：查询侧加 instruction 前缀，入库侧不加
BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


def _model_fully_cached(model_name: str) -> bool:
    """判断模型是否已完整缓存到本地 HF hub 缓存目录。

    断网/受限网络环境下，sentence-transformers 默认会对 huggingface.co 发起
    版本校验请求（多次超时重试可达数分钟）。若快照已存在，则以离线模式加载，
    彻底跳过联网校验。
    """
    try:
        from huggingface_hub import constants as hf_constants

        snapshots_dir = (
            Path(hf_constants.HF_HUB_CACHE)
            / f"models--{model_name.replace('/', '--')}"
            / "snapshots"
        )
        return snapshots_dir.is_dir() and any(snapshots_dir.iterdir())
    except Exception:  # pragma: no cover - 缓存探测失败则按在线处理
        return False

# OpenAI 兼容 API 批量请求大小与重试参数
_OPENAI_BATCH_SIZE = 32
_OPENAI_MAX_RETRIES = 3
_OPENAI_RETRY_BACKOFF_SECONDS = 1.0


@runtime_checkable
class EmbeddingProvider(Protocol):
    """统一 Embedding 协议"""

    @property
    def dimension(self) -> int:
        """向量维度"""
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """入库侧批量向量化（不加查询前缀）"""
        ...

    def embed_query(self, text: str) -> list[float]:
        """查询侧向量化（bge 本地模型加官方 query instruction 前缀）"""
        ...


class LocalBGEProvider:
    """本地 sentence-transformers BGE Embedding（懒加载，线程安全单例模型）"""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer  # 懒加载，避免模块级引入 torch

                    logger.info("[EMBEDDING] 加载本地模型: %s ...", self.model_name)
                    started = time.perf_counter()
                    if _model_fully_cached(self.model_name):
                        # 快照已缓存：离线加载，跳过对 huggingface.co 的联网校验（断网环境可直达秒级加载）
                        try:
                            self._model = SentenceTransformer(
                                self.model_name, local_files_only=True
                            )
                        except TypeError:  # pragma: no cover - 兼容不支持该参数的旧版本
                            self._model = SentenceTransformer(self.model_name)
                    else:
                        # 首次下载：仍走在线路径，由用户自行保证网络可用
                        self._model = SentenceTransformer(self.model_name)
                    logger.info(
                        "[EMBEDDING] 模型加载完成: %s, 耗时 %.1fs",
                        self.model_name,
                        time.perf_counter() - started,
                    )
        return self._model

    @property
    def dimension(self) -> int:
        if self._model is not None:
            getter = getattr(
                self._model,
                "get_embedding_dimension",
                getattr(self._model, "get_sentence_embedding_dimension", None),
            )
            return int(getter())
        return int(get_settings().embedding_dim)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        model = self._get_model()
        vector = model.encode(
            f"{BGE_QUERY_INSTRUCTION}{text}",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()

    def __repr__(self) -> str:  # pragma: no cover
        return f"LocalBGEProvider(model={self.model_name!r})"


class OpenAICompatProvider:
    """OpenAI 兼容 Embedding API Provider（独立 base_url/key，批量 + 失败重试）"""

    # 单条输入上限：bge 系 API（如硅基流动）对超过 512 token 的输入直接 400 拒绝；
    # 本地 sentence-transformers 同为 512 token 上限但会自动截断。为对齐两端语义，
    # API 侧同样截断（中文约 1 字 ≈ 1 token，450 字符留出安全余量）。
    # 截断只影响超长父块的尾部——父块不参与检索命中（must_not 过滤），完整内容
    # 仍经 parent_content 返回，检索语义不受影响。
    _MAX_INPUT_CHARS = 450

    def __init__(self, model: str, api_key: str, base_url: str, dimension: int):
        from openai import OpenAI

        self.model = model
        self.dimension = int(dimension)
        self._client = OpenAI(api_key=api_key, base_url=base_url or None)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        truncated = [
            t[: self._MAX_INPUT_CHARS] if len(t) > self._MAX_INPUT_CHARS else t
            for t in texts
        ]
        response = self._client.embeddings.create(model=self.model, input=truncated)
        return [item.embedding for item in response.data]

    def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(1, _OPENAI_MAX_RETRIES + 1):
            try:
                return self._embed_batch(texts)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[EMBEDDING] openai 兼容 API 第 %d 次失败: %s", attempt, exc
                )
                if attempt < _OPENAI_MAX_RETRIES:
                    time.sleep(_OPENAI_RETRY_BACKOFF_SECONDS * attempt)
        if len(texts) > 1:
            # 整批失败（如批内个别超限条目导致 API 400）：降级为逐条请求，
            # 隔离坏条目，避免一条失败连带丢弃同批其余条目（2026-10-05 服务器
            # 部署实测：未隔离时 79 文件仅入库 52）。
            logger.warning(
                "[EMBEDDING] 整批嵌入失败（%s），降级为逐条请求隔离坏条目", last_error
            )
            vectors: list[list[float]] = []
            for text in texts:
                vectors.append(self._embed_with_retry([text])[0])
            return vectors
        raise RuntimeError(f"Embedding API 调用失败: {last_error}") from last_error

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _OPENAI_BATCH_SIZE):
            batch = texts[start : start + _OPENAI_BATCH_SIZE]
            vectors.extend(self._embed_with_retry(batch))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_with_retry([text])[0]

    def __repr__(self) -> str:  # pragma: no cover
        return f"OpenAICompatProvider(model={self.model!r}, base_url={self._client.base_url!r})"


# ===== 工厂（配置驱动 + 测试注入覆盖） =====

_provider_instance: EmbeddingProvider | None = None
_provider_override: EmbeddingProvider | None = None


def set_embedding_provider(provider: EmbeddingProvider) -> None:
    """测试注入：覆盖工厂返回的 Provider（FakeEmbeddingProvider 等）"""
    global _provider_override
    _provider_override = provider


def reset_embedding_provider() -> None:
    """清除测试注入 / 配置单例缓存"""
    global _provider_instance, _provider_override
    _provider_instance = None
    _provider_override = None


def get_embedding_provider() -> EmbeddingProvider:
    """按 Settings.embedding_provider 返回单例；测试注入优先"""
    global _provider_instance
    if _provider_override is not None:
        return _provider_override
    if _provider_instance is None:
        settings = get_settings()
        provider_name = settings.embedding_provider.strip().lower()
        if provider_name == "openai":
            _provider_instance = OpenAICompatProvider(
                model=settings.embedding_model,
                api_key=settings.embedding_api_key,
                base_url=settings.embedding_base_url,
                dimension=settings.embedding_dim,
            )
        else:
            _provider_instance = LocalBGEProvider(model_name=settings.embedding_model)
        logger.info("[EMBEDDING] provider 初始化: %s", _provider_instance)
    return _provider_instance
