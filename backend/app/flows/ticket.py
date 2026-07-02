"""
投诉工单 Flow Handler（只读）

职责：
- 处理 TICKET 意图中的"跟进已有投诉"：读取真实投诉记录并总结
- 其余 TICKET 意图只给出创建指引，绝不在本 Flow 内写库

安全属性（AI 绝不静默建单）：
- 明确的创建请求在 agents/agent.py 的确认闸门被拦截并向用户确认；
- 用户确认后由闸门直接调用 complaint_create 建单；
- 因此本 Flow 不允许存在任何写库路径 —— 否则 LLM 路由到 ticket 的
  模糊输入（如"客服态度太差了"）会在无确认的情况下建单。
"""

import logging
from app.agents.complaint_intent import extract_complaint_id, is_followup_request
from app.database.connection import DatabaseAccessError
from app.database.repositories import ComplaintRepository
from app.flows.base import BaseFlow, FlowResult
from app.schemas.intent import IntentResult
from app.models.message import Message, MessageRole
from app.services.llm import call_llm

logger = logging.getLogger(__name__)

FOLLOWUP_PROMPT = """你是投诉跟进客服。只基于下面给出的真实投诉记录回答：
1. 当前处理进度（状态、优先级、最近处理记录）
2. 是否已升级/是否需要升级
3. 用户下一步可以做什么
不要编造记录里没有的信息。语气亲切、简短。"""


class TicketFlow(BaseFlow):
    """投诉工单处理器（跟进只读 + 创建指引，本 Flow 内绝不写库）"""

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        logger.info(f"TicketFlow 处理: {intent_result.raw_input[:50]}")

        # 跟进已有投诉：只读分支，读取真实投诉记录后直接返回。
        if is_followup_request(intent_result.raw_input):
            return await self._handle_followup(intent_result, history)

        # 非跟进、非明确创建（明确创建已在 agent.py 确认闸门被拦截并确认）：
        # 绝不静默建单 —— 不调用任何工具/写库，只给出创建指引。
        logger.info("TicketFlow: 非跟进且未经确认，不建单，返回创建指引")
        content = (
            "如果你想提交投诉，我可以帮你创建投诉工单——"
            "请回复“我要提交投诉 + 简单描述遇到的问题”，"
            "我会先和你确认投诉内容，确认后再正式提交。"
        )
        return FlowResult(
            message=Message(role=MessageRole.ASSISTANT, content=content),
            tool_calls=[],
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
