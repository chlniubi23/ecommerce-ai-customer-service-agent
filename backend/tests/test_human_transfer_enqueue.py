"""转人工"真入队"测试。

核心诉求（区分 Chatbot vs Agent）：转人工不是"读一下排队数就说成功"，
而是真正把用户加入人工队列——写一条 human_transfer_requests 记录，
并让队列人数真实 +1，返回给用户的排队位次基于真实队列。
"""

import unittest
from unittest.mock import patch, AsyncMock

from app.database.repositories import (
    HumanAgentStatusRepository,
    HumanTransferRepository,
)
from app.flows.human_transfer import HumanTransferFlow
from app.schemas.intent import IntentResult, IntentType
from app.tools.tool_registry import init_tools, tool_registry


class HumanTransferRepositoryTest(unittest.TestCase):
    def test_create_transfer_request_persists_and_bumps_queue(self):
        repo = HumanTransferRepository()
        status_repo = HumanAgentStatusRepository()

        before = status_repo.get_status("general_service")
        self.assertIsNotNone(before, "需要 general_service 队列种子数据")
        before_count = before["queue_count"]

        record = repo.create_transfer_request(
            team_name="general_service",
            reason="用户要求人工核实退款进度",
            user_id="USRD13243F290A7",
            session_id="test-session-1",
        )

        self.assertEqual(record["transfer_status"], "queued")
        self.assertEqual(record["queue_position"], before_count + 1)
        self.assertTrue(record["transfer_id"].startswith("HTR"))

        after = status_repo.get_status("general_service")
        self.assertEqual(after["queue_count"], before_count + 1)

        # 该记录能被真实读回（证明落库，不是内存）
        reloaded = repo.get_by_id(record["transfer_id"])
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["reason"], "用户要求人工核实退款进度")


class HumanTransferFlowRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_flow_actually_enqueues(self):
        if not tool_registry.get("transfer_human"):
            init_tools()
        flow = HumanTransferFlow()
        intent = IntentResult(
            intent=IntentType.HUMAN_TRANSFER,
            confidence=0.95,
            raw_input="我要转人工",
        )
        with patch("app.flows.human_transfer.call_llm", new=AsyncMock(return_value="已为您转接人工，正在排队")):
            result = await flow.handle(intent, history=[], slots=None)

        transfer_calls = [tc for tc in result.tool_calls if tc.get("tool_name") == "transfer_human"]
        self.assertTrue(transfer_calls, "必须调用 transfer_human 工具")
        output = transfer_calls[0].get("tool_output", {})
        self.assertTrue(transfer_calls[0].get("success"))
        # 真入队后应返回真实的 transfer_id 与排队位次
        self.assertIn("transfer_id", output)
        self.assertIn("queue_position", output)


if __name__ == "__main__":
    unittest.main()
