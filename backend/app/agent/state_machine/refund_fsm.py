"""
RefundFSM - 退款流程状态机

状态流转：
  START → WAIT_ORDER_ID → WAIT_REFUND_REASON → PROCESSING → DONE

必填 Slots：
  - order_id: 订单号
  - refund_reason: 退款原因

示例对话：
  用户: "我要退款"
  AI: "好的，请提供您的订单号"          → WAIT_ORDER_ID
  用户: "123456"
  AI: "请问退款原因是什么？"             → WAIT_REFUND_REASON
  用户: "不想要了"
  [调用 RefundTool] → PROCESSING → DONE
"""

import re
import logging
from typing import Any
from app.agent.state_machine.base_fsm import BaseFSM, SlotDefinition

logger = logging.getLogger(__name__)


class RefundFSM(BaseFSM):
    """退款流程状态机"""

    @property
    def flow_name(self) -> str:
        return "refund"

    @property
    def slot_definitions(self) -> list[SlotDefinition]:
        return [
            SlotDefinition(
                name="order_id",
                description="订单号",
                required=True,
                prompt="好的，我来帮您处理退款。请问您的订单号是多少？",
                state="WAIT_ORDER_ID",
            ),
            SlotDefinition(
                name="refund_reason",
                description="退款原因",
                required=True,
                prompt="收到，请问您退款的原因是什么呢？（比如：不想要了、质量问题、买错了等）",
                state="WAIT_REFUND_REASON",
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
        elif slot_name == "refund_reason":
            # 如果用户是查询退款状态（不是申请退款），自动填充原因
            if self._is_refund_status_query(user_input):
                return "查询退款状态"
            return self._extract_refund_reason(user_input)
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
        elif slot_name == "refund_reason":
            # 先尝试关键词匹配
            result = self._extract_refund_reason(user_input)
            if result:
                return result
            # 正在等 reason 时，接受自由文本
            stripped = user_input.strip()
            if 2 <= len(stripped) <= 100 and not stripped.isdigit():
                return stripped
            return None
        return None

    def _extract_order_id(self, text: str) -> str | None:
        """提取订单号。

        优先级（与 tools/tool_router.py 的 _extract_order_id 保持一致）：
        1. 系统上下文标注的"本轮优先处理订单号"
        2. 明确标注的订单号（订单号: xxx / order id: xxx，需显式"号"或 id 标记；
           "订单ORD_xxx" 紧邻写法也接受）
        3. 形如 ORD_xxx 的业务订单号（仅大写 ORD 前缀，避免 RefundAgent/ordered
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

        return None

    def _is_refund_status_query(self, text: str) -> bool:
        """判断用户是否在查询退款状态（而非申请退款）"""
        status_patterns = [
            "退款了吗", "退款进度", "退款状态", "退款到哪了",
            "退了吗", "退款成功了吗", "退款到账了吗", "退款审核",
            "退款怎么样了", "退款结果", "退了没", "退款没",
        ]
        return any(p in text for p in status_patterns)

    def _extract_refund_reason(self, text: str) -> str | None:
        """提取退款原因"""
        # 排除纯意图触发短语（这些不是真正的退款原因）
        intent_triggers = {
            "我要退款", "退款", "我要退货", "退货", "申请退款",
            "申请退货", "我想退款", "我想退货", "帮我退款",
            "我要申请退款", "退钱", "我要退钱",
        }
        stripped = text.strip()
        if stripped in intent_triggers:
            return None

        # 关键词映射
        reason_map = {
            "不想要": "不想要了",
            "不需要": "不需要了",
            "买错": "买错了",
            "质量": "质量问题",
            "坏了": "商品损坏",
            "破损": "商品破损",
            "不合适": "商品不合适",
            "尺码": "尺码不合适",
            "颜色": "颜色不满意",
            "没收到": "未收到商品",
            "没到": "未收到商品",
            "没有到": "未收到商品",
            "假": "怀疑假货",
            "发错": "发错商品",
        }
        for keyword, reason in reason_map.items():
            if keyword in text:
                return reason
        # 仅在 FSM 处于 WAIT_REFUND_REASON 状态时，才接受自由文本作为原因
        # 首次进入时不要用自由文本兜底（避免意图短语被误识别）
        return None
