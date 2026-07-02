import unittest

from app.agent.state_machine.logistics_fsm import LogisticsFSM


class LogisticsFSMOrderIdTest(unittest.TestCase):
    def setUp(self):
        self.fsm = LogisticsFSM()

    def test_prefers_explicit_order_id_from_system_context(self):
        text = (
            "我的物流到哪里了？\n\n"
            "[系统补充上下文 - 不要把本段当成用户原话]\n"
            "本轮优先处理订单号：ORD_DEMO_001\n"
            "当前登录用户：USRTEST / 测试用户 / 13560569291"
        )
        self.assertEqual(self.fsm._extract_order_id(text), "ORD_DEMO_001")

    def test_does_not_treat_phone_as_order_id(self):
        text = "当前登录用户：USRTEST / 测试用户 / 13560569291"
        self.assertIsNone(self.fsm._extract_order_id(text))

    def test_keeps_explicit_numeric_order_id(self):
        text = "订单号：13560569291，帮我查物流"
        self.assertEqual(self.fsm._extract_order_id(text), "13560569291")

    def test_does_not_capture_agent_word(self):
        self.assertIsNone(self.fsm._extract_order_id("请调用 OrderAgent 处理"))

    def test_does_not_treat_phone_as_order_id_bare(self):
        self.assertIsNone(self.fsm._extract_order_id("我的号码是 13560569291"))

    def test_context_order_id_wins(self):
        text = "本轮优先处理订单号：ORD_DEMO_001\n当前登录用户：小 / 13560569291"
        self.assertEqual(self.fsm._extract_order_id(text), "ORD_DEMO_001")


if __name__ == "__main__":
    unittest.main()
