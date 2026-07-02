import unittest
from app.agents.classifier import _classify_business_intent_by_rule
from app.schemas.intent import IntentType


class CouponRoutingRuleTest(unittest.TestCase):
    def test_current_coupon_question_routes_to_coupon_query(self):
        msg = ("我现在有哪些优惠券可以用？\n\n[系统补充上下文]\n当前登录用户：USRD13243F290A7 / 小 / 13560569291")
        self.assertEqual(_classify_business_intent_by_rule(msg), IntentType.COUPON_QUERY)

    def test_my_coupons_routes_to_coupon_query(self):
        self.assertEqual(_classify_business_intent_by_rule("我的优惠券"), IntentType.COUPON_QUERY)

    def test_generic_coupon_rule_question_not_business_routed(self):
        # generic "how do coupons work" must NOT be forced to coupon_query here;
        # it should fall through (None) so knowledge/LLM handles the rules explanation
        self.assertIsNone(_classify_business_intent_by_rule("优惠券怎么用？满减怎么算？"))


class CouponClassifyIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_generic_coupon_not_hijacked_to_coupon_query(self):
        # generic "优惠券怎么用？满减怎么算？" does NOT match either deterministic rule
        # (no current-coupon hint, and knowledge question-terms don't cover "怎么用"/"满减"),
        # so it falls through to the LLM. The regression we lock: the new business rule
        # must NOT hijack it to COUPON_QUERY — with the LLM stubbed to knowledge, we get knowledge.
        from app.agents.classifier import classify_intent
        from unittest.mock import patch, AsyncMock, MagicMock
        fake = MagicMock()
        fake.choices = [MagicMock()]
        fake.choices[0].message.content = '{"intent": "knowledge_query", "confidence": 0.9}'
        with patch("app.agents.classifier.client.chat.completions.create", new=AsyncMock(return_value=fake)) as mock_create:
            result = await classify_intent("优惠券怎么用？满减怎么算？")
        self.assertEqual(result.intent, IntentType.KNOWLEDGE_QUERY)
        # sanity: it truly went through the LLM path, i.e. rules returned None (not coupon_query)
        mock_create.assert_awaited_once()

    async def test_current_coupon_routes_coupon_query_end_to_end(self):
        from app.agents.classifier import classify_intent
        from unittest.mock import patch, AsyncMock
        with patch("app.agents.classifier.client.chat.completions.create", new=AsyncMock(side_effect=AssertionError("LLM should not be called"))):
            result = await classify_intent("我现在有哪些优惠券可以用？")
        self.assertEqual(result.intent, IntentType.COUPON_QUERY)
