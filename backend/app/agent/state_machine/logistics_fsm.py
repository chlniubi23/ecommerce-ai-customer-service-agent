"""
LogisticsFSM - 物流查询流程状态机

状态流转：
  START → WAIT_ORDER_ID → PROCESSING → DONE

必填 Slots：
  - order_id: 订单号

示例对话：
  用户: "我的快递到哪了"
  AI: "请提供您的订单号"          → WAIT_ORDER_ID
  用户: "123456"
  [调用 LogisticsTool] → PROCESSING → DONE
"""

import re
import logging
from typing import Any
from app.agent.state_machine.base_fsm import BaseFSM, SlotDefinition

logger = logging.getLogger(__name__)


class LogisticsFSM(BaseFSM):
    """物流查询流程状态机"""

    @property
    def flow_name(self) -> str:
        return "logistics_query"

    @property
    def slot_definitions(self) -> list[SlotDefinition]:
        return [
            SlotDefinition(
                name="order_id",
                description="订单号",
                required=True,
                prompt="好的，我帮您查物流。请问订单号是多少？",
                state="WAIT_ORDER_ID",
            ),
        ]

    @property
    def initial_state(self) -> str:
        return "START"

    @property
    def terminal_state(self) -> str:
        return "DONE"

    def _extract_slot_value(self, slot_name: str, user_input: str) -> Any | None:
        """从用户输入中提取 Slot 值（用于 get_initial_result 的批量提取）"""
        if slot_name == "order_id":
            return self._extract_order_id(user_input)
        return None

    def _extract_slot_value_waiting(self, slot_name: str, user_input: str) -> Any | None:
        """当 FSM 正在等待某个 Slot 时的提取逻辑（更宽松）"""
        if slot_name == "order_id":
            result = self._extract_order_id(user_input)
            if result:
                return result
            # 正在等订单号时，整段输入就是一个短编号（如用户直接回复 "123456"）
            stripped = user_input.strip()
            if re.match(r'^[A-Za-z0-9_\-]{4,40}$', stripped):
                return stripped
            return None
        return None

    def _extract_order_id(self, text: str) -> str | None:
        """提取订单号。

        优先级（与 tools/tool_router.py 及 refund_fsm.py 的 _extract_order_id 保持一致）：
        1. 系统上下文标注的"本轮优先处理订单号"
        2. 明确标注的订单号（订单号: xxx / order id: xxx，需显式"号"或 id 标记；
           "订单ORD_xxx" 紧邻写法也接受）
        3. 形如 ORD_xxx 的业务订单号（仅大写 ORD 前缀，避免 OrderAgent/ordered
           这类英文单词里的子串误触发）
        4. 不把任意裸数字当订单号，避免手机号误入
        """
        explicit_patterns: list[tuple[str, int]] = [
            (r'本轮优先处理订单号[：:\s]*([A-Za-z0-9_\-]{4,40})', 0),
            (r'订单号[：:\s]*([A-Za-z0-9_\-]{4,40})', 0),
            (r'订单(ORD[A-Za-z0-9_\-]{4,40})', 0),
            (r'\border[_\s]?id\b[：:\s]+([A-Za-z0-9_\-]{4,40})', re.IGNORECASE),
        ]
        for pattern, flags in explicit_patterns:
            match = re.search(pattern, text, flags)
            if match:
                return match.group(1)

        ord_match = re.search(r'\b(ORD[A-Za-z0-9_\-]{4,40})\b', text)
        if ord_match:
            return ord_match.group(1)

        stripped = text.strip()
        if re.match(r'^(?:ORD|ord)[A-Za-z0-9_\-]{4,40}$', stripped):
            return stripped
        return None
