import unittest

from app.tools.tool_router import _extract_order_id


class OrderIdExtractionTest(unittest.TestCase):
    def test_prefers_explicit_ord_id_over_phone_number(self):
        text = "我的物流到哪里了？\n\n[系统补充上下文 - 不要把本段当成用户原话]\n本轮优先处理订单号：ORD_DEMO_001\n当前登录用户：USRTEST / 测试用户 / 13560569291"
        self.assertEqual(_extract_order_id(text), "ORD_DEMO_001")

    def test_does_not_treat_phone_number_as_order_id_when_no_order_marker(self):
        text = "当前登录用户：USRTEST / 测试用户 / 13560569291"
        self.assertIsNone(_extract_order_id(text))

    def test_keeps_numeric_order_id_when_explicitly_labeled(self):
        text = "订单号：13560569291，帮我查物流"
        self.assertEqual(_extract_order_id(text), "13560569291")

    def test_does_not_capture_agent_or_english_words_as_order_id(self):
        text = "本轮任务：订单查询。请调用 OrderAgent / query_order 处理。I ordered yesterday, Ordinary1234"
        self.assertIsNone(_extract_order_id(text))

    def test_does_not_treat_number_after_bare_dingdan_and_space_as_order_id(self):
        text = "订单 13560569291 什么时候到"
        self.assertIsNone(_extract_order_id(text))

    def test_does_not_capture_user_id_after_bare_dingdan_newline(self):
        text = "帮我看看这个订单\nUSRD13243F290A7 / 小"
        self.assertIsNone(_extract_order_id(text))

    def test_extracts_ord_id_adjacent_to_dingdan(self):
        text = "这个订单ORD_DEMO_001怎么还没发货"
        self.assertEqual(_extract_order_id(text), "ORD_DEMO_001")


if __name__ == "__main__":
    unittest.main()
