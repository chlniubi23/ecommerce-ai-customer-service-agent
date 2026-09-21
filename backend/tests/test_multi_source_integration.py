"""多来源信息整合与检索增强的离线测试（开发方案第六节）。

全部离线：FakeEmbeddingProvider + 临时持久化目录 + mock 工具执行器/LLM。
覆盖：
1. 截图场景回归（页面快照兜底 + 整合守则）
2. 协调器双域 enrich
3. enrich 失败不静默
4. 完整性契约触发补全
5. 父子块切分与组装
6. 多路融合（语义路失败、关键词路命中）
7. 二次补检（相关性/覆盖度）与无结果语义
"""

import hashlib
import math
import unittest
from collections import Counter
from unittest.mock import patch

from app.rag.schemas.document import Chunk, Document


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


def _make_store(tmp_path):
    from pathlib import Path

    from app.rag.vectorstore.chroma_store import VectorStore

    return VectorStore(
        persist_dir=str(Path(tmp_path) / "vs"),
        collection_name="test_kb",
        provider=FakeEmbeddingProvider(),
    )


def _tool_result(tool_name: str, data: dict | None = None, success: bool = True, error: str = ""):
    from app.tools.base_tool import ToolResult

    return ToolResult(success=success, data=data or {}, error=error, tool_name=tool_name)


def _exec_result(tool_name: str, data: dict | None = None, success: bool = True, error: str = ""):
    from app.tools.executors.tool_executor import ToolExecutionResult

    return ToolExecutionResult(
        tool_name=tool_name,
        tool_args={"order_id": (data or {}).get("order_id", "")},
        tool_result=_tool_result(tool_name, data, success, error),
        success=success,
        error=error,
        latency_ms=1.0,
    )


# 页面快照消息（模拟前端 buildContextPrompt 注入，含物流事实——复现场景）
SNAPSHOT_MESSAGE = """帮我看看这个订单现在什么状态

[系统补充上下文 - 不要把本段当成用户原话]
本轮优先处理订单号：ORD_DEMO_003
当前订单：ORD_DEMO_003 / 订单 已发货 / 支付 已支付 / 配送 运输中 / 金额 ¥999.00
物流：顺丰速运 / SFDEMO2026061601 / 运输中 / 广州转运中心
物流轨迹：2026-06-16 10:00 广州转运中心 已发出
当前登录用户：USR_TEST / 测试用户 / 13800000000
"""


class TestContextFacts(unittest.TestCase):
    """任务 A3：extract_context_facts 纯函数。"""

    def test_extract_structured_fact_lines(self):
        from app.agents.context_facts import extract_context_facts

        facts = extract_context_facts(SNAPSHOT_MESSAGE)
        self.assertIn("物流：顺丰速运 / SFDEMO2026061601 / 运输中 / 广州转运中心", facts["logistics"])
        self.assertIn("物流轨迹", facts["logistics_timeline"])
        self.assertIn("ORD_DEMO_003", facts["order"])
        self.assertNotIn("refund", facts)

    def test_no_context_returns_empty_and_never_raises(self):
        from app.agents.context_facts import extract_context_facts

        self.assertEqual(extract_context_facts("普通消息，没有上下文"), {})
        self.assertEqual(extract_context_facts(""), {})
        self.assertEqual(extract_context_facts(None), {})


class TestEnhancedFlowContractAndSnapshot(unittest.IsolatedAsyncioTestCase):
    """任务 A2/A3/A4：完整性契约、失败不静默、页面快照兜底、整合守则。"""

    async def test_screenshot_scenario_snapshot_fallback_and_rules(self):
        """截图场景回归：query_order 成功（无物流键）+ logistics_query 失败
        → LLM 输入含 [页面快照补充] 物流事实，system prompt 含整合守则。"""
        from app.agents import enhanced_flow

        called: list[str] = []

        async def fake_execute_by_name(tool_name: str, **kwargs):
            called.append(tool_name)
            if tool_name == "query_order":
                return _exec_result(tool_name, {
                    "order_id": "ORD_DEMO_003", "order_status": "已发货",
                    "payment_status": "已支付",
                })
            if tool_name == "logistics_query":
                return _exec_result(tool_name, success=False, error="未查询到物流记录")
            return _exec_result(tool_name, success=False, error="未知工具")

        captured: dict = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return "您的订单已发货。"

        with patch.object(enhanced_flow.tool_executor, "execute_by_name", side_effect=fake_execute_by_name), \
             patch.object(enhanced_flow, "call_llm", side_effect=fake_call_llm):
            result = await enhanced_flow.enhanced_flow_handle(
                user_input=SNAPSHOT_MESSAGE,
                history=[],
                tool_name="query_order",
                tool_params={"order_id": "ORD_DEMO_003"},
                domain_prompt="订单管家提示词",
            )

        # 完整性契约触发补全
        self.assertIn("logistics_query", called)
        # 失败不静默
        self.assertIn("[补全失败提示]", captured["user_message"])
        self.assertIn("logistics_query 查询失败(未查询到物流记录)", captured["user_message"])
        # 页面快照兜底（物流单号未同步但详情页可见场景）
        self.assertIn("[页面快照补充]", captured["user_message"])
        self.assertIn("SFDEMO2026061601", captured["user_message"])
        self.assertIn("（来源：用户当前页面）", captured["user_message"])
        # 整合守则在 system prompt 中
        self.assertIn("信息整合守则", captured["system_prompt"])
        self.assertIn("严禁把\"单一来源没有\"说成\"系统没有/未同步\"", captured["system_prompt"])
        self.assertEqual(result.message.content, "您的订单已发货。")

    async def test_contract_triggers_enrich_without_params_order_id(self):
        """完整性契约（修 D4）：params 无 order_id，但主工具结果缺契约字段
        （从结果中提取 order_id）→ 自动触发 logistics_query。"""
        from app.agents import enhanced_flow

        called: list[str] = []

        async def fake_execute_by_name(tool_name: str, **kwargs):
            called.append(tool_name)
            if tool_name == "query_order":
                return _exec_result(tool_name, {"order_id": "ORD_1", "order_status": "已发货"})
            if tool_name == "logistics_query":
                return _exec_result(tool_name, {
                    "order_id": "ORD_1", "carrier_name": "顺丰速运",
                    "tracking_no": "SF001", "current_status": "运输中",
                })
            return _exec_result(tool_name, success=False, error="未知工具")

        with patch.object(enhanced_flow.tool_executor, "execute_by_name", side_effect=fake_execute_by_name):
            results, context = await enhanced_flow.enhanced_tool_execute(
                "query_order", {}, enrich=True, page_facts={}
            )

        self.assertIn("logistics_query", called)
        self.assertIn("[实时查询]", context)
        self.assertIn("[补全查询]", context)
        self.assertNotIn("[补全失败提示]", context)

    async def test_enrich_failure_not_silent(self):
        """enrich 失败不再静默（修 D3）：context 含 [补全失败提示]。"""
        from app.agents import enhanced_flow

        async def fake_execute_by_name(tool_name: str, **kwargs):
            if tool_name == "query_order":
                return _exec_result(tool_name, {"order_id": "ORD_1", "order_status": "已发货"})
            if tool_name == "logistics_query":
                return _exec_result(tool_name, success=False, error="数据库连接失败")
            return _exec_result(tool_name, success=False, error="未知工具")

        with patch.object(enhanced_flow.tool_executor, "execute_by_name", side_effect=fake_execute_by_name):
            _results, context = await enhanced_flow.enhanced_tool_execute(
                "query_order", {"order_id": "ORD_1"}, enrich=True, page_facts={}
            )

        self.assertIn("[补全失败提示] logistics_query 查询失败(数据库连接失败)", context)
        self.assertIn("如实告知用户当前查询不到", context)

    def test_integration_rules_in_prompts(self):
        """任务 A4：两处提示词统一包含信息整合守则。"""
        from app.agents.enhanced_flow import ANALYSIS_PROMPT
        from app.agents.coordinator import SYNTHESIZE_PROMPT

        for prompt in (ANALYSIS_PROMPT, SYNTHESIZE_PROMPT):
            self.assertIn("信息整合守则", prompt)
            self.assertIn("同一事实以实时查询为准，快照为辅", prompt)
            self.assertIn("严禁把\"单一来源没有\"说成\"系统没有/未同步\"", prompt)


class TestCoordinatorMultiSource(unittest.IsolatedAsyncioTestCase):
    """任务 A1：协调器双域增强编排 + 前端事实保留。"""

    async def test_dual_domain_merges_enrich_tool_calls(self):
        from app.agents import coordinator

        called: list[str] = []

        async def fake_execute_by_name(tool_name: str, **kwargs):
            called.append(tool_name)
            if tool_name == "query_order":
                return _exec_result(tool_name, {"order_id": "ORD_DEMO_003", "order_status": "已发货"})
            if tool_name == "logistics_query":
                return _exec_result(tool_name, {
                    "order_id": "ORD_DEMO_003", "carrier_name": "顺丰速运",
                    "tracking_no": "SFDEMO2026061601", "current_status": "运输中",
                })
            return _exec_result(tool_name, success=False, error="未知工具")

        captured: dict = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return "订单已发货，物流在途。"

        with patch.object(coordinator.tool_executor, "execute_by_name", side_effect=fake_execute_by_name), \
             patch.object(coordinator, "call_llm", side_effect=fake_call_llm):
            result = await coordinator.coordinate(
                SNAPSHOT_MESSAGE, history=[], domains=["order", "logistics"]
            )

        tool_names = [tc.get("tool_name") for tc in result.tool_calls]
        # 双域各自的主工具都被调用
        self.assertIn("query_order", tool_names)
        self.assertIn("logistics_query", tool_names)
        # order 域触发了 enrich（order 域链路中出现 logistics_query）
        self.assertGreaterEqual(tool_names.count("logistics_query"), 1)
        # D1 修复：LLM 综合输入保留前端页面实时快照
        self.assertIn("[页面实时快照（前端注入，可信）]", captured["user_message"])
        self.assertIn("SFDEMO2026061601", captured["user_message"])

    async def test_intent_detection_still_uses_visible_input_only(self):
        """红线回归：意图判定/闸门仍只用 visible_input，前端上下文不触发多意图。"""
        from app.agents import coordinator

        self.assertEqual(coordinator.detect_multi_intent(SNAPSHOT_MESSAGE), ["order"])
        self.assertFalse(coordinator.should_coordinate(SNAPSHOT_MESSAGE))


class TestParentChildChunking(unittest.TestCase):
    """任务 B1：父子块切分、检索面排除父块、get_by_ids 回取父块。"""

    def test_chunker_produces_parent_and_children(self):
        from app.rag.chunkers import ParentChildChunker

        long_text = "退款规则说明。" + "用户在签收后七天内可以无理由退货，退款原路退回，1到3个工作日到账。" * 20
        docs = [Document(page_content=long_text, metadata={
            "file_id": "kb_refund_demo", "file_name": "refund_demo.md",
            "knowledge_category": "refund",
        })]
        parents, children = ParentChildChunker().chunk_documents(docs)

        self.assertGreaterEqual(len(parents), 1)
        self.assertGreater(len(children), len(parents))
        parent_ids = {p.chunk_id for p in parents}
        for child in children:
            self.assertEqual(child.metadata.get("chunk_type"), "child")
            self.assertIn(child.metadata.get("parent_id"), parent_ids)
        for parent in parents:
            self.assertEqual(parent.metadata.get("chunk_type"), "parent")
        # 确定性 chunk_id（rebuild 幂等）
        self.assertTrue(parents[0].chunk_id.startswith("kb_refund_demo_p"))

    def test_query_hits_children_only_and_get_by_ids_returns_parent(self):
        from unittest.mock import patch as _patch

        from app.rag.chunkers import ParentChildChunker
        from app.tools import knowledge_search_tool as tool_module
        from app.tools.knowledge_search_tool import _attach_parent_content

        store = _make_store(self._tmp_dir())
        long_text = "七天无理由退货规则总览。" + "签收后七天内可无理由退货，商品完好不影响二次销售，退款原路退回。" * 20
        docs = [Document(page_content=long_text, metadata={
            "file_id": "kb_refund_demo2", "file_name": "refund_demo2.md",
            "knowledge_category": "refund",
        })]
        parents, children = ParentChildChunker().chunk_documents(docs)
        store.add_chunks(parents + children)

        # 检索面只命中子块（父块 chunk_type=parent 被排除）
        hits = store.query("七天无理由退货规则总览", top_k=10)
        self.assertTrue(hits)
        for hit in hits:
            self.assertNotEqual(hit["metadata"].get("chunk_type"), "parent")

        # 命中子块按 parent_id 回取父块完整内容
        child = hits[0]
        parent_id = child["metadata"]["parent_id"]
        parents_by_id = {p["chunk_id"]: p for p in store.get_by_ids([parent_id])}
        self.assertIn(parent_id, parents_by_id)
        self.assertIn("七天无理由退货规则总览", parents_by_id[parent_id]["content"])

        # 工具组装：chunk 获得 parent_content（注入测试 store，不触碰真实单例）
        with _patch.object(tool_module, "chroma_store", store):
            attached = _attach_parent_content([dict(child)])
        self.assertIn("parent_content", attached[0])
        self.assertIn("七天无理由退货规则总览", attached[0]["parent_content"])
        store._client.close()

    def _tmp_dir(self):
        import tempfile

        return tempfile.mkdtemp(prefix="pc_chunk_")


class TestMultiRouteFusion(unittest.TestCase):
    """任务 B2：双路检索与 RRF 融合。"""

    def test_keyword_route_hits_when_vector_below_threshold(self):
        import tempfile
        from unittest.mock import patch as _patch

        from app.rag.services import retrieval_service as rs_module
        from app.rag.services.retrieval_service import RetrievalService

        tmp = tempfile.mkdtemp(prefix="fusion_")
        store = _make_store(tmp)
        store.add_chunks([
            Chunk(chunk_id="c_coupon", content="优惠券领取规则：每日可在会员中心领取优惠券。", metadata={
                "file_id": "f1", "file_name": "coupon_rules.md", "knowledge_category": "coupon",
            }),
            Chunk(chunk_id="c_refund", content="退货规则：签收后七天内可无理由退货。", metadata={
                "file_id": "f2", "file_name": "refund_rules.md", "knowledge_category": "refund",
            }),
        ])

        svc = RetrievalService(top_k=5, min_score=0.99)  # 阈值极高 → 语义路必空
        with _patch.object(rs_module, "chroma_store", store):
            fused = svc.query_knowledge_fused(
                question="优惠券怎么领取",
                keyword_terms=["优惠券", "领取"],
                top_k=5,
                min_score=0.99,
            )

        self.assertTrue(fused.has_relevant)
        routes = fused.chunks[0].get("retrieval_routes")
        self.assertEqual(routes, ["keyword"])
        self.assertEqual(fused.chunks[0]["chunk_id"], "c_coupon")
        self.assertIn("keyword", fused.debug_info["routes"])
        self.assertEqual(fused.debug_info["routes"]["vector"]["count"], 0)
        store._client.close()


class TestRevalidation(unittest.IsolatedAsyncioTestCase):
    """任务 B3：结果校验与二次补检（最多一次）。"""

    def _make_tool(self):
        from app.tools.knowledge_search_tool import KnowledgeSearchTool

        return KnowledgeSearchTool()

    def _retrieval_result(self, chunks, debug=None):
        from app.rag.services.retrieval_service import RetrievalResult

        return RetrievalResult(query="q", chunks=chunks, has_relevant=bool(chunks), debug_info=debug or {})

    async def test_relevance_revalidation_recovers_with_expanded_query(self):
        """首路无向量命中 → expanded_query 重检并取最优。"""
        from app.tools import knowledge_search_tool as tool_module

        golden_chunk = {
            "chunk_id": "g1", "content": "七天无理由退货：签收后七天内可无理由退货，商品需完好。",
            "metadata": {"file_id": "f1", "file_name": "seven_day_return_atomic.md",
                         "knowledge_category": "refund", "chunk_index": 0},
            "distance": 0.25, "relevance_score": 0.75,
            "retrieval_routes": ["vector"], "rrf_score": 0.016,
        }
        calls: list[dict] = []

        def fake_fused(question, keyword_terms=None, top_k=None, min_score=None):
            calls.append({"question": question, "min_score": min_score})
            if len(calls) < 3:
                return self._retrieval_result([])
            return self._retrieval_result([dict(golden_chunk)])

        tool = self._make_tool()
        with patch.object(tool_module.retrieval_service, "query_knowledge_fused", side_effect=fake_fused):
            result = await tool.execute(
                query="七天无理由退货的规则是什么", top_k=3, allow_llm=False,
                workflow_id="t", session_id="t",
            )

        self.assertTrue(result.success)
        self.assertTrue(result.data["debug_info"]["revalidation"]["triggered"])
        self.assertEqual(result.data["debug_info"]["revalidation"]["reason"], "relevance")
        self.assertTrue(any(c["chunk_id"] == "g1" for c in result.data["chunks"]))
        # 至少含 expanded_query 重检调用
        self.assertGreaterEqual(len(calls), 3)

    async def test_coverage_revalidation_with_entity_guard(self):
        """覆盖度校验：top-5 无实体 → 实体窄查询重检；补检结果须含实体。"""
        from app.tools import knowledge_search_tool as tool_module

        irrelevant = {
            "chunk_id": "x1", "content": "完全无关的通用说明内容。",
            "metadata": {"file_id": "f9", "file_name": "misc.md",
                         "knowledge_category": "product", "chunk_index": 0},
            "distance": 0.4, "relevance_score": 0.6,
            "retrieval_routes": ["vector"], "rrf_score": 0.016,
        }
        macbook = {
            "chunk_id": "m1", "content": "MacBook Air M4 内存 16GB，不支持用户自行扩展内存。",
            "metadata": {"file_id": "f2", "file_name": "macbook_air_m4_specs_atomic.md",
                         "knowledge_category": "product", "chunk_index": 0},
            "distance": 0.3, "relevance_score": 0.7,
            "retrieval_routes": ["vector"], "rrf_score": 0.016,
        }

        call_count = {"n": 0}

        def fake_fused(question, keyword_terms=None, top_k=None, min_score=None):
            # 第 1 次调用 = 初始融合检索（返回无关块）；第 2 次 = 覆盖度补检（返回实体块）
            call_count["n"] += 1
            if call_count["n"] == 1:
                return self._retrieval_result([dict(irrelevant)])
            return self._retrieval_result([dict(macbook)])

        tool = self._make_tool()
        with patch.object(tool_module.retrieval_service, "query_knowledge_fused", side_effect=fake_fused):
            result = await tool.execute(
                query="MacBook Air 的内存支持扩展吗", top_k=3, allow_llm=False,
                workflow_id="t", session_id="t",
            )

        self.assertTrue(result.success)
        revalidation = result.data["debug_info"]["revalidation"]
        self.assertTrue(revalidation["triggered"])
        self.assertEqual(revalidation["reason"], "coverage")
        self.assertTrue(any(c["chunk_id"] == "m1" for c in result.data["chunks"]))

    async def test_both_failures_keep_no_result_semantics(self):
        """两次都失败 → 保持无结果语义（兜底不编造）。"""
        from app.tools import knowledge_search_tool as tool_module

        def fake_fused(question, keyword_terms=None, top_k=None, min_score=None):
            return self._retrieval_result([])

        tool = self._make_tool()
        with patch.object(tool_module.retrieval_service, "query_knowledge_fused", side_effect=fake_fused):
            result = await tool.execute(
                query="怎么申请营业执照", top_k=3, allow_llm=False,
                workflow_id="t", session_id="t",
            )

        self.assertFalse(result.success)
        self.assertTrue(result.data["debug_info"]["revalidation"]["triggered"])
        self.assertEqual(result.data["chunks"], [])


class TestContextSourceAnnotation(unittest.TestCase):
    """任务 B4：final_context 片段来源标注与父块内容。"""

    def test_build_context_annotates_source_and_parent(self):
        from app.knowledge_agent.context import knowledge_context_builder

        chunks = [{
            "chunk_id": "kb_refund_demo_p0000_c0001",
            "content": "子块片段：签收后七天内可无理由退货。",
            "metadata": {
                "file_id": "kb_refund_demo", "file_name": "seven_day_return_atomic.md",
                "knowledge_category": "refund", "chunk_index": 1, "parent_id": "kb_refund_demo_p0000",
            },
            "distance": 0.25, "relevance_score": 0.75,
            "parent_content": "父块完整内容：七天无理由退货规则总览……签收后七天内可无理由退货……",
        }]
        context = knowledge_context_builder.build_context(chunks)

        self.assertIn("[来源: refund/seven_day_return_atomic.md | 命中: 子块#1 | 父块完整内容]", context)
        self.assertIn("父块完整内容：七天无理由退货规则总览", context)
        self.assertIn("Chunk ID: kb_refund_demo_p0000_c0001", context)

    def test_build_context_without_parent(self):
        from app.knowledge_agent.context import knowledge_context_builder

        chunks = [{
            "chunk_id": "legacy_1", "content": "旧格式片段内容。",
            "metadata": {"file_name": "old.md", "knowledge_category": "faq", "chunk_index": 0},
            "distance": 0.4, "relevance_score": 0.6,
        }]
        context = knowledge_context_builder.build_context(chunks)
        self.assertIn("[来源: faq/old.md | 命中: 片段#0]", context)
        self.assertIn("旧格式片段内容。", context)


if __name__ == "__main__":
    unittest.main()
