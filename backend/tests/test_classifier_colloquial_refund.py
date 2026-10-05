"""口语退款时效查询路由回归测试（任务 E3，2026-10-05 演示实测案例）。

背景：「我那笔钱咋还没回来啊」这类无"退款"字样的纯口语时效问法曾未命中任何规则层，
LLM 分类误判为 refund 意图被退款闸门追问原因。修复后这类问法在知识规则层直接路由
knowledge_query；**保护条款**：退款申请动词在场时必须返回 None（申请表达优先于查询
表达，交回后续逻辑进退款确认闸门）。

直接测规则函数（不调 LLM），输入均为用户可见文本。
"""

import unittest

from app.agents import classifier
from app.schemas.intent import IntentType


class ColloquialRefundQueryRoutingTest(unittest.TestCase):
    # ---- 应路由 knowledge_query：纯口语时效查询 ----

    def test_demo_case_money_not_back(self):
        # 演示实测原句
        self.assertEqual(
            classifier._classify_knowledge_intent_by_rule("我那笔钱咋还没回来啊"),
            IntentType.KNOWLEDGE_QUERY,
        )

    def test_refund_how_long_to_arrive(self):
        self.assertEqual(
            classifier._classify_knowledge_intent_by_rule("退款多久能到账啊"),
            IntentType.KNOWLEDGE_QUERY,
        )

    def test_money_not_back_urgent(self):
        self.assertEqual(
            classifier._classify_knowledge_intent_by_rule("钱还没回来，急"),
            IntentType.KNOWLEDGE_QUERY,
        )

    def test_when_to_arrive_bare(self):
        self.assertEqual(
            classifier._classify_knowledge_intent_by_rule("啥时候到账"),
            IntentType.KNOWLEDGE_QUERY,
        )

    def test_more_colloquial_variants(self):
        for query in ("咋还没到账", "还没退给我", "退款还没到账呢"):
            self.assertEqual(
                classifier._classify_knowledge_intent_by_rule(query),
                IntentType.KNOWLEDGE_QUERY,
                msg=f"应路由知识库: {query}",
            )

    # ---- 保护条款：退款申请动词在场 → 不路由知识库（返回 None） ----

    def test_explicit_refund_request_not_routed_to_knowledge(self):
        self.assertIsNone(classifier._classify_knowledge_intent_by_rule("我要退款"))

    def test_apply_verb_with_colloquial_phrase_not_routed(self):
        # 申请动词 + 口语时效短语并存：申请优先
        self.assertIsNone(
            classifier._classify_knowledge_intent_by_rule("帮我申请退款，钱咋还没到")
        )

    def test_want_refund_with_colloquial_phrase_not_routed(self):
        self.assertIsNone(
            classifier._classify_knowledge_intent_by_rule("我想退款，钱还没回来")
        )

    def test_help_refund_with_arrival_phrase_not_routed(self):
        self.assertIsNone(
            classifier._classify_knowledge_intent_by_rule("帮我退货退款，还没到账")
        )

    # ---- 既有行为回归：申请表达进 refund 闸门的链路保持不变 ----

    def test_trusted_refund_instruction_still_routed_as_refund(self):
        # 业务规则层：前端可信指令的退款任务映射保持不变（裸"我要退款"由 LLM 兜底，
        # 知识层已在保护条款与 blocked_business_actions 双重放行）
        self.assertEqual(
            classifier._classify_business_intent_by_rule(
                "本轮任务：退款/售后。请关联订单号 ORD_DEMO_001。"
            ),
            IntentType.REFUND,
        )

    def test_want_refund_visible_input_reaches_refund_via_llm_fallback_path(self):
        # 「我想退款」无订单号时业务规则层可能返回 None，但知识层必须放行（None），
        # 保证最终由退款闸门/LLM 处理而不是知识库
        self.assertIsNone(classifier._classify_knowledge_intent_by_rule("我想退款"))


if __name__ == "__main__":
    unittest.main()
