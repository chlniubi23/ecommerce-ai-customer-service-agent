"""
工单创建 Flow Handler

职责：
- 处理 TICKET 意图
- 调用 TicketTool 创建售后工单
- 使用 LLM 自然语言总结工单结果

架构：
  用户输入 → ToolRouter → TicketTool → Tool Result
  → Tool Result 注入 Prompt → LLM → AI 回复
"""

import logging
from app.agents.complaint_intent import extract_complaint_id, is_followup_request
from app.database.connection import DatabaseAccessError
from app.database.repositories import ComplaintRepository
from app.flows.base import BaseFlow, FlowResult
from app.schemas.intent import IntentResult
from app.models.message import Message, MessageRole
from app.services.llm import call_llm
from app.tools.tool_router import select_tool
from app.tools.executors.tool_executor import tool_executor

logger = logging.getLogger(__name__)

TICKET_PROMPT = """你是电商平台的售后客服。

你的职责是帮助用户创建售后工单。

回复要求：
1. 确认已为用户创建工单
2. 告知工单号和预计处理时间
3. 如果工具返回了结果，用自然语言总结
4. 语气亲切专业
5. 不要输出 JSON，只输出自然语言回复
"""

FOLLOWUP_PROMPT = """你是投诉跟进客服。只基于下面给出的真实投诉记录回答：
1. 当前处理进度（状态、优先级、最近处理记录）
2. 是否已升级/是否需要升级
3. 用户下一步可以做什么
不要编造记录里没有的信息。语气亲切、简短。"""


class TicketFlow(BaseFlow):
    """工单创建处理器"""

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        logger.info(f"TicketFlow 处理: {intent_result.raw_input[:50]}")

        # 跟进已有投诉：只读分支，读取真实投诉记录后直接返回。
        # 必须先于 select_tool/创建路径，任何跟进请求都绝不能落入创建投诉。
        if is_followup_request(intent_result.raw_input):
            return await self._handle_followup(intent_result, history)

        tool_calls = []
        user_message = intent_result.raw_input

        # 通过 ToolRouter 决策
        plan = await select_tool(
            intent="ticket",
            user_input=intent_result.raw_input,
            history=history,
        )

        if plan.should_call and plan.tool:
            exec_result = await tool_executor.execute(plan.tool, **plan.params)
            tool_calls.append(exec_result.to_trace_dict())
            if exec_result.success:
                user_message = f"{intent_result.raw_input}\n\n{exec_result.to_context_string()}"
                logger.info("TicketFlow: 工单创建成功，注入上下文")
        else:
            logger.info(f"TicketFlow: 未调用工具 - {plan.reason}")

        content = await call_llm(
            system_prompt=TICKET_PROMPT,
            user_message=user_message,
            history=history,
        )

        return FlowResult(
            message=Message(role=MessageRole.ASSISTANT, content=content),
            tool_calls=tool_calls,
        )

    async def _handle_followup(self, intent_result: IntentResult, history: list[dict]) -> FlowResult:
        """跟进已有投诉：查询真实投诉记录并总结，绝不创建新投诉。"""
        ref_id = extract_complaint_id(intent_result.raw_input)
        complaint = None
        if ref_id:
            try:
                complaint = ComplaintRepository().get_by_any_id(ref_id)
            except DatabaseAccessError as exc:
                logger.warning(f"TicketFlow follow-up db error: {exc}")

        if complaint:
            user_message = (
                f"用户问题：{intent_result.raw_input}\n\n"
                f"[真实投诉记录]\n{complaint}"
            )
            content = await call_llm(
                system_prompt=FOLLOWUP_PROMPT,
                user_message=user_message,
                history=history,
            )
            return FlowResult(
                message=Message(role=MessageRole.ASSISTANT, content=content),
                tool_calls=[{
                    "tool_name": "complaint_lookup",
                    "tool_input": {"complaint_id": ref_id},
                    "tool_output": {
                        "complaint_id": complaint.get("complaint_id"),
                        "complaint_status": complaint.get("complaint_status"),
                        "priority": complaint.get("priority"),
                    },
                    "success": True,
                    "latency_ms": 0,
                }],
            )

        content = (
            f"我没有查到编号 {ref_id or '（未识别）'} 的投诉记录，"
            "请确认工单号是否正确，或者我可以帮你转人工客服核实。"
        )
        return FlowResult(
            message=Message(role=MessageRole.ASSISTANT, content=content),
            tool_calls=[],
        )
