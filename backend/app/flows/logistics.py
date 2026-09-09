"""
物流查询 Flow Handler

职责：
- 处理 LOGISTICS_QUERY 意图
- 使用物流专用 Prompt 调用 LLM
- 增强：自动补充订单信息、失败降级到订单查询、异常检测

架构：
  用户输入 → Enhanced Executor → LogisticsTool (+OrderTool)
  → 多工具结果 → LLM 综合分析 → AI 回复
"""

import logging
from app.flows.base import BaseFlow, FlowResult
from app.schemas.intent import IntentResult
from app.models.message import Message, MessageRole
from app.prompts.logistics import LOGISTICS_PROMPT
from app.services.llm import call_llm
from app.tools.tool_router import select_tool
from app.tools.executors.tool_executor import tool_executor
from app.agents.enhanced_flow import enhanced_flow_handle

logger = logging.getLogger(__name__)

LOGISTICS_ENHANCED_PROMPT = """你是"小达"，电商物流跟踪专员。

关键能力：
- 综合物流轨迹和订单状态，给出全面的物流分析
- 主动计算预计到达时间（基于发货地、收货地、当前位置推算）
- 检测异常：停滞超2天、退回、派送失败等，主动提醒+给方案
- 如果物流查不到但有订单信息，推断可能原因（未发货/刚发货/运单延迟）

回答风格：
- 高效干脆，像靠谱的快递员
- 先给核心结论（到哪了/几天到），再给细节
- 异常时给明确可操作的下一步"""


class LogisticsFlow(BaseFlow):
    """物流查询处理器（增强版）"""

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        logger.info(f"LogisticsFlow 处理: {intent_result.raw_input[:50]}")

        if slots and "order_id" in slots:
            # FSM slots → 增强执行（自动补充订单状态）
            return await enhanced_flow_handle(
                user_input=intent_result.raw_input,
                history=history,
                tool_name="logistics_query",
                tool_params={"order_id": slots["order_id"]},
                domain_prompt=LOGISTICS_ENHANCED_PROMPT,
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
                    domain_prompt=LOGISTICS_ENHANCED_PROMPT,
                    enrich=True,
                )
            else:
                logger.info(f"LogisticsFlow: 未调用工具 - {plan.reason}")

        content = await call_llm(
            system_prompt=LOGISTICS_PROMPT,
            user_message=intent_result.raw_input,
            history=history,
        )

        return FlowResult(
            message=Message(role=MessageRole.ASSISTANT, content=content),
            tool_calls=[],
        )
