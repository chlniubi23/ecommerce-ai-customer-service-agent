import unittest
from unittest.mock import patch, AsyncMock

from app.agents import classifier
from app.agents.classifier import _classify_business_intent_by_rule, classify_intent
from app.schemas.intent import IntentType
from app.tools.tool_router import _extract_order_id


def _ctx(visible: str, task_line: str, order_id: str = "ORD_DEMO_003") -> str:
    return (
        f"{visible}\n\n"
        "[系统补充上下文 - 不要把本段当成用户原话]\n"
        "你是平台正式 AI 客服，必须优先使用下面的真实数据库记录回答。\n"
        f"{task_line}\n"
        f"本轮优先处理订单号：{order_id}\n"
        "当前登录用户：USRTEST / 测试 / 13800000000"
    )


class RoutingPreservesContextTest(unittest.TestCase):
    """前端把订单号和'本轮任务'写在系统上下文里，路由和取参不能因剥离而失效。"""

    def test_logistics_task_routes_even_in_system_context(self):
        msg = _ctx("我的物流到哪了？", "本轮任务：物流查询。请调用 LogisticsAgent 查询 ORD_DEMO_003 的真实物流。")
        self.assertEqual(_classify_business_intent_by_rule(msg), IntentType.LOGISTICS_QUERY)

    def test_order_task_routes_even_in_system_context(self):
        msg = _ctx("帮我看看订单", "本轮任务：订单查询。请调用 OrderAgent 查询 ORD_DEMO_003 的真实订单。")
        self.assertEqual(_classify_business_intent_by_rule(msg), IntentType.ORDER_QUERY)

    def test_refund_task_routes_even_in_system_context(self):
        msg = _ctx("我要退款", "本轮任务：退款/售后。请调用 RefundAgent 处理 ORD_DEMO_003。")
        self.assertEqual(_classify_business_intent_by_rule(msg), IntentType.REFUND)

    def test_complaint_task_context_alone_does_not_route_to_ticket(self):
        # 仅上下文里有'投诉/升级'指令、用户没明确要创建 → 不能进 TICKET（否则又会误建）
        msg = _ctx("帮我总结当前订单和投诉情况", "本轮任务：投诉/升级。请调用 ComplaintAgent 关联 ORD_DEMO_003。")
        self.assertIsNone(_classify_business_intent_by_rule(msg))


class RawInputPreservesOrderIdTest(unittest.IsolatedAsyncioTestCase):
    async def test_logistics_raw_input_keeps_order_id_for_tools(self):
        msg = _ctx("我的物流到哪了？", "本轮任务：物流查询。请调用 LogisticsAgent 查询 ORD_DEMO_003。")
        # 不应触达 LLM（规则命中即返回）；为安全起见仍 mock 掉网络
        with patch.object(classifier.client.chat.completions, "create", new=AsyncMock(side_effect=AssertionError("should not call LLM"))):
            result = await classify_intent(msg)
        self.assertEqual(result.intent, IntentType.LOGISTICS_QUERY)
        self.assertEqual(_extract_order_id(result.raw_input), "ORD_DEMO_003")


if __name__ == "__main__":
    unittest.main()
