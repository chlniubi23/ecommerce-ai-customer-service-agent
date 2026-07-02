"""投诉跟进请求路由测试：跟进必须走 TICKET（读真实投诉记录），绝不走知识库。"""

import unittest
from unittest.mock import AsyncMock, patch

from app.agents.classifier import classify_intent
from app.flows.ticket import TicketFlow
from app.schemas.intent import IntentResult, IntentType


class ComplaintFollowupRoutingTest(unittest.IsolatedAsyncioTestCase):
    async def test_followup_ticket_request_routes_to_ticket_not_knowledge(self):
        message = (
            "帮我跟进投诉工单 CMP_DEMO_D01，说明当前处理进度和是否需要升级\n\n"
            "[系统补充上下文 - 不要把本段当成用户原话]\n"
            "本轮优先处理订单号：ORD_DEMO_003\n"
            "当前登录用户：USRD13243F290A7 / 小 / 13560569291"
        )
        result = await classify_intent(message)
        self.assertEqual(result.intent, IntentType.TICKET)


class ComplaintFollowupFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_followup_ticket_flow_reads_real_complaint(self):
        flow = TicketFlow()
        intent = IntentResult(
            intent=IntentType.TICKET,
            confidence=0.92,
            raw_input="帮我跟进投诉工单 CMP_DEMO_D01，说明当前处理进度",
        )
        with patch("app.flows.ticket.ComplaintRepository") as repo_cls, \
             patch(
                 "app.flows.ticket.call_llm",
                 new=AsyncMock(return_value="当前投诉已升级到主管处理，建议等待处理结果"),
             ):
            repo_cls.return_value.get_by_any_id.return_value = {
                "complaint_id": "CMP_DEMO_D01",
                "complaint_status": "已升级",
                "priority": "紧急",
                "process_records": [],
                "escalations": [],
            }
            result = await flow.handle(intent, history=[])
        repo_cls.return_value.get_by_any_id.assert_called_once_with("CMP_DEMO_D01")
        self.assertIn("已升级", result.message.content)

    async def test_followup_never_creates_complaint(self):
        flow = TicketFlow()
        intent = IntentResult(
            intent=IntentType.TICKET,
            confidence=0.92,
            raw_input="帮我跟进投诉工单 CMP_DEMO_D01 的进度",
        )
        with patch("app.flows.ticket.ComplaintRepository") as repo_cls, \
             patch("app.flows.ticket.call_llm", new=AsyncMock(return_value="ok")), \
             patch("app.flows.ticket.select_tool") as select_tool_mock:
            repo_cls.return_value.get_by_any_id.return_value = None
            result = await flow.handle(intent, history=[])
        select_tool_mock.assert_not_called()
        self.assertIn("没有查到", result.message.content)


if __name__ == "__main__":
    unittest.main()
