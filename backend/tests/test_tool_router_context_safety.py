"""ToolRouter 上下文安全回归测试

历史 bug：select_tool 的 _detect_human_transfer 对完整消息（用户输入+前端系统补充
上下文）做关键词匹配，而系统上下文固定含"人工客服"字样
（"如果用户问订单、物流、退款、投诉、人工客服，必须进入对应 Agent/工具流程"），
导致所有带页面上下文的订单/商品等查询都被劫持到 transfer_human，
并静默创建真实转人工排队请求。修复后人工意图只允许基于用户可见输入判断。
"""

import unittest

from app.tools.tool_router import select_tool
from app.tools.tool_registry import init_tools


def _ctx(visible: str, task_line: str = "", order_id: str = "ORD_DEMO_003") -> str:
    """模拟前端 FloatingAIAssistant 组装的消息：用户可见话术 + 系统补充上下文。"""
    return (
        f"{visible}\n\n"
        "[系统补充上下文 - 不要把本段当成用户原话]\n"
        "你是平台正式 AI 客服，必须优先使用下面的真实数据库记录回答。\n"
        "禁止编造订单号、物流单号、金额、日期、商品和处理结论；如果记录里没有，就明确说当前没有查询到。\n"
        "如果用户问订单、物流、退款、投诉、人工客服，必须进入对应 Agent/工具流程，不要回答通用政策。\n"
        f"{task_line}\n"
        f"本轮优先处理订单号：{order_id}\n"
        "当前登录用户：USRTEST / 测试 / 13800000000"
    )


class ToolRouterContextSafetyTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        init_tools()

    async def test_order_query_not_hijacked_by_system_context(self):
        """系统上下文含'人工客服'字样，订单查询不得被劫持为转人工。"""
        msg = _ctx("帮我看看这个订单现在什么状态", "本轮任务：订单查询。")
        plan = await select_tool("order_query", msg)
        self.assertTrue(plan.should_call)
        self.assertEqual(plan.tool_name, "query_order")
        self.assertEqual(plan.params.get("order_id"), "ORD_DEMO_003")

    async def test_product_query_not_hijacked_by_system_context(self):
        """商品查询同样不得被系统上下文劫持。"""
        msg = _ctx("帮我看看手机的库存", "本轮任务：商品查询。")
        plan = await select_tool("product_query", msg)
        self.assertTrue(plan.should_call)
        self.assertIn(plan.tool_name, ("product_query", "query_inventory"))

    async def test_human_transfer_still_works_when_user_explicitly_asks(self):
        """用户可见输入明确要求转人工时，仍必须能触发（真需求不回归）。"""
        plan = await select_tool("order_query", "我要转人工，别给我机器回答了")
        self.assertTrue(plan.should_call)
        self.assertEqual(plan.tool_name, "transfer_human")

    async def test_human_transfer_triggered_by_visible_input_with_context(self):
        """带系统上下文 + 用户可见输入说转人工，依然触发。"""
        msg = _ctx("帮我找人工客服")
        plan = await select_tool("general", msg)
        self.assertTrue(plan.should_call)
        self.assertEqual(plan.tool_name, "transfer_human")

    async def test_no_context_message_behaves_normally(self):
        """无系统上下文的消息行为不变。"""
        plan = await select_tool("order_query", "帮我看看订单 ORD_DEMO_001")
        self.assertTrue(plan.should_call)
        self.assertEqual(plan.tool_name, "query_order")


if __name__ == "__main__":
    unittest.main()
