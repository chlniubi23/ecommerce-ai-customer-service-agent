import unittest
from unittest.mock import patch, AsyncMock

from app.flows.coupon import CouponFlow
from app.schemas.intent import IntentResult, IntentType
from app.tools.tool_registry import init_tools, tool_registry
from app.database.repositories import CouponRepository


class CouponRepositoryTest(unittest.TestCase):
    def test_demo_coupons_for_user(self):
        coupons = CouponRepository().list_by_user("USRD13243F290A7")
        self.assertTrue(len(coupons) >= 1)
        self.assertIn("coupon_name", coupons[0])
        self.assertIn("coupon_status", coupons[0])

    def test_no_user_returns_empty(self):
        self.assertEqual(CouponRepository().list_by_user(""), [])


class CouponToolRegisteredTest(unittest.TestCase):
    def test_query_coupons_registered(self):
        if not tool_registry.get("query_coupons"):
            init_tools()
        self.assertIsNotNone(tool_registry.get("query_coupons"))


class CouponFlowRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_current_coupon_question_uses_real_coupon_tool(self):
        flow = CouponFlow()
        intent = IntentResult(
            intent=IntentType.COUPON_QUERY,
            confidence=0.92,
            raw_input="我现在有哪些优惠券可以用？\n\n[系统补充上下文]\n当前登录用户：USRD13243F290A7 / 小 / 13560569291",
        )
        with patch("app.flows.coupon.call_llm", new=AsyncMock(return_value="你当前有 2 张可用优惠券")):
            result = await flow.handle(intent, history=[], slots={"user_id": "USRD13243F290A7"})
        self.assertTrue(any(tc.get("tool_name") == "query_coupons" for tc in result.tool_calls))

    async def test_generic_coupon_question_stays_rules_prose(self):
        flow = CouponFlow()
        intent = IntentResult(
            intent=IntentType.COUPON_QUERY, confidence=0.92,
            raw_input="优惠券怎么用？有满减吗？",
        )
        with patch("app.flows.coupon.call_llm", new=AsyncMock(return_value="优惠券规则如下...")):
            result = await flow.handle(intent, history=[], slots=None)
        self.assertEqual(result.tool_calls, [])


if __name__ == "__main__":
    unittest.main()
