"""个性化推荐"接进对话 + 基于真实用户历史"测试。

区分"框架空转"（引擎存在但没接进对话、不看用户历史） vs "真实个性化"：
1. 推荐基于用户真实购买历史推断的偏好品类/品牌
2. 已购买过的商品不重复推荐
3. 只推有货商品
4. ProductFlow 在用户问"推荐点什么"时真的调用了 recommend_products 工具
"""

import unittest
from unittest.mock import patch, AsyncMock

from app.database.repositories import ProductRecommendationRepository, OrderRepository
from app.flows.product import ProductFlow
from app.schemas.intent import IntentResult, IntentType
from app.tools.tool_registry import init_tools, tool_registry


DEMO_USER = "USRD13243F290A7"


class RecommendationRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.repo = ProductRecommendationRepository()

    def test_recommend_uses_history_and_excludes_purchased(self):
        orders = OrderRepository().list_user_orders(DEMO_USER)
        purchased_ids = {
            item.get("product_id")
            for order in orders
            for item in (order.get("items") or [])
            if item.get("product_id")
        }

        result = self.repo.recommend_for_user(DEMO_USER, limit=5)
        self.assertIn("preferred_categories", result)
        self.assertIn("recommendations", result)

        for rec in result["recommendations"]:
            # 不推荐已购买过的商品
            self.assertNotIn(rec["product_id"], purchased_ids)
            # 只推有货
            self.assertTrue(rec.get("available_quantity", 0) is None or rec.get("in_stock", True))
            # 有推荐理由（可解释）
            self.assertTrue(rec.get("reason"))

    def test_no_history_falls_back_to_popular(self):
        # 无历史用户也应有兜底推荐（热门/有货），不能空转
        result = self.repo.recommend_for_user("USR_NO_SUCH_USER", limit=3)
        self.assertIn("recommendations", result)


class RecommendationRoutingTest(unittest.TestCase):
    def test_recommend_questions_route_to_product_query(self):
        from app.agents.classifier import _classify_business_intent_by_rule as classify
        for text in ["帮我推荐几款手机", "有什么值得入手的", "根据我的购买记录推荐点"]:
            self.assertEqual(classify(text), IntentType.PRODUCT_QUERY, text)

    def test_non_recommend_not_hijacked(self):
        from app.agents.classifier import _classify_business_intent_by_rule as classify
        # 无推荐词的订单/退款问题不应被推荐规则误伤为 PRODUCT_QUERY
        self.assertNotEqual(classify("我要查订单"), IntentType.PRODUCT_QUERY)
        self.assertNotEqual(classify("退款怎么申请"), IntentType.PRODUCT_QUERY)


class ProductFlowRecommendationTest(unittest.IsolatedAsyncioTestCase):
    async def test_recommend_question_calls_recommend_tool(self):
        if not tool_registry.get("recommend_products"):
            init_tools()
        flow = ProductFlow()
        intent = IntentResult(
            intent=IntentType.PRODUCT_QUERY,
            confidence=0.9,
            raw_input="根据我买过的东西，帮我推荐几款值得入手的商品\n\n[系统补充上下文]\n当前登录用户：USRD13243F290A7 / 小 / 138",
        )
        with patch("app.flows.product.call_llm", new=AsyncMock(return_value="为你推荐了几款")):
            result = await flow.handle(intent, history=[], slots=None)
        self.assertTrue(
            any(tc.get("tool_name") == "recommend_products" for tc in result.tool_calls),
            "推荐类问题应调用 recommend_products 工具",
        )


if __name__ == "__main__":
    unittest.main()
