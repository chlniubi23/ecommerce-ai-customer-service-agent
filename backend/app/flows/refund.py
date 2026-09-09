"""
退款/退货 Flow Handler

职责：
- 处理 REFUND 意图
- 增强：自动补充订单信息确认可退、失败重试、降级查订单
- 退款前自动验证订单状态

架构：
  用户输入 → Enhanced Executor → RefundTool (+OrderTool)
  → 多工具结果 → LLM 综合分析 → AI 回复
"""

import logging
from app.flows.base import BaseFlow, FlowResult
from app.schemas.intent import IntentResult
from app.models.message import Message, MessageRole
from app.prompts.refund import REFUND_PROMPT
from app.services.llm import call_llm
from app.tools.tool_router import select_tool
from app.tools.executors.tool_executor import tool_executor
from app.agents.enhanced_flow import enhanced_flow_handle

logger = logging.getLogger(__name__)

REFUND_ENHANCED_PROMPT = """你是"小安"，经验丰富的电商售后专员。

关键能力：
- 结合订单状态判断退款可行性（未发货可直接退、已签收走售后流程）
- 退款成功时给出预计到账时间和注意事项
- 退款失败时分析原因并给替代方案（换货、补偿、人工介入）
- 主动发现用户可能需要的其他帮助（如退款+物流拦截）

回答风格：
- 温暖共情，先安抚再处理
- 给出明确时间预期
- 复杂情况给出清晰的选择方案"""


class RefundFlow(BaseFlow):
    """退款/退货处理器（增强版）"""

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        logger.info(f"RefundFlow 处理: {intent_result.raw_input[:50]}")

        if slots and "order_id" in slots:
            # FSM slots → 增强执行（自动补充订单信息验证可退性）
            return await enhanced_flow_handle(
                user_input=intent_result.raw_input,
                history=history,
                tool_name="refund_apply",
                tool_params={
                    "order_id": slots["order_id"],
                    "reason": slots.get("refund_reason", ""),
                },
                domain_prompt=REFUND_ENHANCED_PROMPT,
                enrich=True,
            )
        else:
            # 通过 ToolRouter 提取参数
            plan = await select_tool(
                intent=intent_result.intent.value,
                user_input=intent_result.raw_input,
                history=history,
            )

            if plan.should_call and plan.tool:
                return await enhanced_flow_handle(
                    user_input=intent_result.raw_input,
                    history=history,
                    tool_name=plan.tool.name,
                    tool_params=plan.params,
                    domain_prompt=REFUND_ENHANCED_PROMPT,
                    enrich=True,
                )
            else:
                logger.info(f"RefundFlow: 未调用工具 - {plan.reason}")

        content = await call_llm(
            system_prompt=REFUND_PROMPT,
            user_message=intent_result.raw_input,
            history=history,
        )

        return FlowResult(
            message=Message(role=MessageRole.ASSISTANT, content=content),
            tool_calls=[],
        )
