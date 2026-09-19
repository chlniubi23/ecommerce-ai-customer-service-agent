"""RAG 真实向量库改造的离线测试。

不依赖网络与真实模型下载：
- FakeEmbeddingProvider 提供确定性哈希向量（32 维）
- VectorStore 使用 pytest tmp_path 下的临时持久化目录
"""

import hashlib
import math
import unittest
from collections import Counter

import pytest

from app.rag.schemas.document import Chunk


# ================= FakeEmbeddingProvider（确定性哈希向量，32 维） =================

class FakeEmbeddingProvider:
    """确定性 N-gram Hash 向量，仅用于测试，语义上近似字面重叠。"""

    def __init__(self, dim: int = 32):
        self.dimension = dim

    def _embed(self, text: str) -> list[float]:
        text = (text or "").lower().strip()
        ngrams: list[str] = []
        for n in (2, 3):
            for i in range(len(text) - n + 1):
                ngrams.append(text[i : i + n])
        ngrams.extend(text.split())
        if not ngrams:
            return [0.0] * self.dimension

        vec = [0.0] * self.dimension
        for gram, count in Counter(ngrams).items():
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if (h // self.dimension) % 2 == 0 else -1.0
            vec[idx] += sign * math.log1p(count)
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@pytest.fixture
def fake_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture
def store(tmp_path, fake_provider):
    from app.rag.vectorstore.chroma_store import VectorStore

    vs = VectorStore(
        persist_dir=str(tmp_path / "vector_store"),
        collection_name="test_kb",
        provider=fake_provider,
    )
    yield vs
    try:
        vs._client.close()
    except Exception:
        pass


def _make_chunk(chunk_id: str, content: str, **metadata) -> Chunk:
    base = {
        "file_id": "file_a",
        "file_name": "seven_day_return_atomic.md",
        "source": "seven_day_return_atomic.md",
        "knowledge_category": "refund",
    }
    base.update(metadata)
    return Chunk(chunk_id=chunk_id, content=content, metadata=base)


# ================= Provider 工厂 =================

class TestEmbeddingProviderFactory(unittest.TestCase):

    def setUp(self):
        from app.rag.vectorstore import embedding_provider as ep

        self.ep = ep
        ep.reset_embedding_provider()

    def tearDown(self):
        self.ep.reset_embedding_provider()

    def test_factory_returns_local_by_default(self):
        provider = self.ep.get_embedding_provider()
        self.assertIsInstance(provider, self.ep.LocalBGEProvider)
        # 单例
        self.assertIs(self.ep.get_embedding_provider(), provider)
        # 本地 provider 未加载模型（懒加载，不触发模型下载）
        self.assertIsNone(provider._model)

    def test_factory_returns_openai_when_configured(self):
        from app.core.config import get_settings

        settings = get_settings()
        original = (settings.embedding_provider, settings.embedding_api_key, settings.embedding_base_url)
        try:
            settings.embedding_provider = "openai"
            settings.embedding_api_key = "sk-test"
            settings.embedding_base_url = "https://embedding.example.com/v1"
            self.ep.reset_embedding_provider()
            provider = self.ep.get_embedding_provider()
            self.assertIsInstance(provider, self.ep.OpenAICompatProvider)
            self.assertEqual(provider.dimension, settings.embedding_dim)
        finally:
            (settings.embedding_provider, settings.embedding_api_key, settings.embedding_base_url) = original
            self.ep.reset_embedding_provider()

    def test_factory_supports_injection_override(self):
        fake = FakeEmbeddingProvider()
        self.ep.set_embedding_provider(fake)
        self.assertIs(self.ep.get_embedding_provider(), fake)
        self.ep.reset_embedding_provider()
        self.assertIsNot(self.ep.get_embedding_provider(), fake)


# ================= VectorStore 增删查 / upsert 幂等 =================

class TestVectorStoreCrud:

    def test_add_count_and_query_shape(self, store, fake_provider):
        store.add_chunks([
            _make_chunk("c1", "七天无理由退货规则：签收后7天内可无理由退货。"),
            _make_chunk("c2", "优惠券领取规则：每日可在会员中心领取。", knowledge_category="coupon", file_name="coupon_rules.md", file_id="file_b"),
            _make_chunk("c3", "MacBook Air M4 参数：芯片 M4，内存 16GB。", knowledge_category="product", file_name="macbook_air_m4.md", file_id="file_c"),
        ])
        assert store.count() == 3

        results = store.query("七天无理由退货", top_k=2)
        assert len(results) == 2
        for item in results:
            assert set(item.keys()) == {"chunk_id", "content", "metadata", "distance", "relevance_score"}
            assert 0.0 <= item["relevance_score"] <= 1.0
            assert item["distance"] == round(1.0 - item["relevance_score"], 4)

    def test_upsert_idempotent_and_content_update(self, store):
        chunk = _make_chunk("c1", "退款到账时效：原路退回 1-3 个工作日。")
        assert store.add_chunks([chunk]) == 1
        assert store.count() == 1

        # 同 chunk_id 重复入库 → 覆盖，不产生重复记录
        assert store.add_chunks([chunk]) == 1
        assert store.count() == 1

        # 内容更新生效
        updated = _make_chunk("c1", "退款到账时效：原路退回最快当天到账，1-3 个工作日。")
        store.add_chunks([updated])
        assert store.count() == 1
        stored = store.get_by_file_name("seven_day_return_atomic.md")
        assert len(stored) == 1
        assert "最快当天到账" in stored[0]["content"]

    def test_delete_by_file_id(self, store):
        store.add_chunks([
            _make_chunk("c1", "七天无理由退货规则"),
            _make_chunk("c2", "优惠券领取规则", knowledge_category="coupon", file_name="coupon_rules.md", file_id="file_b"),
        ])
        assert store.count() == 2

        store.delete_by_file_id("file_b")
        assert store.count() == 1
        assert store.get_by_file_name("coupon_rules.md") == []

    def test_get_by_file_name_returns_all_sibling_chunks(self, store):
        store.add_chunks([
            _make_chunk("c1", "MacBook Air M4 芯片参数", knowledge_category="product", file_name="macbook_air_m4.md", file_id="file_c"),
            _make_chunk("c2", "MacBook Air M4 屏幕参数", knowledge_category="product", file_name="macbook_air_m4.md", file_id="file_c"),
            _make_chunk("c3", "MacBook Air M4 电池续航", knowledge_category="product", file_name="macbook_air_m4.md", file_id="file_c"),
        ])
        items = store.get_by_file_name("macbook_air_m4.md")
        assert {item["chunk_id"] for item in items} == {"c1", "c2", "c3"}
        for item in items:
            assert set(item.keys()) == {"chunk_id", "content", "metadata"}

    def test_query_where_filter_knowledge_category(self, store):
        store.add_chunks([
            _make_chunk("c1", "七天无理由退货规则 退款时效"),
            _make_chunk("c2", "优惠券领取规则 优惠券使用", knowledge_category="coupon", file_name="coupon_rules.md", file_id="file_b"),
        ])
        results = store.query("退款 优惠券", top_k=5, where={"knowledge_category": "coupon"})
        assert results, "where 过滤应命中 coupon chunk"
        assert all(r["metadata"]["knowledge_category"] == "coupon" for r in results)

    def test_clear(self, store):
        store.add_chunks([_make_chunk("c1", "七天无理由退货规则")])
        assert store.count() == 1
        removed = store.clear()
        assert removed == 1
        assert store.count() == 0


# ================= knowledge_search_tool 同源扩展回归 =================

class TestExpandSameSourceChunks:

    def test_expand_uses_public_store_api(self, store, monkeypatch):
        from app.tools import knowledge_search_tool as tool_mod

        store.add_chunks([
            _make_chunk("c1", "MacBook Air M4 参数：芯片 M4。", knowledge_category="product", file_name="macbook_air_m4.md", file_id="file_p"),
            _make_chunk("c2", "MacBook Air M4 参数：内存 16GB 起步。", knowledge_category="product", file_name="macbook_air_m4.md", file_id="file_p"),
            _make_chunk("c3", "MacBook Air M4 参数：重量约 1.24kg。", knowledge_category="product", file_name="macbook_air_m4.md", file_id="file_p"),
        ])

        # 用临时 store 替换工具模块引用的单例（不再访问私有 _data）
        monkeypatch.setattr(tool_mod, "chroma_store", store)

        initial = [{
            "chunk_id": "c1",
            "content": "MacBook Air M4 参数：芯片 M4。",
            "metadata": {"file_name": "macbook_air_m4.md", "file_id": "file_p", "knowledge_category": "product"},
            "distance": 0.2,
            "relevance_score": 0.8,
        }]
        expanded = tool_mod._expand_same_source_chunks("MacBook Air M4 参数介绍", initial)

        assert {c["chunk_id"] for c in expanded} == {"c1", "c2", "c3"}
        by_id = {c["chunk_id"]: c for c in expanded}
        # 新并入的兄弟块标记为低相关度，不打乱主排序依据
        assert by_id["c2"]["relevance_score"] == 0.0
        assert by_id["c1"]["relevance_score"] == 0.8

    def test_non_detail_query_not_expanded(self, store, monkeypatch):
        from app.tools import knowledge_search_tool as tool_mod

        monkeypatch.setattr(tool_mod, "chroma_store", store)
        chunks = [{"chunk_id": "c1", "content": "退款规则", "metadata": {"file_name": "a.md"}, "distance": 0.1, "relevance_score": 0.9}]
        assert tool_mod._expand_same_source_chunks("退款多久到账", chunks) is chunks

    def test_rank_chunks_uses_lexical_boost_terms(self):
        from app.tools.knowledge_search_tool import _rank_chunks_for_query

        chunks = [
            {"chunk_id": "c1", "content": "七天无理由退货规则 签收后7天内", "metadata": {"knowledge_category": "refund"}, "relevance_score": 0.5},
            {"chunk_id": "c2", "content": "完全不相关的内容", "metadata": {"knowledge_category": "refund"}, "relevance_score": 0.5},
        ]
        ranked = _rank_chunks_for_query(
            "七天无理由退货的规则是什么", chunks, category="refund",
            lexical_boost_terms=["七天无理由", "退货", "退款规则"],
        )
        assert ranked[0]["chunk_id"] == "c1"
        assert "runtime_rank_score" in ranked[0]
