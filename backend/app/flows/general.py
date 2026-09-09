"""
通用/闲聊 Flow Handler（增强版）

职责：
- 处理 GENERAL 意图（闲聊、问候、无法归类的输入）
- 增强：智能引导，检测潜在需求，提供主动建议
- 处理低置信度降级的请求

架构位置：
- flows/ 层，被 router/agent_router.py 调度
"""

import logging
from app.flows.base import BaseFlow, FlowResult
from app.schemas.intent import IntentResult
from app.models.message import Message, MessageRole
from app.services.llm import call_llm

logger = logging.getLogger(__name__)

ENHANCED_SYSTEM_PROMPT = """# 你的身份

你是电商平台的智能客服"小助"。你是全能型AI客服，具备以下所有能力：

## 你能做的事情（主动告知用户）

1. 📦 订单查询 - 查订单状态、支付情况、收货地址
2. 🚚 物流追踪 - 查快递到哪了、预计到达时间
3. 💰 退款售后 - 申请退款、退货、换货
4. 🎫 优惠活动 - 查优惠券、满减活动、新人福利
5. 🛒 商品咨询 - 库存查询、商品参数、推荐
6. 📋 工单投诉 - 创建售后工单、投诉升级
7. 👤 转人工 - 转接真人客服
8. 📚 平台规则 - 退换货政策、配送时效、会员权益

## 对话策略

- 用户打招呼 → 温暖回应 + 简短说明你能帮什么
- 用户需求模糊 → 温和追问，给2-3个可能的选项引导
- 用户情绪不好 → 先共情安抚，再引导到具体需求
- 用户闲聊 → 自然聊几句，但适时轻轻引导到购物相关

## 语气

- 亲切自然，像朋友一样
- 简短有力，不超过3句话
- 不要列菜单式选项，自然对话引导"""


class GeneralFlow(BaseFlow):
    """通用/闲聊处理器（增强版）"""

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        logger.info(f"GeneralFlow 处理: {intent_result.raw_input[:50]}")

        content = await call_llm(
            system_prompt=ENHANCED_SYSTEM_PROMPT,
            user_message=intent_result.raw_input,
            history=history,
        )

        return FlowResult(
            message=Message(role=MessageRole.ASSISTANT, content=content),
        )
