"""主动服务"事件驱动"测试。

区分"进店看板"(每次重算快照) vs "主动服务"(业务状态变化 → 落一条事件，
带去重与未读状态)。核心诉求：
1. 业务动作发生时能 emit 一条持久化事件（事件驱动）
2. 同一情形重复扫描不会刷屏（dedup_key 去重）
3. 事件有未读/已读状态，用户看过可标记，不会反复打扰
4. 时间类条件（物流迟滞/优惠券将过期）能被扫描感知并生成事件
"""

import unittest

from app.database.repositories import ProactiveEventRepository


class ProactiveEventRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.repo = ProactiveEventRepository()
        self.user_id = "USRD13243F290A7"

    def test_emit_persists_unread_event(self):
        event = self.repo.emit(
            user_id=self.user_id,
            event_type="refund_pending_detected",
            severity="high",
            title="退款进入审核",
            description="订单 ORD_TEST 的退款已提交，预计 3 个工作日。",
            action_prompt="帮我跟进订单 ORD_TEST 的退款进度",
            dedup_key="refund_pending:ORD_TEST_EVENT",
        )
        self.assertEqual(event["event_status"], "unread")
        self.assertTrue(event["event_id"].startswith("PEV"))

        reloaded = self.repo.get_by_id(event["event_id"])
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["title"], "退款进入审核")

    def test_emit_is_deduped(self):
        key = "dedup_test:ORD_SAME"
        first = self.repo.emit(
            user_id=self.user_id, event_type="order_attention_detected",
            severity="low", title="首次", description="d", action_prompt="p", dedup_key=key,
        )
        second = self.repo.emit(
            user_id=self.user_id, event_type="order_attention_detected",
            severity="low", title="重复扫描", description="d2", action_prompt="p", dedup_key=key,
        )
        # 同 dedup_key 只应存在一条（同一事件不刷屏）
        self.assertEqual(first["event_id"], second["event_id"])

    def test_mark_read_removes_from_unread(self):
        event = self.repo.emit(
            user_id=self.user_id, event_type="complaint_followup_detected",
            severity="high", title="工单待处理", description="d", action_prompt="p",
            dedup_key="unread_flow:CMP_TEST",
        )
        self.repo.mark_read(event["event_id"])
        unread_ids = [e["event_id"] for e in self.repo.list_for_user(self.user_id, statuses=("unread",))]
        self.assertNotIn(event["event_id"], unread_ids)


class ProactiveEmitHelperTest(unittest.TestCase):
    def test_helper_skips_when_no_user(self):
        from app.services.proactive import emit_proactive_event
        # 无 user_id 时静默跳过，不抛异常（不能拖累主流程）
        self.assertIsNone(
            emit_proactive_event(
                user_id=None, event_type="x", severity="low",
                title="t", description="d", action_prompt="p", dedup_key="k",
            )
        )


if __name__ == "__main__":
    unittest.main()
