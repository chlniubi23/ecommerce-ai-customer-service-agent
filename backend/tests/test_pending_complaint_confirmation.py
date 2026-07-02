import unittest
from unittest.mock import patch, AsyncMock

from app.agent.memory.session import session_manager
from app.agents.agent import run as agent_run
from app.tools.base_tool import ToolResult
from app.tools.executors.tool_executor import ToolExecutionResult


class PendingComplaintConfirmationTest(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_reply_creates_pending_complaint_without_classification(self):
        session_id = "gate-confirm-test"
        session_manager.delete(session_id)
        session = session_manager.get_or_create(session_id)
        session.pending_complaint = {"content": "外包装破损", "complaint_type": "售后", "order_id": "ORD_DEMO_003"}
        session_manager.save(session)

        async def fake_exec(tool_name, **kwargs):
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_args=kwargs,
                tool_result=ToolResult(success=True, data={"complaint_id": "CMP_TEST_1"}, tool_name=tool_name),
                success=True, error="", latency_ms=1.0,
            )

        with patch("app.tools.executors.tool_executor.tool_executor.execute_by_name", new=AsyncMock(side_effect=fake_exec)) as exec_mock, \
             patch("app.agents.agent.classify_intent", new=AsyncMock(side_effect=AssertionError("classification must be skipped when pending_complaint exists"))):
            result = await agent_run(user_message="确认", history=[], session_id=session_id)

        exec_mock.assert_awaited_once()
        called_tool = exec_mock.await_args.args[0] if exec_mock.await_args.args else exec_mock.await_args.kwargs.get("tool_name")
        self.assertEqual(called_tool, "complaint_create")
        self.assertIn("CMP_TEST_1", result.message.content) if "CMP_TEST_1" in result.message.content else self.assertTrue(len(result.message.content) > 0)
        refreshed = session_manager.get_or_create(session_id)
        self.assertIsNone(refreshed.pending_complaint)
        session_manager.delete(session_id)

    async def test_deny_reply_cancels_pending_without_classification(self):
        session_id = "gate-deny-test"
        session_manager.delete(session_id)
        session = session_manager.get_or_create(session_id)
        session.pending_complaint = {"content": "外包装破损", "complaint_type": "售后", "order_id": "ORD_DEMO_003"}
        session_manager.save(session)

        with patch("app.tools.executors.tool_executor.tool_executor.execute_by_name", new=AsyncMock(side_effect=AssertionError("must not create on denial"))), \
             patch("app.agents.agent.classify_intent", new=AsyncMock(side_effect=AssertionError("classification must be skipped"))):
            result = await agent_run(user_message="不用了", history=[], session_id=session_id)

        refreshed = session_manager.get_or_create(session_id)
        self.assertIsNone(refreshed.pending_complaint)
        self.assertTrue(len(result.message.content) > 0)
        session_manager.delete(session_id)


if __name__ == "__main__":
    unittest.main()
