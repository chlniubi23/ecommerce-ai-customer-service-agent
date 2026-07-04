"""投诉跟进请求路由测试：跟进必须走 TICKET（读真实投诉记录），绝不走知识库。

同时守护安全属性"AI 绝不静默建单"：TicketFlow 内不允许存在任何写库路径。
"""

import unittest
from unittest.mock import AsyncMock, patch

from app.agents.classifier import classify_intent
from app.agents.complaint_intent import extract_complaint_id
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

    async def test_followup_without_space_before_ref_routes_to_ticket(self):
        # 编号紧贴中文时 \b 边界不成立，曾导致再次落入知识库
        result = await classify_intent("帮我跟进投诉工单CMP_DEMO_D01的进度")
        self.assertEqual(result.intent, IntentType.TICKET)

    def test_extract_complaint_id_glued_to_chinese(self):
        self.assertEqual(
            extract_complaint_id("帮我跟进投诉工单CMP_DEMO_D01的进度"),
            "CMP_DEMO_D01",
        )
        self.assertEqual(
            extract_complaint_id("跟进工单 TKT123ABC 的状态"),
            "TKT123ABC",
        )


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
        # create=True：select_tool 已从 ticket.py 移除；若有人重新引入并调用，
        # 这里立刻捕获（守护"绝不静默建单"）。
        with patch("app.flows.ticket.ComplaintRepository") as repo_cls, \
             patch("app.flows.ticket.call_llm", new=AsyncMock(return_value="ok")), \
             patch("app.flows.ticket.select_tool", create=True) as select_tool_mock:
            repo_cls.return_value.get_by_any_id.return_value = None
            repo_cls.return_value.get_latest_by_order_id.return_value = None
            result = await flow.handle(intent, history=[])
        select_tool_mock.assert_not_called()
        self.assertIn("没有查到", result.message.content)

    async def test_followup_by_order_id_when_no_complaint_ref(self):
        """用户说"这个订单我投诉过了想看进展"（无编号）+ 上下文带订单号：
        按订单号查最近一条投诉，读真实记录，绝不新建。"""
        flow = TicketFlow()
        intent = IntentResult(
            intent=IntentType.TICKET,
            confidence=0.92,
            raw_input=(
                "这个订单我已经投诉了，我想知道最新处理进展\n\n"
                "[系统补充上下文 - 不要把本段当成用户原话]\n"
                "本轮优先处理订单号：ORD_DEMO_003"
            ),
        )
        with patch("app.flows.ticket.ComplaintRepository") as repo_cls, \
             patch("app.flows.ticket.call_llm", new=AsyncMock(return_value="投诉处理中")):
            repo_cls.return_value.get_by_any_id.return_value = None
            repo_cls.return_value.get_latest_by_order_id.return_value = {
                "complaint_id": "CMP_DEMO_001",
                "complaint_status": "已升级",
                "priority": "紧急",
                "process_records": [],
                "escalations": [],
            }
            result = await flow.handle(intent, history=[])
        repo_cls.return_value.get_latest_by_order_id.assert_called_once_with("ORD_DEMO_003")
        self.assertTrue(any(tc.get("tool_name") == "complaint_lookup" for tc in result.tool_calls))

    async def test_unconfirmed_ticket_intent_never_creates(self):
        """LLM 把模糊抱怨路由到 ticket 时（非跟进、非明确创建），绝不建单。"""
        flow = TicketFlow()
        intent = IntentResult(
            intent=IntentType.TICKET,
            confidence=0.7,
            raw_input="客服态度太差了，必须给我个说法",
        )
        with patch("app.flows.ticket.select_tool", create=True) as select_tool_mock, \
             patch("app.flows.ticket.call_llm", new=AsyncMock(return_value="ok")), \
             patch("app.flows.ticket.ComplaintRepository") as repo_cls:
            result = await flow.handle(intent, history=[])
        select_tool_mock.assert_not_called()
        repo_cls.return_value.get_by_any_id.assert_not_called()
        self.assertEqual(result.tool_calls, [])
        # 回复不得声称已创建工单
        self.assertNotIn("TKT", result.message.content)
        self.assertNotIn("工单号已", result.message.content)
        self.assertNotIn("已为你创建", result.message.content)
        self.assertNotIn("已创建", result.message.content)


if __name__ == "__main__":
    unittest.main()
