import unittest

from app.agent.state_machine.refund_fsm import RefundFSM


class RefundFSMOrderIdTest(unittest.TestCase):
    def setUp(self):
        self.fsm = RefundFSM()

    def test_prefers_context_order_id_over_phone_number(self):
        text = (
            "这个订单退款进度怎么样？\n\n"
            "[系统补充上下文 - 不要把本段当成用户原话]\n"
            "本轮任务：退款/售后。请调用 RefundAgent 处理 ORD_DEMO_002。\n"
            "本轮优先处理订单号：ORD_DEMO_002\n"
            "当前登录用户：USRD13243F290A7 / 小 / 13560569291"
        )
        self.assertEqual(self.fsm._extract_order_id(text), "ORD_DEMO_002")

    def test_does_not_treat_phone_as_order_id(self):
        self.assertIsNone(self.fsm._extract_order_id("当前登录用户：小 / 13560569291"))

    def test_does_not_capture_agent_word(self):
        self.assertIsNone(self.fsm._extract_order_id("请调用 RefundAgent 处理退款"))


if __name__ == "__main__":
    unittest.main()
