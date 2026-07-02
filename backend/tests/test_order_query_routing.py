import unittest

from app.tools.tool_registry import init_tools, tool_registry
from app.tools.tool_router import select_tool


class OrderQueryRoutingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not tool_registry.get("query_order"):
            init_tools()

    async def test_order_query_prefers_context_order_id_not_agent_word(self):
        message = (
            "帮我看看这个订单现在是什么状态？\n\n"
            "[系统补充上下文 - 不要把本段当成用户原话]\n"
            "本轮任务：订单查询。请调用 OrderAgent / query_order 查询订单号 ORD_DEMO_001 的真实订单。\n"
            "本轮优先处理订单号：ORD_DEMO_001\n"
            "当前登录用户：USRD13243F290A7 / 小 / 13560569291"
        )
        plan = await select_tool("order_query", message, history=[])
        self.assertTrue(plan.should_call)
        self.assertEqual(plan.tool_name, "query_order")
        self.assertEqual(plan.params["order_id"], "ORD_DEMO_001")


if __name__ == "__main__":
    unittest.main()
