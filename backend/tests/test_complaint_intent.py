import unittest

from app.agents import complaint_intent as ci


class ComplaintIntentTest(unittest.TestCase):
    # ----- explicit create requests -----
    def test_explicit_create_phrases_are_detected(self):
        for text in [
            "我要投诉这个订单",
            "帮我创建一个投诉",
            "我想提交投诉，订单 ORD_DEMO_003 外包装破损",
            "帮我发起投诉工单",
            "给我新建一条客诉",
        ]:
            self.assertTrue(ci.is_explicit_create_request(text), text)

    # ----- query / follow-up must NOT be treated as create -----
    def test_query_and_followup_are_not_create(self):
        for text in [
            "帮我跟进投诉工单 CMP_DEMO_D01，说明当前处理进度和是否需要升级",
            "查询我的投诉记录",
            "我的投诉处理到哪了",
            "总结当前订单、物流、退款和投诉情况",
            "看看投诉进度",
            "投诉情况怎么样了",
            # 过去完成 + 想查进度：语义上不可能是"新建投诉"，绝不能判成 create
            "这个订单我已经投诉了，我想知道最新处理进展",
            "我之前投诉过这个订单，现在处理得怎么样",
            "我投诉过了，帮我看看进展",
        ]:
            self.assertFalse(ci.is_explicit_create_request(text), text)

    # ----- 已表明存在投诉 + 查询意图 → 跟进（只读），即使没带编号 -----
    def test_already_complained_progress_is_followup(self):
        for text in [
            "这个订单我已经投诉了，我想知道最新处理进展",
            "我之前投诉过这个订单，现在处理得怎么样",
            "我投诉过了，帮我看看进展",
        ]:
            self.assertTrue(ci.is_followup_request(text), text)

    # ----- confirmation -----
    def test_confirmation_phrases(self):
        for text in ["确认", "确认提交", "是的，提交吧", "可以", "好的就这样", "提交"]:
            self.assertTrue(ci.is_confirmation(text), text)

    def test_non_confirmation(self):
        for text in ["不用了", "先不要", "算了", "我再想想", "帮我查物流"]:
            self.assertFalse(ci.is_confirmation(text), text)

    # ----- denial -----
    def test_denial_phrases(self):
        for text in ["不用了", "先不要", "算了", "取消", "再想想"]:
            self.assertTrue(ci.is_denial(text), text)

    def test_non_denial(self):
        for text in ["确认提交", "可以", "是的"]:
            self.assertFalse(ci.is_denial(text), text)


class ComplaintGateTest(unittest.TestCase):
    """会话级确认闸门：AI 创建投诉前必须先经用户确认。"""

    def test_no_pending_explicit_create_asks_for_confirmation(self):
        self.assertEqual(
            ci.resolve_complaint_gate(has_pending=False, user_input="我要投诉订单 ORD_DEMO_003"),
            "ask_confirm",
        )

    def test_no_pending_query_does_nothing(self):
        self.assertEqual(
            ci.resolve_complaint_gate(has_pending=False, user_input="帮我跟进投诉工单 CMP_DEMO_D01"),
            "none",
        )

    def test_pending_confirmation_creates(self):
        self.assertEqual(
            ci.resolve_complaint_gate(has_pending=True, user_input="确认提交"),
            "create",
        )

    def test_pending_denial_cancels(self):
        self.assertEqual(
            ci.resolve_complaint_gate(has_pending=True, user_input="不用了"),
            "cancel",
        )

    def test_pending_unclear_reasks(self):
        self.assertEqual(
            ci.resolve_complaint_gate(has_pending=True, user_input="这个订单到底怎么回事"),
            "ask_again",
        )


if __name__ == "__main__":
    unittest.main()
