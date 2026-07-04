import unittest
from unittest.mock import patch

from app.agents import coordinator
from app.tools.base_tool import ToolResult
from app.tools.executors.tool_executor import ToolExecutionResult


FRONTEND_CONTEXT = """你好

[系统补充上下文 - 不要把本段当成用户原话]
你是平台正式 AI 客服，必须优先使用下面的真实数据库记录回答。
如果用户问订单、物流、退款、投诉、人工客服，必须进入对应 Agent/工具流程，不要回答通用政策。
本轮优先处理订单号：ORD_DEMO_003
当前登录用户：USR_TEST / 测试用户 / 13800000000
回答要求：直接给结论和下一步操作；涉及售后、投诉、人工客服时说明当前系统记录和可执行动作。
"""


class CoordinatorSafetyTest(unittest.IsolatedAsyncioTestCase):
    def test_detect_multi_intent_ignores_frontend_system_context(self):
        self.assertEqual(coordinator.detect_multi_intent(FRONTEND_CONTEXT), [])
        self.assertFalse(coordinator.should_coordinate(FRONTEND_CONTEXT))

    async def test_summary_request_does_not_create_complaint_record(self):
        user_input = """帮我总结当前订单、物流、退款和投诉情况。

[系统补充上下文 - 不要把本段当成用户原话]
本轮优先处理订单号：ORD_DEMO_003
当前登录用户：USR_TEST / 测试用户 / 13800000000
如果用户问订单、物流、退款、投诉、人工客服，必须进入对应 Agent/工具流程。
"""
        called_tools: list[str] = []

        async def fake_execute_by_name(tool_name: str, **kwargs):
            called_tools.append(tool_name)
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_args=kwargs,
                tool_result=ToolResult(success=True, data={"tool": tool_name}, tool_name=tool_name),
                success=True,
                error="",
                latency_ms=1.0,
            )

        async def fake_call_llm(*args, **kwargs):
            return "已汇总当前服务情况。"

        with patch.object(coordinator.tool_executor, "execute_by_name", side_effect=fake_execute_by_name), patch.object(coordinator, "call_llm", side_effect=fake_call_llm):
            await coordinator.coordinate(
                user_input,
                history=[],
                domains=["order", "logistics", "refund", "complaint"],
            )

        self.assertNotIn("complaint_create", called_tools)

    async def test_coordinator_never_creates_complaint_directly(self):
        """即使用户在多域请求里明确要投诉，协调器也不直接写库，
        而是交给对话确认闸门，避免静默建单。"""
        user_input = "我要提交投诉，订单 ORD_DEMO_003 外包装破损，需要客服处理"
        called_tools: list[str] = []

        async def fake_execute_by_name(tool_name: str, **kwargs):
            called_tools.append(tool_name)
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_args=kwargs,
                tool_result=ToolResult(success=True, data={"tool": tool_name}, tool_name=tool_name),
                success=True,
                error="",
                latency_ms=1.0,
            )

        async def fake_call_llm(*args, **kwargs):
            return "已了解你的投诉诉求。"

        with patch.object(coordinator.tool_executor, "execute_by_name", side_effect=fake_execute_by_name), patch.object(coordinator, "call_llm", side_effect=fake_call_llm):
            await coordinator.coordinate(
                user_input,
                history=[],
                domains=["order", "complaint"],
            )

        self.assertNotIn("complaint_create", called_tools)

    async def test_already_complained_reads_real_record_not_ask_submit(self):
        """"这个订单我已经投诉了，想知道进展"：协调器应读真实投诉记录，
        绝不再要求用户"确认提交投诉"（复现并守护该 bug）。"""
        user_input = (
            "这个订单我已经投诉了，我想知道最新处理进展\n\n"
            "[系统补充上下文 - 不要把本段当成用户原话]\n"
            "本轮优先处理订单号：ORD_DEMO_003"
        )

        async def fake_execute_by_name(tool_name: str, **kwargs):
            return ToolExecutionResult(
                tool_name=tool_name, tool_args=kwargs,
                tool_result=ToolResult(success=True, data={"tool": tool_name}, tool_name=tool_name),
                success=True, error="", latency_ms=1.0,
            )

        async def fake_call_llm(*args, **kwargs):
            return "你的投诉正在处理中。"

        with patch.object(coordinator.tool_executor, "execute_by_name", side_effect=fake_execute_by_name), \
             patch.object(coordinator, "call_llm", side_effect=fake_call_llm), \
             patch.object(coordinator, "ComplaintRepository") as repo_cls:
            repo_cls.return_value.get_latest_by_order_id.return_value = {
                "complaint_id": "CMP_DEMO_001", "complaint_status": "已升级", "priority": "紧急",
            }
            result = await coordinator.coordinate(user_input, history=[], domains=["order", "complaint"])

        repo_cls.return_value.get_latest_by_order_id.assert_called_once_with("ORD_DEMO_003")
        self.assertTrue(any(tc.get("tool_name") == "complaint_lookup" for tc in result.tool_calls))
        # 综合上下文里必须带上真实记录、且不再要求"确认提交投诉"
        self.assertNotIn("complaint_create", [tc.get("tool_name") for tc in result.tool_calls])


if __name__ == "__main__":
    unittest.main()
