"""
RecoveryManager - 异常输入恢复管理器

职责：
- 检测用户输入是否为无效 Slot 值（闲聊、乱码、表情等）
- 管理重试计数
- 超过重试上限时触发 fallback（退出当前 Flow）
- 生成友好的 clarification / fallback 提示

设计理念：
- 无效输入检测基于规则（短文本 + 无意义模式匹配）
- 不依赖 LLM，保持低延迟
- 每个 Slot 独立计数，成功提取后重置
- MAX_RETRY_COUNT = 3（可配置）

架构位置：
- agent/recovery/ 层
- 被 agents/agent.py 在 slot filling 失败时调用

使用方式：
    decision = recovery_manager.check(session, user_input, slot_extracted)
    if decision.should_fallback:
        session.clear_flow()
        return decision.fallback_message
    elif decision.should_clarify:
        return decision.clarify_message
"""

import re
import logging
from dataclasses import dataclass
from app.agent.memory.session import Session, MAX_RETRY_COUNT

logger = logging.getLogger(__name__)


# 无效输入模式：闲聊、乱码、表情、单字符等
INVALID_PATTERNS = [
    r'^[哈呵嘿嗯啊哦噢嘻]{2,}$',        # 哈哈哈、嘿嘿
    r'^[。，？！…~\.、\?!]+$',            # 纯标点
    r'^[\U0001F600-\U0001F64F]+$',       # 纯 Emoji
    r'^.{0,1}$',                          # 空或单字符
    r'^(不知道|随便|不清楚|不记得|忘了|算了|没有|没)$',  # 无意义回复
    r'^\?+$',                             # ???
    r'^\.+$',                             # ...
]

# Slot 相关的 clarification 模板
SLOT_CLARIFY_TEMPLATES = {
    "order_id": "我还需要您的订单号才能继续处理哦～订单号一般在购买记录或短信通知里，格式类似 123456 或 ORD20240101",
    "refund_reason": "请告诉我退款的原因，比如：不想要了、质量问题、买错了等～",
}

DEFAULT_CLARIFY = "不太理解您的意思呢，能再说清楚一点吗？"

FALLBACK_MESSAGE = (
    "抱歉, 暂时无法获取到完整信息\n"
    "建议您稍后重新描述问题, 或者直接发送完整信息(如: 订单123456退款, 质量问题)\n"
    "也可以联系人工客服帮您处理~"
)


@dataclass
class RecoveryDecision:
    """
    恢复决策结果

    Attributes:
        should_clarify: 是否需要 clarification（友好追问）
        should_fallback: 是否触发 fallback（退出 Flow）
        clarify_message: 追问提示语
        fallback_message: 兜底提示语
        retry_count: 当前重试次数
    """
    should_clarify: bool = False
    should_fallback: bool = False
    clarify_message: str = ""
    fallback_message: str = ""
    retry_count: int = 0


class RecoveryManager:
    """异常输入恢复管理器"""

    def is_invalid_input(self, user_input: str) -> bool:
        """
        检测输入是否为无效 Slot 值

        Args:
            user_input: 用户原始输入

        Returns:
            True 表示无效输入
        """
        stripped = user_input.strip()
        for pattern in INVALID_PATTERNS:
            if re.match(pattern, stripped):
                return True
        return False

    def check(
        self,
        session: Session,
        user_input: str,
        slot_extracted: bool,
    ) -> RecoveryDecision:
        """
        检查是否需要 recovery

        逻辑：
        1. 如果 Slot 成功提取 → 重置 retry，正常继续
        2. 如果输入无效或提取失败 → increment retry
        3. retry >= MAX → fallback（退出 Flow）
        4. retry < MAX → clarification（友好追问）

        Args:
            session: 当前会话
            user_input: 用户输入
            slot_extracted: 本轮 Slot 是否成功提取

        Returns:
            RecoveryDecision
        """
        if slot_extracted:
            session.reset_retry()
            return RecoveryDecision()

        # Slot 未提取成功
        is_invalid = self.is_invalid_input(user_input)
        current_retry = session.increment_retry()

        logger.info(
            f"[RecoveryManager] Slot 未提取, invalid={is_invalid}, "
            f"retry={current_retry}/{MAX_RETRY_COUNT}, "
            f"waiting={session.waiting_for}"
        )

        if current_retry >= MAX_RETRY_COUNT:
            # 达到上限 → fallback
            logger.info(f"[RecoveryManager] 达到重试上限，退出 Flow")
            return RecoveryDecision(
                should_fallback=True,
                fallback_message=FALLBACK_MESSAGE,
                retry_count=current_retry,
            )

        # 生成 clarification 消息
        waiting_for = session.waiting_for
        if is_invalid:
            # 无效输入：给出更具体的引导
            clarify = SLOT_CLARIFY_TEMPLATES.get(waiting_for, DEFAULT_CLARIFY)
        else:
            # 输入看起来正常但提取失败：温和重复
            clarify = SLOT_CLARIFY_TEMPLATES.get(waiting_for, DEFAULT_CLARIFY)

        return RecoveryDecision(
            should_clarify=True,
            clarify_message=clarify,
            retry_count=current_retry,
        )


# 全局单例
recovery_manager = RecoveryManager()
