"""
优惠券/促销 Flow Handler

职责：
- 处理 COUPON_QUERY 意图
- 当前用户"我有哪些优惠券"类问题：调用 query_coupons 工具，基于真实优惠券数据回答
- 通用优惠券规则问题（"优惠券怎么用"）：保留原 COUPON_PROMPT 规则话术

扩展规划：
- 有真实 user_coupons 表后，CouponRepository 换成 SQL 查询即可，Flow 不用改
"""

import logging
import re
from app.flows.base import BaseFlow, FlowResult
from app.schemas.intent import IntentResult
from app.models.message import Message, MessageRole
from app.prompts.coupon import COUPON_PROMPT
from app.services.llm import call_llm
from app.tools.executors.tool_executor import tool_executor

logger = logging.getLogger(__name__)

_CURRENT_COUPON_HINTS = (
    "我现在有哪些优惠券",
    "我的优惠券",
    "我有哪些优惠券",
    "当前可用优惠券",
    "有哪些券可以用",
    "我有什么优惠券",
)

CURRENT_COUPON_PROMPT = """你是电商平台优惠券福利官。只根据下面提供的真实优惠券数据回答用户当前有哪些可用优惠券：
- 先说可用张数，再逐张说明（名称、门槛/折扣、适用范围、有效期）
- 已使用/已过期的不要算进可用，可简要提一句
- 不要编造数据里没有的优惠券
语气亲切简短。"""


def _extract_user_id(text: str) -> str | None:
    match = re.search(r'\b(USR[A-Za-z0-9_\-]{4,40})\b', text)
    return match.group(1) if match else None


class CouponFlow(BaseFlow):
    """优惠券/促销处理器"""

    @staticmethod
    def _ensure_coupon_tool() -> None:
        """确保 query_coupons 已注册（正常在应用启动时由 init_tools 注册，
        这里做懒加载兜底，避免注册表未初始化时查不到工具）。"""
        from app.tools.tool_registry import tool_registry, init_tools
        if tool_registry.get("query_coupons") is None:
            init_tools()

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        logger.info(f"CouponFlow 处理: {intent_result.raw_input[:50]}")
        raw = intent_result.raw_input
        is_current = any(hint in raw for hint in _CURRENT_COUPON_HINTS)
        user_id = _extract_user_id(raw) or (slots or {}).get("user_id")

        if is_current and user_id:
            self._ensure_coupon_tool()
            exec_result = await tool_executor.execute_by_name("query_coupons", user_id=user_id)
            if exec_result.success:
                content = await call_llm(
                    system_prompt=CURRENT_COUPON_PROMPT,
                    user_message=f"用户问题：{raw}\n\n[真实优惠券数据]\n{exec_result.to_context_string()}",
                    history=history,
                )
                return FlowResult(
                    message=Message(role=MessageRole.ASSISTANT, content=content),
                    tool_calls=[exec_result.to_trace_dict()],
                )
            logger.info(f"CouponFlow: query_coupons 未成功，降级到规则话术 - {exec_result.error}")

        content = await call_llm(
            system_prompt=COUPON_PROMPT,
            user_message=raw,
            history=history,
        )
        return FlowResult(message=Message(role=MessageRole.ASSISTANT, content=content))
