"""
聊天 API 路由模块

职责：
- 定义 /api/v1/chat 相关的 HTTP 端点
- 处理请求验证和错误捕获
- 调用 Agent 决策引擎获取 AI 回复
- 使用统一 Response Schema 包装返回值

架构位置：
- 路由层（最外层），只负责 HTTP 请求/响应
- 不包含任何业务逻辑，业务逻辑全部在 agents/ 中
- 所有返回值必须经过 success_response / error_response 包装

Phase 2 改造：
- 从直接调用 services/llm.py 改为调用 agents/agent.py
- API 层不再知道 Prompt、Intent、Flow 等细节
- 只负责：接收请求 → 调 Agent → 包装响应

扩展规划：
- Phase 3: 增加 /api/v1/chat/stream 流式响应端点
- Phase 4: 增加 /api/v1/chat/session 会话管理端点
"""

import asyncio
import json
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from app.models.chat import ChatRequest
from app.models.message import ChatData, AgentTraceData
from app.models.base_response import BaseResponse, success_response, error_response
from app.agents.agent import run as agent_run
from app.core.config import get_settings
from app.services.llm import stream_callback

# 配置日志
logger = logging.getLogger(__name__)

# 获取应用配置
settings = get_settings()

# 创建路由器，统一设置路由前缀和标签
router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


@router.post(
    "",
    response_model=BaseResponse[ChatData],
    summary="发送聊天消息",
    description="接收用户消息，经 Agent 决策引擎处理后返回 AI 回复。返回统一信封格式。",
)
async def chat(request: ChatRequest):
    """
    聊天接口（Agent 模式）

    完整流程：
    用户消息 → Agent → Intent Classification → Router → Flow → AI 回复

    完整 API 路径: POST /api/v1/chat

    返回格式:
        成功: { success: true, data: { reply: Message }, error: null, metadata: {...} }
        失败: { success: false, data: null, error: { code, message }, metadata: {...} }

    Message.metadata 中包含 Agent 决策信息：
        - intent: 识别的意图类型
        - confidence: 置信度
        - intent_desc: 意图中文描述

    Args:
        request: 聊天请求体，包含 message 和 history

    Returns:
        BaseResponse[ChatData]: 统一信封包装的聊天响应
    """
    try:
        logger.info(f"收到聊天请求，消息长度: {len(request.message)}")

        # 构建对话历史（转为 dict 列表）
        history = [
            {"role": msg.role.value, "content": msg.content}
            for msg in request.history
        ]

        # 调用 Agent 决策引擎
        # Agent 内部完成: Session → Intent Classification → Router → FSM → Flow → Response
        result = await agent_run(
            user_message=request.message,
            history=history,
            session_id=request.session_id,
        )

        if result.intent_result:
            logger.info(
                f"Agent 回复成功, "
                f"intent={result.intent_result.intent.value}, "
                f"confidence={result.intent_result.confidence:.2f}"
            )
        else:
            logger.info(f"Agent 回复成功 (session resume), flow={result.trace.selected_flow}")

        # 使用统一信封包装成功响应
        return _build_chat_response(result)

    except Exception as e:
        logger.error(f"聊天请求处理失败: {str(e)}", exc_info=True)

        resp = error_response(
            code="AGENT_ERROR",
            message="AI 服务暂时不可用，请稍后重试",
            detail=str(e) if settings.app_debug else None,
        )
        return JSONResponse(
            status_code=500,
            content=resp.model_dump(),
        )


def _build_chat_response(result) -> BaseResponse:
    """组装统一信封（含 Debug 模式的 Trace 摘要），非流式/流式端点共用。"""
    trace_data = None
    if settings.app_debug:
        metadata = result.message.metadata or {}
        trace_data = AgentTraceData(
            trace_id=result.trace.trace_id,
            intent=result.trace.final_intent,
            confidence=result.trace.final_confidence,
            selected_flow=result.trace.selected_flow,
            selected_prompt=result.trace.selected_prompt,
            duration_ms=round(result.trace.total_duration_ms),
            intent_desc=metadata.get("intent_desc", ""),
            reasoning=result.trace.reasoning,
            tool_calls=result.trace.tool_calls,
            session_id=result.trace.session_id,
            current_state=result.trace.current_state,
            waiting_for=result.trace.waiting_for,
            collected_slots=result.trace.collected_slots,
            # Phase 5.3: Memory + Context 增强
            memory_count=metadata.get("memory_count", 0),
            retrieval_query=metadata.get("retrieval_query", ""),
            rag_used=metadata.get("rag_used", False),
            rag_chunks=metadata.get("rag_chunks", 0),
            rag_sources=metadata.get("rag_sources", []),
            # Phase 5.4: Tool Calling 增强
            selected_tool=metadata.get("selected_tool", ""),
            tool_args=metadata.get("tool_args", {}),
            tool_result=metadata.get("tool_result", {}),
            tool_latency_ms=metadata.get("tool_latency_ms", 0.0),
            tool_success=metadata.get("tool_success", False),
            tool_error=metadata.get("tool_error", ""),
            workflow_steps=metadata.get("workflow_steps", 0),
        )

    return success_response(
        data=ChatData(reply=result.message, trace=trace_data),
        model=settings.openai_model,
    )


def _sse(payload: dict) -> str:
    """编码一条 SSE 事件。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post(
    "/stream",
    response_model=None,
    summary="发送聊天消息（SSE 流式）",
    description=(
        "与 POST /api/v1/chat 等价，但以 text/event-stream 返回。"
        "事件序列：start → delta*(LLM 文本增量) → done(完整信封)；失败时 error。"
    ),
)
async def chat_stream(request: ChatRequest):
    """
    流式聊天接口（SSE）。

    Agent 链路（分类/工具/闸门）与非流式完全一致；当最终回复由 LLM 生成时
    （call_llm 通道），token 以 delta 事件实时推送。闸门类模板回复没有
    LLM 增量，直接由 done 事件携带完整内容，前端需两者都兼容。
    """

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        token = stream_callback.set(lambda text: queue.put_nowait(("delta", text)))
        task = asyncio.create_task(agent_run(
            user_message=request.message,
            history=[
                {"role": msg.role.value, "content": msg.content}
                for msg in request.history
            ],
            session_id=request.session_id,
        ))
        getter: asyncio.Task | None = None
        try:
            yield _sse({"type": "start"})
            getter = asyncio.create_task(queue.get())
            while True:
                await asyncio.wait(
                    {task, getter}, return_when=asyncio.FIRST_COMPLETED
                )
                if getter.done():
                    kind, text = getter.result()
                    yield _sse({"type": kind, "text": text})
                    getter = asyncio.create_task(queue.get())
                if task.done():
                    # Agent 已结束：排空剩余增量后收尾
                    getter.cancel()
                    while not queue.empty():
                        kind, text = queue.get_nowait()
                        yield _sse({"type": kind, "text": text})
                    break
            try:
                result = task.result()
            except Exception:
                logger.error("流式聊天请求处理失败", exc_info=True)
                yield _sse({"type": "error", "message": "AI 服务暂时不可用，请稍后重试"})
                return
            yield _sse({"type": "done", "data": _build_chat_response(result).model_dump()})
        finally:
            stream_callback.reset(token)
            if getter is not None and not getter.done():
                getter.cancel()
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
