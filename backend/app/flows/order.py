"""
订单查询 Flow Handler

职责：
- 处理 ORDER_QUERY 意图
- 调用 OrderQueryTool 查询订单信息
- 增强：自动补充物流信息、失败重试、综合分析

架构：
  用户输入 → Enhanced Executor → OrderQueryTool (+LogisticsTool)
  → 多工具结果 → LLM 综合分析 → AI 回复
"""

import logging
from app.flows.base import BaseFlow, FlowResult
from app.schemas.intent import IntentResult
from app.models.message import Message, MessageRole
from app.prompts.order import ORDER_PROMPT
from app.services.llm import call_llm
from app.tools.tool_router import select_tool
from app.tools.executors.tool_executor import tool_executor
from app.agents.enhanced_flow import enhanced_flow_handle, enhanced_tool_execute

logger = logging.getLogger(__name__)

ORDER_ENHANCED_PROMPT = """你是"小单"，电商订单管家。

关键能力：
- 综合订单状态、支付状态、物流状态给出完整画面
- 发现异常主动提醒（超时未发货、物流停滞等）
- 针对用户可能的后续需求给出建议（如：已签收→引导评价；异常→建议退款）

回答风格：
- 干练但不冷淡，像负责任的管家
- 先给结论，再给细节
- 用大白话而非系统术语"""


class OrderFlow(BaseFlow):
    """订单查询处理器（增强版）"""

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        logger.info(f"OrderFlow 处理: {intent_result.raw_input[:50]}")

        tool_calls = []
        user_message = intent_result.raw_input

        if slots and "order_id" in slots:
            # FSM slots → 增强执行（自动补充物流）
            return await enhanced_flow_handle(
                user_input=intent_result.raw_input,
                history=history,
                tool_name="query_order",
                tool_params={"order_id": slots["order_id"]},
                domain_prompt=ORDER_ENHANCED_PROMPT,
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
                # 使用增强执行
                return await enhanced_flow_handle(
                    user_input=intent_result.raw_input,
                    history=history,
                    tool_name=plan.tool.name,
                    tool_params=plan.params,
                    domain_prompt=ORDER_ENHANCED_PROMPT,
                    enrich=True,
                )
            else:
                logger.info(f"OrderFlow: 未调用工具 - {plan.reason}")

        content = await call_llm(
            system_prompt=ORDER_PROMPT,
            user_message=user_message,
            history=history,
        )

        return FlowResult(
            message=Message(role=MessageRole.ASSISTANT, content=content),
            tool_calls=tool_calls,
        )
