"""
Agent 主入口 - 决策引擎核心

职责：
- 编排完整的 Agent 决策链
- 支持多轮对话（Session + FSM + Slot Filling）
- 串联 Session Check → Classifier → Router → FSM → Tool → Response
- 收集完整的 Agent Execution Trace

数据流（首轮）：
  用户输入
  → Session Check（无活跃会话）
  → Intent Classification → TraceStep
  → Agent Router → TraceStep
  → FSM/Slot Filling（收集参数 or 直接执行）
  → Flow Handler（执行 + Prompt）→ TraceStep
  → Message + AgentTrace

数据流（多轮/恢复）：
  用户输入
  → Session Check（有活跃会话，正在等 Slot）
  → 跳过 Classify/Route
  → FSM/Slot Filling（填充 Slot）
  → 如果 Ready → Flow 执行工具
  → 如果 Not Ready → 返回追问

架构位置：
- agents/ 层顶层入口，被 api/chat.py 调用
- 协调 classifier、router、flows、session、fsm 五个子系统
- 构建 AgentTrace 并触发 Trace Logger
"""

import time
import uuid
import logging
from app.agents.classifier import classify_intent
from app.router.agent_router import route
from app.schemas.intent import IntentResult, IntentType, INTENT_DESCRIPTIONS
from app.schemas.trace import AgentTrace, TraceStep, TraceStepType
from app.models.message import Message, MessageRole
from app.core.trace_logger import log_trace
from app.agent.memory.session import Session, session_manager, MAX_RETRY_COUNT
from app.agent.slots.slot_manager import slot_manager, SlotFillingResult
from app.agent.state_machine.fsm_registry import fsm_registry
from app.agent.interrupt.interrupt_manager import interrupt_manager, InterruptDecision
from app.agent.recovery.recovery_manager import recovery_manager, RecoveryDecision
from app.services.llm import call_llm

logger = logging.getLogger(__name__)

LEGACY_RAG_DEPRECATION = {
    "classification": "Deprecated",
    "deprecated": True,
    "production_reachable": False,
    "replacement": "KnowledgeFlow -> KnowledgeWorkflow -> KnowledgeAgent -> knowledge_search",
    "removal_candidate": True,
    "note": "Direct rag_answer/RAGFlow branch is disabled in production by production_disable_legacy_rag.",
}


# Flow 类名到 Prompt 标识的映射
FLOW_PROMPT_MAP = {
    "RefundFlow": "refund_prompt",
    "LogisticsFlow": "logistics_prompt",
    "OrderFlow": "order_prompt",
    "ProductFlow": "product_prompt",
    "KnowledgeFlow": "knowledge_prompt",
    "CouponFlow": "coupon_prompt",
    "TicketFlow": "ticket_prompt",
    "HumanTransferFlow": "human_transfer_prompt",
    "GeneralFlow": "system_prompt",
}

# Intent 值到 Flow 类名的映射
INTENT_FLOW_MAP = {
    "refund": "RefundFlow",
    "logistics_query": "LogisticsFlow",
    "order_query": "OrderFlow",
    "product_query": "ProductFlow",
    "knowledge_query": "KnowledgeFlow",
    "coupon_query": "CouponFlow",
    "ticket": "TicketFlow",
    "human_transfer": "HumanTransferFlow",
    "general": "GeneralFlow",
}


def _generate_reasoning(
    user_input: str,
    intent_result: IntentResult | None,
    intent_desc: str,
    route_downgraded: bool = False,
    tool_calls: list[dict] | None = None,
    session_resumed: bool = False,
    session_flow: str = "",
    session_state: str = "",
    slot_filling: SlotFillingResult | None = None,
) -> str:
    """
    生成 Agent 内部推理摘要

    支持多轮对话场景的推理说明。
    """
    input_preview = user_input[:40]
    reasoning_parts = []
    reasoning_parts.append(f'用户说："{input_preview}"')

    # 多轮恢复说明
    if session_resumed:
        reasoning_parts.append(f"检测到活跃会话 → 恢复 {session_flow} 流程（状态: {session_state}）")
        reasoning_parts.append("跳过意图分类和路由，直接进入槽位填充")
    elif intent_result:
        intent = intent_result.intent.value
        confidence = intent_result.confidence
        # 意图信号
        intent_signals = {
            "refund": "表达了退款/退货诉求",
            "logistics_query": "在询问物流/快递状态",
            "order_query": "想了解订单相关信息",
            "product_query": "在咨询商品相关问题",
            "coupon_query": "在询问优惠/促销信息",
            "general": "属于日常问候或闲聊",
        }
        signal = intent_signals.get(intent, "意图不明确")
        reasoning_parts.append(f"判断：{signal}")

        if confidence >= 0.9:
            reasoning_parts.append(f"置信度很高（{confidence:.0%}），直接进入 {intent_desc} 流程")
        elif confidence >= 0.8:
            reasoning_parts.append(f"置信度较高（{confidence:.0%}），进入 {intent_desc} 流程")
        else:
            reasoning_parts.append(f"置信度偏低（{confidence:.0%}）")

        if route_downgraded:
            reasoning_parts.append("因置信度不足，降级到通用对话流程")

    # Slot Filling 说明
    if slot_filling:
        if slot_filling.ready:
            reasoning_parts.append(f"所有必填参数已收集: {slot_filling.slots}")
            reasoning_parts.append("参数就绪 → 执行工具调用")
        else:
            reasoning_parts.append(f"缺少参数: {slot_filling.waiting_for}")
            reasoning_parts.append(f"追问用户获取 {slot_filling.waiting_for}")

    # 工具调用说明
    if tool_calls:
        for tc in tool_calls:
            tool_name = tc.get('tool_name', 'unknown')
            success = tc.get('success', False)
            if success:
                reasoning_parts.append(f"调用工具 {tool_name} → 成功，已获取真实数据")
            else:
                reasoning_parts.append(f"调用工具 {tool_name} → 失败")

    return "\n".join(reasoning_parts)


def _build_trace(
    trace_id: str,
    user_message: str,
    steps: list[TraceStep],
    total_duration: float,
    session,
    intent_result: IntentResult | None,
    intent_desc: str,
    selected_flow: str,
    selected_prompt: str,
    message: Message,
    tool_calls: list[dict] | None = None,
    session_resumed: bool = False,
    slot_filling: SlotFillingResult | None = None,
    extra_reasoning: str = "",
) -> AgentTrace:
    """构建 AgentTrace 的辅助函数"""
    reasoning_parts = []
    if extra_reasoning:
        reasoning_parts.append(extra_reasoning)
    else:
        reasoning_parts.append(
            _generate_reasoning(
                user_input=user_message,
                intent_result=intent_result,
                intent_desc=intent_desc,
                session_resumed=session_resumed,
                session_flow=session.current_flow if session else "",
                session_state=session.current_state if session else "",
                slot_filling=slot_filling,
                tool_calls=tool_calls,
            )
        )

    return AgentTrace(
        trace_id=trace_id,
        user_input=user_message,
        steps=steps,
        total_duration_ms=total_duration,
        final_intent=session.current_flow if session and session.current_flow else (intent_result.intent.value if intent_result else "general"),
        final_confidence=intent_result.confidence if intent_result else 1.0,
        selected_flow=selected_flow,
        selected_prompt=selected_prompt,
        final_response=message.content[:100],
        reasoning="\n".join(reasoning_parts),
        tool_calls=tool_calls or [],
        session_id=session.session_id if session else "",
        current_state=session.current_state if session else "",
        waiting_for=session.waiting_for if session else "",
        collected_slots=dict(session.slots) if session else {},
        suspended_flows=list(session.suspended_flows) if session else [],
        retry_count=session.retry_count if session else 0,
    )


def _build_metadata(
    session,
    intent_result: IntentResult | None,
    intent_desc: str,
    selected_flow: str,
    selected_prompt: str,
    trace_id: str,
    duration_ms: float,
    session_id: str,
    tool_calls: list[dict] | None = None,
    existing_metadata: dict | None = None,
) -> dict:
    """构建 Message metadata 的辅助函数"""
    meta = {
        "intent": intent_result.intent.value if intent_result else (session.current_flow if session else "general"),
        "confidence": intent_result.confidence if intent_result else 1.0,
        "intent_desc": intent_desc,
        "selected_flow": selected_flow,
        "selected_prompt": selected_prompt,
        "trace_id": trace_id,
        "duration_ms": round(duration_ms),
        "session_id": session_id,
        "fsm_state": session.current_state if session else "",
        "waiting_for": session.waiting_for if session else "",
    }
    # Phase 5.4: Tool Calling 增强字段
    if tool_calls:
        first_tc = tool_calls[0]
        meta["selected_tool"] = first_tc.get("tool_name", "")
        meta["tool_args"] = first_tc.get("tool_input", {})
        meta["tool_result"] = first_tc.get("tool_output", {})
        meta["tool_latency_ms"] = first_tc.get("latency_ms", 0.0)
        meta["tool_success"] = first_tc.get("success", False)
        meta["tool_error"] = "" if first_tc.get("success", False) else str(first_tc.get("tool_output", {}).get("error", ""))
        meta["workflow_steps"] = len(tool_calls)
    if existing_metadata:
        preserved_keys = [
            "selected_agent",
            "knowledge_documents",
            "knowledge_chunks",
            "knowledge_citations",
            "answer_source",
            "trace",
        ]
        for key in preserved_keys:
            if key in existing_metadata:
                meta[key] = existing_metadata[key]
    return meta


class AgentResult:
    """
    Agent 执行结果

    包含 AI 回复 Message、意图分类结果和完整 Trace。
    API 层据此构建统一信封响应。
    """
    def __init__(
        self,
        message: Message,
        intent_result: IntentResult | None,
        trace: AgentTrace,
    ):
        self.message = message
        self.intent_result = intent_result
        self.trace = trace


SLOT_HUMANIZE_PROMPT = """你是电商客服"小助手"。用户发来一条消息，你需要向用户追问一个信息。

要求：
1. 先理解用户的情绪（焦虑、着急、不满、平静等）
2. 如果用户有负面情绪，先用1句话真诚安抚（不要敷衍）
3. 然后自然地引出你需要的信息
4. 语气亲切温暖，像朋友一样关心对方
5. 不要超过3句话，简洁有力
6. 不要用"您好"开头，不要太正式

用户说：{user_input}
你需要追问的信息：{waiting_for_desc}

直接输出回复，不要解释。"""

# 追问信息的中文描述映射
SLOT_DESC_MAP = {
    "order_id": "订单号",
    "refund_reason": "退款原因",
}


async def _humanize_slot_prompt(
    user_input: str,
    raw_prompt: str,
    flow_name: str,
    waiting_for: str,
    history: list[dict],
) -> str:
    """用 LLM 将 FSM 硬编码追问转化为有情感共鸣的自然语言回复"""
    try:
        waiting_desc = SLOT_DESC_MAP.get(waiting_for, waiting_for)
        prompt = SLOT_HUMANIZE_PROMPT.format(
            user_input=user_input[:200],
            waiting_for_desc=waiting_desc,
        )
        result = await call_llm(
            system_prompt=prompt,
            user_message=user_input,
            history=history[-4:] if history else [],
            temperature=0.7,
        )
        if result and len(result.strip()) > 5:
            return result.strip()
    except Exception as e:
        logger.warning(f"[Agent] 人格化追问失败，回退到原始 prompt: {e}")
    return raw_prompt


async def _handle_complaint_gate(
    session,
    user_message: str,
    intent_result,
    intent_desc: str,
    history: list[dict],
    trace_id: str,
    total_start: float,
    steps: list,
    session_id: str,
):
    """投诉创建确认闸门。

    返回 AgentResult 表示已直接处理本轮（提问确认 / 取消 / 不明确再问 / 确认后建单）；
    返回 None 表示放行（查询/跟进类，交由后续 route 只读处理，不建单）。
    """
    from app.agents import complaint_intent as ci
    from app.agents.coordinator import _extract_order_id

    has_pending = session.pending_complaint is not None
    action = ci.resolve_complaint_gate(has_pending, user_message)
    visible = ci.user_visible_input(user_message)

    def _finish(content: str, reasoning: str):
        session.add_history("assistant", content)
        session.clear_flow()
        session_manager.save(session)
        message = Message(role=MessageRole.ASSISTANT, content=content)
        total_duration = (time.perf_counter() - total_start) * 1000
        trace = _build_trace(
            trace_id=trace_id, user_message=user_message, steps=steps,
            total_duration=total_duration, session=session,
            intent_result=intent_result, intent_desc=intent_desc,
            selected_flow="TicketFlow", selected_prompt="ticket_prompt",
            message=message, extra_reasoning=reasoning,
        )
        log_trace(trace)
        message.metadata = _build_metadata(
            session=session, intent_result=intent_result, intent_desc=intent_desc,
            selected_flow="TicketFlow", selected_prompt="ticket_prompt",
            trace_id=trace_id, duration_ms=total_duration, session_id=session_id,
        )
        return AgentResult(message=message, intent_result=intent_result, trace=trace)

    if action == "none":
        # 查询/跟进类，不进入创建流程；交还给后续 route（只读，不建单）
        return None

    if action == "ask_confirm":
        order_id = _extract_order_id(visible)
        draft = {
            "content": visible[:200],
            "complaint_type": "售后",
            "order_id": order_id,
        }
        session.pending_complaint = draft
        order_hint = f"，关联订单 {order_id}" if order_id else ""
        content = (
            f"我可以帮你提交这条投诉{order_hint}：\n“{draft['content']}”\n\n"
            "确认要我现在帮你提交吗？回复“确认”我就提交，回复“不用”则取消。"
        )
        # 注意：此处不调用任何写库工具
        session.add_history("assistant", content)
        session_manager.save(session)
        message = Message(role=MessageRole.ASSISTANT, content=content)
        total_duration = (time.perf_counter() - total_start) * 1000
        trace = _build_trace(
            trace_id=trace_id, user_message=user_message, steps=steps,
            total_duration=total_duration, session=session,
            intent_result=intent_result, intent_desc=intent_desc,
            selected_flow="TicketFlow", selected_prompt="ticket_prompt",
            message=message, extra_reasoning="识别到创建投诉意图，先向用户确认，未写入数据库",
        )
        log_trace(trace)
        message.metadata = _build_metadata(
            session=session, intent_result=intent_result, intent_desc=intent_desc,
            selected_flow="TicketFlow", selected_prompt="ticket_prompt",
            trace_id=trace_id, duration_ms=total_duration, session_id=session_id,
        )
        return AgentResult(message=message, intent_result=intent_result, trace=trace)

    if action == "ask_again":
        content = "你是要我帮你提交这条投诉吗？回复“确认”我就提交，回复“不用”则取消。"
        return _finish(content, "等待用户确认投诉，回答不明确，再次询问")

    if action == "cancel":
        session.pending_complaint = None
        content = "好的，已取消，不会提交这条投诉。还有什么可以帮你？"
        return _finish(content, "用户取消投诉创建，未写入数据库")

    if action == "create":
        draft = session.pending_complaint or {}
        session.pending_complaint = None
        from app.tools.executors.tool_executor import tool_executor
        user_id = session.slots.get("user_id") or _extract_user_id_from_history(history)
        params = {
            "content": draft.get("content", visible[:200]),
            "complaint_type": draft.get("complaint_type", "售后"),
        }
        if draft.get("order_id"):
            params["order_id"] = draft["order_id"]
        if user_id:
            params["user_id"] = user_id
        exec_result = await tool_executor.execute_by_name("complaint_create", **params)
        if exec_result.success:
            data = exec_result.tool_result.data if exec_result.tool_result else {}
            cid = data.get("complaint_id", "")
            content = f"已为你提交投诉{('，工单号 ' + cid) if cid else ''}，我们会尽快处理并同步进度。"
            reasoning = "用户已确认，调用 complaint_create 创建投诉"
        else:
            content = f"抱歉，投诉提交失败了：{exec_result.error}。你可以稍后再试或前往投诉中心提交。"
            reasoning = f"用户确认后创建投诉失败: {exec_result.error}"
        return _finish(content, reasoning)

    return None


def _extract_user_id_from_history(history: list[dict] | None) -> str | None:
    """从历史消息中提取用户 ID（前端上下文里带的 USRxxxx）。"""
    import re as _re
    if not history:
        return None
    for msg in reversed(history):
        match = _re.search(r'\b(USR[A-Za-z0-9_\-]{4,40})\b', msg.get("content", ""))
        if match:
            return match.group(1)
    return None


async def run(
    user_message: str,
    history: list[dict] = [],
    session_id: str = "",
) -> AgentResult:
    """
    执行 Agent 决策链（支持多轮对话）

    流程：
    1. 加载/创建 Session
    2. 检查是否有活跃会话（session 恢复）
       - 有 → 跳过 classify/route，直接进入 Slot Filling
       - 无 → 正常 classify → route
    3. FSM + Slot Filling
       - Ready → 执行 Flow（含 Tool Calling）
       - Not Ready → 返回追问
    4. 构建 AgentTrace

    Args:
        user_message: 用户当前输入
        history: 对话历史
        session_id: 会话 ID（前端传入）

    Returns:
        AgentResult
    """
    total_start = time.perf_counter()
    trace_id = uuid.uuid4().hex[:16]
    steps: list[TraceStep] = []

    # ===== Session 管理 =====
    if not session_id:
        session_id = uuid.uuid4().hex[:16]
    session = session_manager.get_or_create(session_id)
    session.add_history("user", user_message)

    # ===== 待确认投诉短路：用户上一轮被要求确认，本轮直接交给确认闸门 =====
    # 避免"确认"被当成新意图重新分类，导致 pending_complaint 被搁置、确认建单永不触发。
    # 但仅在本轮是"确认/拒绝"时短路；用户若转向无关问题（如查物流），
    # 应丢弃过期草稿并走正常路由，而不是被闸门反复追问。
    if session.pending_complaint is not None:
        from app.agents.complaint_intent import is_confirmation, is_denial

        if is_confirmation(user_message) or is_denial(user_message):
            pending_intent = IntentResult(
                intent=IntentType.TICKET,
                confidence=1.0,
                raw_input=user_message,
            )
            gate_result = await _handle_complaint_gate(
                session=session,
                user_message=user_message,
                intent_result=pending_intent,
                intent_desc=INTENT_DESCRIPTIONS.get(IntentType.TICKET, "创建工单/售后"),
                history=history,
                trace_id=trace_id,
                total_start=total_start,
                steps=steps,
                session_id=session_id,
            )
            if gate_result is not None:
                return gate_result
        else:
            # 无关轮次：丢弃过期草稿，继续走正常分类/路由（不 return）
            logger.info("[Agent] 放弃未确认投诉草稿，用户转向了其他问题")
            session.pending_complaint = None
            session_manager.save(session)

    # 用于 Trace 的变量
    intent_result: IntentResult | None = None
    intent_desc = ""
    selected_flow = ""
    selected_prompt = ""
    route_downgraded = False
    tool_calls: list[dict] = []
    session_resumed = False
    slot_result: SlotFillingResult | None = None

    # ===== 前置检测：无活跃 Flow + 有挂起 Flow + 恢复关键词 =====
    from app.agent.interrupt.interrupt_manager import RESUME_KEYWORDS
    if (
        not session.is_active()
        and session.has_suspended_flow()
        and user_message.strip().lower() in RESUME_KEYWORDS
    ):
        snapshot = session.resume_suspended_flow()
        logger.info(f"[Agent] 从挂起栈恢复: {snapshot}")

        # 直接返回恢复提示 + slot 追问
        selected_flow = INTENT_FLOW_MAP.get(session.current_flow, "GeneralFlow")
        selected_prompt = FLOW_PROMPT_MAP.get(selected_flow, "unknown")
        intent_desc = INTENT_DESCRIPTIONS.get(
            IntentType(session.current_flow) if session.current_flow in [e.value for e in IntentType] else IntentType.GENERAL,
            "未知"
        )

        fsm = fsm_registry.get(session.current_flow)
        resume_content = "好的，我们继续之前的流程～\n"
        if fsm:
            waiting_slot = fsm._find_waiting_slot(session.current_state)
            if waiting_slot:
                resume_content += waiting_slot.prompt

        steps.append(TraceStep(
            step_type=TraceStepType.ROUTING,
            name="FlowResume",
            duration_ms=0,
            input_data={"user_input": user_message[:100]},
            output_data={"resumed_flow": session.current_flow, "resumed_state": session.current_state},
        ))

        message = Message(role=MessageRole.ASSISTANT, content=resume_content)
        session.add_history("assistant", resume_content)
        session_manager.save(session)

        total_duration = (time.perf_counter() - total_start) * 1000
        trace = _build_trace(
            trace_id=trace_id, user_message=user_message, steps=steps,
            total_duration=total_duration, session=session,
            intent_result=None, intent_desc=intent_desc,
            selected_flow=selected_flow, selected_prompt=selected_prompt,
            message=message, session_resumed=True,
            extra_reasoning=f"用户确认恢复被挂起的 {session.current_flow} 流程",
        )
        log_trace(trace)
        message.metadata = _build_metadata(
            session=session, intent_result=None, intent_desc=intent_desc,
            selected_flow=selected_flow, selected_prompt=selected_prompt,
            trace_id=trace_id, duration_ms=total_duration, session_id=session_id,
        )
        return AgentResult(message=message, intent_result=None, trace=trace)

    # ===== 判断：是否恢复已有会话 =====
    if session.is_active() and not session.is_completed():
        # 多轮恢复模式
        session_resumed = True
        selected_flow = INTENT_FLOW_MAP.get(session.current_flow, "GeneralFlow")
        selected_prompt = FLOW_PROMPT_MAP.get(selected_flow, "unknown")
        intent_desc = INTENT_DESCRIPTIONS.get(
            IntentType(session.current_flow) if session.current_flow in [e.value for e in IntentType] else IntentType.GENERAL,
            "未知"
        )

        logger.info(
            f"[Agent] 会话恢复: flow={session.current_flow}, "
            f"state={session.current_state}, waiting={session.waiting_for}"
        )

        # ===== 中断检测 =====
        interrupt_decision = await interrupt_manager.check(session, user_message)

        if interrupt_decision.should_resume and session.has_suspended_flow():
            # 用户要求恢复被挂起的 Flow
            snapshot = session.resume_suspended_flow()
            selected_flow = INTENT_FLOW_MAP.get(session.current_flow, "GeneralFlow")
            selected_prompt = FLOW_PROMPT_MAP.get(selected_flow, "unknown")

            steps.append(TraceStep(
                step_type=TraceStepType.ROUTING,
                name="FlowResume",
                duration_ms=0,
                input_data={"user_input": user_message[:100]},
                output_data={
                    "resumed_flow": session.current_flow,
                    "resumed_state": session.current_state,
                    "from_suspended": True,
                },
            ))

            # 返回恢复提示 + 继续追问
            fsm = fsm_registry.get(session.current_flow)
            resume_prompt = f"好的，我们继续处理之前的流程～\n"
            if fsm:
                waiting_slot = fsm._find_waiting_slot(session.current_state)
                if waiting_slot:
                    resume_prompt += waiting_slot.prompt

            message = Message(role=MessageRole.ASSISTANT, content=resume_prompt)
            session.add_history("assistant", resume_prompt)
            session_manager.save(session)

            total_duration = (time.perf_counter() - total_start) * 1000
            trace = _build_trace(
                trace_id=trace_id, user_message=user_message, steps=steps,
                total_duration=total_duration, session=session,
                intent_result=None, intent_desc=intent_desc,
                selected_flow=selected_flow, selected_prompt=selected_prompt,
                message=message, session_resumed=True,
            )
            log_trace(trace)
            message.metadata = _build_metadata(
                session=session, intent_result=None, intent_desc=intent_desc,
                selected_flow=selected_flow, selected_prompt=selected_prompt,
                trace_id=trace_id, duration_ms=total_duration, session_id=session_id,
            )
            return AgentResult(message=message, intent_result=None, trace=trace)

        if interrupt_decision.should_interrupt:
            # 挂起当前 Flow → 切换到新 Flow
            resume_prompt = interrupt_decision.resume_prompt
            session.suspend_current_flow()
            intent_result = interrupt_decision.new_intent_result

            steps.append(TraceStep(
                step_type=TraceStepType.ROUTING,
                name="FlowInterrupt",
                duration_ms=0,
                input_data={"user_input": user_message[:100]},
                output_data={
                    "interrupted_flow": session.suspended_flows[-1]["flow_name"] if session.suspended_flows else "",
                    "new_intent": intent_result.intent.value,
                    "resume_prompt": resume_prompt,
                },
            ))

            logger.info(f"[Agent] Flow 中断 → 新意图: {intent_result.intent.value}")

            # 重新走正常的 classify→route 逻辑（跳过 classify，直接用新 intent）
            flow_name = intent_result.intent.value
            session.current_flow = flow_name
            intent_desc = INTENT_DESCRIPTIONS.get(intent_result.intent, "未知")
            session_resumed = False

            if fsm_registry.has(flow_name):
                session.current_state = "START"
                slot_result = slot_manager.process(session, user_message)

                steps.append(TraceStep(
                    step_type=TraceStepType.ROUTING,
                    name="AgentRouter",
                    duration_ms=0,
                    input_data={"intent": flow_name, "confidence": intent_result.confidence},
                    output_data={"selected_flow": INTENT_FLOW_MAP.get(flow_name, "GeneralFlow"), "has_fsm": True},
                ))
            else:
                slot_result = None
                step2_start = time.perf_counter()
                route_result = await route(intent_result, history)
                step2_duration = (time.perf_counter() - step2_start) * 1000

                selected_flow = route_result.selected_flow
                selected_prompt = FLOW_PROMPT_MAP.get(selected_flow, "unknown")
                tool_calls = route_result.tool_calls

                steps.append(TraceStep(
                    step_type=TraceStepType.FLOW_EXECUTION,
                    name=selected_flow,
                    duration_ms=step2_duration,
                    input_data={"user_input": user_message[:100]},
                    output_data={"response_preview": route_result.message.content[:100]},
                ))

                # 新 Flow 无 FSM → 直接完成 → 提示恢复
                message_content = route_result.message.content
                if session.has_suspended_flow():
                    message_content += f"\n\n{resume_prompt}"

                message = Message(role=MessageRole.ASSISTANT, content=message_content)
                session.add_history("assistant", message_content)
                session.clear_flow()
                session_manager.save(session)

                total_duration = (time.perf_counter() - total_start) * 1000
                trace = _build_trace(
                    trace_id=trace_id, user_message=user_message, steps=steps,
                    total_duration=total_duration, session=session,
                    intent_result=intent_result, intent_desc=intent_desc,
                    selected_flow=selected_flow, selected_prompt=selected_prompt,
                    message=message, tool_calls=route_result.tool_calls,
                )
                log_trace(trace)
                message.metadata = _build_metadata(
                    session=session, intent_result=intent_result, intent_desc=intent_desc,
                    selected_flow=selected_flow, selected_prompt=selected_prompt,
                    trace_id=trace_id, duration_ms=total_duration, session_id=session_id,
                    tool_calls=route_result.tool_calls,
                )
                return AgentResult(message=message, intent_result=intent_result, trace=trace)

            # 注: 如果中断后的新 Flow 有 FSM，继续走后面的 slot_result 处理

        else:
            # ===== 不中断 → 继续当前 Flow 的 Slot Filling =====
            steps.append(TraceStep(
                step_type=TraceStepType.ROUTING,
                name="SessionResume",
                duration_ms=0,
                input_data={"user_input": user_message[:100]},
                output_data={
                    "resumed_flow": session.current_flow,
                    "resumed_state": session.current_state,
                    "waiting_for": session.waiting_for,
                },
            ))

            # 先记录旧 slots 用于判断是否成功提取
            old_slots = dict(session.slots)
            slot_result = slot_manager.process(session, user_message)

            # ===== 异常恢复检测 =====
            slot_extracted = slot_result.slots != old_slots
            recovery_decision = recovery_manager.check(session, user_message, slot_extracted)

            if recovery_decision.should_fallback:
                # 达到重试上限 → 退出 Flow
                message = Message(role=MessageRole.ASSISTANT, content=recovery_decision.fallback_message)
                session.add_history("assistant", recovery_decision.fallback_message)
                session.clear_flow()
                session_manager.save(session)

                total_duration = (time.perf_counter() - total_start) * 1000
                trace = _build_trace(
                    trace_id=trace_id, user_message=user_message, steps=steps,
                    total_duration=total_duration, session=session,
                    intent_result=None, intent_desc=intent_desc,
                    selected_flow=selected_flow, selected_prompt=selected_prompt,
                    message=message, session_resumed=True,
                    extra_reasoning=f"连续 {recovery_decision.retry_count} 次无法提取有效参数，退出流程",
                )
                log_trace(trace)
                message.metadata = _build_metadata(
                    session=session, intent_result=None, intent_desc=intent_desc,
                    selected_flow=selected_flow, selected_prompt=selected_prompt,
                    trace_id=trace_id, duration_ms=total_duration, session_id=session_id,
                )
                return AgentResult(message=message, intent_result=None, trace=trace)

            if recovery_decision.should_clarify:
                # 无效输入 → 返回 clarification，不推进 FSM
                message = Message(role=MessageRole.ASSISTANT, content=recovery_decision.clarify_message)
                session.add_history("assistant", recovery_decision.clarify_message)
                session_manager.save(session)

                total_duration = (time.perf_counter() - total_start) * 1000
                trace = _build_trace(
                    trace_id=trace_id, user_message=user_message, steps=steps,
                    total_duration=total_duration, session=session,
                    intent_result=None, intent_desc=intent_desc,
                    selected_flow=selected_flow, selected_prompt=selected_prompt,
                    message=message, session_resumed=True,
                    extra_reasoning=f"输入无效 (retry {recovery_decision.retry_count}/{MAX_RETRY_COUNT})，提示用户重新输入",
                )
                log_trace(trace)
                message.metadata = _build_metadata(
                    session=session, intent_result=None, intent_desc=intent_desc,
                    selected_flow=selected_flow, selected_prompt=selected_prompt,
                    trace_id=trace_id, duration_ms=total_duration, session_id=session_id,
                )
                return AgentResult(message=message, intent_result=None, trace=trace)

    else:
        # ===== 多 Agent 协作检测 =====
        from app.agents.coordinator import should_coordinate, coordinate, detect_multi_intent
        if should_coordinate(user_message):
            domains = detect_multi_intent(user_message)
            logger.info(f"[Agent] 检测到多意图: {domains}，启动多Agent协作")

            coord_start = time.perf_counter()
            coord_result = await coordinate(user_message, history, domains)
            coord_duration = (time.perf_counter() - coord_start) * 1000

            steps.append(TraceStep(
                step_type=TraceStepType.FLOW_EXECUTION,
                name="MultiAgentCoordinator",
                duration_ms=coord_duration,
                input_data={"user_input": user_message[:100], "domains": domains},
                output_data={"tool_count": len(coord_result.tool_calls), "response_preview": coord_result.message.content[:100]},
            ))
            for tc in coord_result.tool_calls:
                steps.append(TraceStep(
                    step_type=TraceStepType.TOOL_CALL,
                    name=tc.get("tool_name", "unknown"),
                    duration_ms=tc.get("latency_ms", 0),
                    input_data=tc.get("tool_input", {}),
                    output_data=tc.get("tool_output", {}),
                    metadata={"success": tc.get("success", False)},
                ))

            message = coord_result.message
            session.add_history("assistant", message.content)
            session.clear_flow()
            session_manager.save(session)

            total_duration = (time.perf_counter() - total_start) * 1000
            trace = AgentTrace(
                trace_id=trace_id,
                user_input=user_message,
                steps=steps,
                total_duration_ms=total_duration,
                final_intent="multi_agent",
                final_confidence=0.95,
                selected_flow="MultiAgentCoordinator",
                selected_prompt="coordinator",
                final_response=message.content[:100],
                reasoning=f"检测到跨域请求（{', '.join(domains)}），启动多Agent并行协作",
                tool_calls=coord_result.tool_calls,
                session_id=session_id,
                current_state="",
                waiting_for="",
                collected_slots={},
                suspended_flows=list(session.suspended_flows),
                retry_count=session.retry_count,
            )
            log_trace(trace)
            message.metadata = {
                "intent": "multi_agent",
                "confidence": 0.95,
                "intent_desc": "多Agent协作",
                "selected_flow": "MultiAgentCoordinator",
                "selected_prompt": "coordinator",
                "trace_id": trace_id,
                "duration_ms": round(total_duration),
                "session_id": session_id,
                "coordinator": True,
                "domains": domains,
                "workflow_steps": len(coord_result.tool_calls),
            }
            return AgentResult(message=message, intent_result=None, trace=trace)

        # ===== 正常模式：Intent Classification =====
        step1_start = time.perf_counter()
        intent_result = await classify_intent(user_message)
        step1_duration = (time.perf_counter() - step1_start) * 1000

        intent_desc = INTENT_DESCRIPTIONS.get(intent_result.intent, "未知")
        steps.append(TraceStep(
            step_type=TraceStepType.INTENT_CLASSIFICATION,
            name="IntentClassifier",
            duration_ms=step1_duration,
            input_data={"user_input": user_message[:100]},
            output_data={
                "intent": intent_result.intent.value,
                "confidence": intent_result.confidence,
                "intent_desc": intent_desc,
            },
        ))

        # 初始化 Session Flow
        flow_name = intent_result.intent.value
        session.current_flow = flow_name

        # ===== 投诉创建确认闸门：AI 绝不静默建单 =====
        # 两类创建：(1) 用户在投诉中心自己提交（走 /api/commerce/complaints，不经此处）
        #           (2) 用户让 AI 创建 —— 必须先确认，再写库
        if flow_name == "ticket":
            gate_result = await _handle_complaint_gate(
                session=session,
                user_message=user_message,
                intent_result=intent_result,
                intent_desc=intent_desc,
                history=history,
                trace_id=trace_id,
                total_start=total_start,
                steps=steps,
                session_id=session_id,
            )
            if gate_result is not None:
                return gate_result

        # ===== RAG 检索增强 =====
        # Phase 5.4: 有专用 Tool Calling Flow 的意图直接走 Flow/FSM，跳过 RAG
        # RAG 仅服务于 general/coupon 等无专用工具的意图
        TOOL_FLOW_INTENTS = {"logistics_query", "refund", "order_query", "product_query", "knowledge_query", "ticket", "human_transfer"}
        skip_rag = flow_name in TOOL_FLOW_INTENTS and intent_result.confidence >= 0.4
        production_disable_legacy_rag = True
        if production_disable_legacy_rag and not skip_rag:
            skip_rag = True
            logger.info(
                "[Agent] Production architecture unification: legacy RAGFlow is deprecated; "
                "requests continue through FlowRegistry/KnowledgeFlow instead of direct rag_answer."
            )
        if skip_rag:
            logger.info(f"[Agent] 意图 {flow_name} 有专用 Tool Flow，跳过 RAG，走 FSM/Route")
        if not skip_rag:
            from app.rag.pipelines.rag_pipeline import rag_answer
            from app.rag.vectorstore import chroma_store

        if not skip_rag and chroma_store.count() > 0:
            logger.info("[Agent] 向量库有数据，尝试 RAG 回答...")
            # 使用 Session 历史 (权威来源，包含之前所有轮次)
            session_history = session.history[:-1]  # 排除刚加入的当前 user message
            rag_start = time.perf_counter()
            rag_result = await rag_answer(
                question=user_message,
                history=session_history,
                top_k=5,
                min_score=0.01,
            )
            rag_duration = (time.perf_counter() - rag_start) * 1000

            if rag_result.used_rag:
                # RAG 命中 → 使用 RAG 回答
                selected_flow = "RAGFlow"
                selected_prompt = "rag_prompt"

                steps.append(TraceStep(
                    step_type=TraceStepType.ROUTING,
                    name="RAGRetrieval",
                    duration_ms=rag_duration,
                    input_data={"query": user_message[:100], "top_k": 5},
                    output_data={
                        "chunks_found": len(rag_result.retrieval.chunks) if rag_result.retrieval else 0,
                        "used_rag": True,
                        "prompt_length": rag_result.prompt_length,
                        "sources": list(set(
                            c.get("metadata", {}).get("file_name", "?")
                            for c in (rag_result.retrieval.chunks if rag_result.retrieval else [])
                        )),
                    },
                    metadata=rag_result.retrieval.debug_info if rag_result.retrieval else {},
                ))

                message = Message(role=MessageRole.ASSISTANT, content=rag_result.answer)
                session.add_history("assistant", rag_result.answer)
                session.clear_flow()
                session_manager.save(session)

                rag_sources = list(set(
                    c.get("metadata", {}).get("file_name", "?")
                    for c in (rag_result.retrieval.chunks if rag_result.retrieval else [])
                ))
                reasoning = (
                    f'用户说："{user_message[:40]}"\n'
                    f"检索Query: \"{rag_result.retrieval_query[:60]}\"\n"
                    f"知识库命中 {len(rag_result.retrieval.chunks if rag_result.retrieval else [])} 个片段\n"
                    f"来源: {', '.join(rag_sources)}\n"
                    f"历史记忆: {rag_result.memory_count} 条\n"
                    f"RAG Prompt {rag_result.prompt_length} 字符"
                )

                total_duration = (time.perf_counter() - total_start) * 1000
                trace = AgentTrace(
                    trace_id=trace_id,
                    user_input=user_message,
                    steps=steps,
                    total_duration_ms=total_duration,
                    final_intent=intent_result.intent.value,
                    final_confidence=intent_result.confidence,
                    selected_flow=selected_flow,
                    selected_prompt=selected_prompt,
                    final_response=message.content[:100],
                    reasoning=reasoning,
                    tool_calls=[],
                    session_id=session_id,
                    current_state="",
                    waiting_for="",
                    collected_slots={},
                    suspended_flows=list(session.suspended_flows),
                    retry_count=session.retry_count,
                )

                log_trace(trace)
                message.metadata = {
                    "intent": intent_result.intent.value,
                    "confidence": intent_result.confidence,
                    "intent_desc": intent_desc,
                    "selected_flow": selected_flow,
                    "selected_prompt": selected_prompt,
                    "trace_id": trace_id,
                    "duration_ms": round(total_duration),
                    "session_id": session_id,
                    "rag_used": True,
                    "rag_chunks": len(rag_result.retrieval.chunks) if rag_result.retrieval else 0,
                    "rag_sources": rag_sources,
                    "memory_count": rag_result.memory_count,
                    "retrieval_query": rag_result.retrieval_query,
                }
                return AgentResult(message=message, intent_result=intent_result, trace=trace)
            else:
                logger.info("[Agent] RAG 无相关结果，走常规 FSM/Route")

        # ===== 检查 FSM =====
        if fsm_registry.has(flow_name):
            # 有 FSM → 走 Slot Filling 流程
            session.current_state = "START"
            slot_result = slot_manager.process(session, user_message)

            steps.append(TraceStep(
                step_type=TraceStepType.ROUTING,
                name="AgentRouter",
                duration_ms=0,
                input_data={
                    "intent": intent_result.intent.value,
                    "confidence": intent_result.confidence,
                },
                output_data={
                    "selected_flow": INTENT_FLOW_MAP.get(flow_name, "GeneralFlow"),
                    "has_fsm": True,
                    "fsm_state": session.current_state,
                },
            ))
        else:
            # 无 FSM → 走路由模式
            slot_result = None

            step2_start = time.perf_counter()
            route_result = await route(intent_result, history)
            step2_duration = (time.perf_counter() - step2_start) * 1000

            selected_flow = route_result.selected_flow
            selected_prompt = FLOW_PROMPT_MAP.get(selected_flow, "unknown")
            route_downgraded = route_result.downgraded
            tool_calls = route_result.tool_calls

            steps.append(TraceStep(
                step_type=TraceStepType.ROUTING,
                name="AgentRouter",
                duration_ms=0,
                input_data={
                    "intent": intent_result.intent.value,
                    "confidence": intent_result.confidence,
                },
                output_data={
                    "selected_flow": selected_flow,
                    "downgraded": route_result.downgraded,
                    "original_intent": route_result.original_intent,
                },
            ))

            steps.append(TraceStep(
                step_type=TraceStepType.FLOW_EXECUTION,
                name=selected_flow,
                duration_ms=step2_duration,
                input_data={"user_input": user_message[:100]},
                output_data={
                    "prompt": selected_prompt,
                    "response_preview": route_result.message.content[:100],
                },
            ))

            if route_result.tool_calls:
                for tc in route_result.tool_calls:
                    steps.append(TraceStep(
                        step_type=TraceStepType.TOOL_CALL,
                        name=tc.get("tool_name", "unknown_tool"),
                        duration_ms=0,
                        input_data=tc.get("tool_input", {}),
                        output_data=tc.get("tool_output", {}),
                        metadata={"success": tc.get("success", False)},
                    ))

            # 记录 AI 回复到 Session
            session.add_history("assistant", route_result.message.content)
            session.clear_flow()
            session_manager.save(session)

            # 生成 Reasoning + 构建 Trace
            message = route_result.message
            reasoning = _generate_reasoning(
                user_input=user_message,
                intent_result=intent_result,
                intent_desc=intent_desc,
                route_downgraded=route_downgraded,
                tool_calls=tool_calls,
            )

            total_duration = (time.perf_counter() - total_start) * 1000
            trace = AgentTrace(
                trace_id=trace_id,
                user_input=user_message,
                steps=steps,
                total_duration_ms=total_duration,
                final_intent=intent_result.intent.value,
                final_confidence=intent_result.confidence,
                selected_flow=selected_flow,
                selected_prompt=selected_prompt,
                final_response=message.content[:100],
                reasoning=reasoning,
                tool_calls=tool_calls,
                session_id=session_id,
                current_state="",
                waiting_for="",
                collected_slots={},
                suspended_flows=list(session.suspended_flows),
                retry_count=session.retry_count,
            )

            log_trace(trace)
            message.metadata = _build_metadata(
                session=session, intent_result=intent_result, intent_desc=intent_desc,
                selected_flow=selected_flow, selected_prompt=selected_prompt,
                trace_id=trace_id, duration_ms=total_duration, session_id=session_id,
                tool_calls=tool_calls,
                existing_metadata=message.metadata,
            )
            return AgentResult(message=message, intent_result=intent_result, trace=trace)

    # ===== FSM 流程处理 =====
    if slot_result and not slot_result.ready:
        # Slot 未就绪 → 用 LLM 人格化追问（情绪共鸣 + 安抚 + 追问）
        humanized_prompt = await _humanize_slot_prompt(
            user_input=user_message,
            raw_prompt=slot_result.prompt,
            flow_name=session.current_flow,
            waiting_for=slot_result.waiting_for,
            history=history,
        )
        message = Message(
            role=MessageRole.ASSISTANT,
            content=humanized_prompt,
        )
        session_manager.save(session)
        session.add_history("assistant", humanized_prompt)

        selected_flow = INTENT_FLOW_MAP.get(session.current_flow, "GeneralFlow")
        selected_prompt = FLOW_PROMPT_MAP.get(selected_flow, "unknown")

        reasoning = _generate_reasoning(
            user_input=user_message,
            intent_result=intent_result,
            intent_desc=intent_desc,
            session_resumed=session_resumed,
            session_flow=session.current_flow,
            session_state=session.current_state,
            slot_filling=slot_result,
        )

        total_duration = (time.perf_counter() - total_start) * 1000
        trace = AgentTrace(
            trace_id=trace_id,
            user_input=user_message,
            steps=steps,
            total_duration_ms=total_duration,
            final_intent=session.current_flow,
            final_confidence=intent_result.confidence if intent_result else 1.0,
            selected_flow=selected_flow,
            selected_prompt=selected_prompt,
            final_response=message.content[:100],
            reasoning=reasoning,
            tool_calls=[],
            session_id=session_id,
            current_state=session.current_state,
            waiting_for=session.waiting_for,
            collected_slots=session.slots,
            suspended_flows=list(session.suspended_flows),
            retry_count=session.retry_count,
        )

        log_trace(trace)
        message.metadata = {
            "intent": session.current_flow,
            "confidence": intent_result.confidence if intent_result else 1.0,
            "intent_desc": intent_desc,
            "selected_flow": selected_flow,
            "selected_prompt": selected_prompt,
            "trace_id": trace_id,
            "duration_ms": round(total_duration),
            "session_id": session_id,
            "fsm_state": session.current_state,
            "waiting_for": session.waiting_for,
        }
        return AgentResult(message=message, intent_result=intent_result, trace=trace)

    # ===== Slot Ready → 执行 Flow（含 Tool Calling）=====
    if slot_result and slot_result.ready:
        flow_name = session.current_flow
        selected_flow = INTENT_FLOW_MAP.get(flow_name, "GeneralFlow")
        selected_prompt = FLOW_PROMPT_MAP.get(selected_flow, "unknown")

        # 构建带 Slot 参数的 IntentResult
        effective_intent = IntentType(flow_name) if flow_name in [e.value for e in IntentType] else IntentType.GENERAL
        effective_intent_result = IntentResult(
            intent=effective_intent,
            confidence=intent_result.confidence if intent_result else 1.0,
            raw_input=user_message,
        )

        # 调用 Flow（带 slot 参数）
        step_flow_start = time.perf_counter()
        route_result = await route(effective_intent_result, history, slots=slot_result.slots)
        step_flow_duration = (time.perf_counter() - step_flow_start) * 1000

        tool_calls = route_result.tool_calls

        steps.append(TraceStep(
            step_type=TraceStepType.FLOW_EXECUTION,
            name=selected_flow,
            duration_ms=step_flow_duration,
            input_data={"user_input": user_message[:100], "slots": slot_result.slots},
            output_data={
                "prompt": selected_prompt,
                "response_preview": route_result.message.content[:100],
            },
        ))

        if route_result.tool_calls:
            for tc in route_result.tool_calls:
                steps.append(TraceStep(
                    step_type=TraceStepType.TOOL_CALL,
                    name=tc.get("tool_name", "unknown_tool"),
                    duration_ms=0,
                    input_data=tc.get("tool_input", {}),
                    output_data=tc.get("tool_output", {}),
                    metadata={"success": tc.get("success", False)},
                ))

        # 流程完成 → 检查是否有挂起的 Flow 需要提示恢复
        message_content = route_result.message.content
        if session.has_suspended_flow():
            suspended = session.suspended_flows[-1]
            flow_name_cn = {
                "refund": "退款", "logistics_query": "物流查询",
                "order_query": "订单查询", "product_query": "商品咨询",
            }
            suspended_name = flow_name_cn.get(suspended["flow_name"], suspended["flow_name"])
            message_content += f"\n\n您之前的{suspended_name}流程还没完成，需要继续吗？"

        message = Message(role=MessageRole.ASSISTANT, content=message_content)
        session.add_history("assistant", message_content)
        session.current_state = "DONE"
        session.clear_flow()
        session_manager.save(session)

        reasoning = _generate_reasoning(
            user_input=user_message,
            intent_result=intent_result,
            intent_desc=intent_desc,
            session_resumed=session_resumed,
            session_flow=flow_name,
            session_state="PROCESSING",
            slot_filling=slot_result,
            tool_calls=tool_calls,
        )

        total_duration = (time.perf_counter() - total_start) * 1000
        trace = AgentTrace(
            trace_id=trace_id,
            user_input=user_message,
            steps=steps,
            total_duration_ms=total_duration,
            final_intent=flow_name,
            final_confidence=intent_result.confidence if intent_result else 1.0,
            selected_flow=selected_flow,
            selected_prompt=selected_prompt,
            final_response=message.content[:100],
            reasoning=reasoning,
            tool_calls=tool_calls,
            session_id=session_id,
            current_state="DONE",
            waiting_for="",
            collected_slots=slot_result.slots,
            suspended_flows=list(session.suspended_flows),
            retry_count=session.retry_count,
        )

        log_trace(trace)
        meta = _build_metadata(
            session=session, intent_result=intent_result, intent_desc=intent_desc,
            selected_flow=selected_flow, selected_prompt=selected_prompt,
            trace_id=trace_id, duration_ms=total_duration, session_id=session_id,
            tool_calls=tool_calls,
        )
        meta["fsm_state"] = "DONE"
        meta["collected_slots"] = slot_result.slots
        message.metadata = meta
        return AgentResult(message=message, intent_result=intent_result, trace=trace)

    # ===== Fallback（不应到达）=====
    message = Message(role=MessageRole.ASSISTANT, content="抱歉，系统遇到问题，请重试。")
    total_duration = (time.perf_counter() - total_start) * 1000
    trace = AgentTrace(
        trace_id=trace_id,
        user_input=user_message,
        steps=steps,
        total_duration_ms=total_duration,
        final_intent="general",
        final_confidence=0.0,
        selected_flow="GeneralFlow",
        selected_prompt="system_prompt",
        final_response=message.content,
        reasoning="Fallback: 未匹配到任何处理路径",
        session_id=session_id,
    )
    log_trace(trace)
    return AgentResult(message=message, intent_result=None, trace=trace)
