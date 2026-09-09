"""
LLM 服务模块 - 纯 LLM 调用层

职责：
- 封装 OpenAI API 调用
- 提供通用 call_llm() 供所有 Flow 使用
- 保留 get_chat_response() 供 API 层直接调用（Agent 模式）
- 不包含任何业务逻辑

架构位置：
- services/ 最底层，被 flows/ 和 agents/ 调用
- 只负责：组装消息 → 调 API → 返回结果
- 不知道上层是什么 Flow，不知道 Prompt 内容

为什么拆出 call_llm()：
- Phase 1 只有一个 SYSTEM_PROMPT，写死在这里没问题
- Phase 2 每个 Flow 有自己的 Prompt，需要外部传入 system_prompt
- call_llm() 是纯函数：system_prompt + user_message + history → content
- 所有 Flow 复用同一个 LLM 调用通道

扩展规划：
- Phase 3 (Tool Calling): call_llm() 增加 tools 参数
- Phase 3 (RAG): Flow 层注入 context 到 system_prompt
- Phase 4 (LangGraph): 被 Graph Node 调用
"""

import contextvars
import logging
from typing import Callable

from openai import AsyncOpenAI
from app.core.config import get_settings
from app.models.message import Message, MessageRole
from app.services.response_style import sanitize_reply, with_style_directive

logger = logging.getLogger(__name__)

# 获取全局配置
settings = get_settings()

# 初始化 OpenAI 异步客户端
# 使用 AsyncOpenAI 支持 FastAPI 的异步特性，提升并发性能
# 全局单例，所有调用共享连接池
client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    timeout=settings.openai_timeout,
    max_retries=settings.openai_max_retries,
)


# ===== 流式支持 =====
# SSE 端点在请求上下文里注入回调；call_llm 检测到回调后自动切换为流式调用，
# 逐段回调输出、最终仍返回清洗后的完整文本。用 ContextVar 而非改函数签名：
# 所有 Flow 共用 call_llm 通道，Flow 层零改动即获得真流式。
StreamCallback = Callable[[str], None]
stream_callback: contextvars.ContextVar[StreamCallback | None] = contextvars.ContextVar(
    "llm_stream_callback", default=None
)


def _build_messages(system_prompt: str, user_message: str, history: list[dict]) -> list[dict]:
    """组装消息列表：system prompt（注入口语化风格指令）+ 历史 + 当前消息。"""
    messages = [{"role": "system", "content": with_style_directive(system_prompt)}]
    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })
    messages.append({
        "role": "user",
        "content": user_message,
    })
    return messages


# LLM 调用结果数据类
# 将 Message、model、usage 打包返回给 API 层
class LLMResult:
    """
    LLM 调用结果

    内部数据类，仅在 service 与 api 之间传递。
    不直接暴露给前端，由 API 层转换为标准响应。

    Attributes:
        message: AI 回复的 Message 对象
        model: 实际使用的模型名称
        usage: Token 使用统计
    """
    def __init__(self, message: Message, model: str, usage: dict | None = None):
        self.message = message
        self.model = model
        self.usage = usage


async def call_llm(
    system_prompt: str,
    user_message: str,
    history: list[dict] = [],
    temperature: float = 0.7,
    max_tokens: int = 800,
) -> str:
    """
    通用 LLM 调用函数

    纯函数式设计：传入 Prompt + 消息，返回文本。
    所有 Flow Handler 通过此函数调用 LLM。

    Args:
        system_prompt: 系统提示词（由各 Flow 的 Prompt 文件提供）
        user_message: 用户当前输入
        history: 对话历史（dict 列表，含 role + content）
        temperature: 生成温度，默认 0.7
        max_tokens: 最大 token 数，默认 2000

    Returns:
        str: LLM 生成的文本回复

    Raises:
        Exception: OpenAI API 调用失败时抛出

    扩展规划：
    - Phase 3: 增加 tools / tool_choice 参数
    """
    messages = _build_messages(system_prompt, user_message, history)
    callback = stream_callback.get()

    if callback is not None:
        # 流式模式：逐段回调给 SSE 端点，函数本身仍返回清洗后的完整文本，
        # Flow / 会话历史的处理逻辑与非流式完全一致
        stream = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        raw_content = ""
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                raw_content += delta
                callback(delta)
        content = sanitize_reply(raw_content)
        logger.debug(f"LLM 流式返回 {len(content)} 字符")
        return content

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    raw_content = response.choices[0].message.content or ""
    # 兜底清洗：去掉残留的 markdown 符号，保证前端纯文本展示
    content = sanitize_reply(raw_content)
    logger.debug(f"LLM 返回 {len(content)} 字符（清洗前 {len(raw_content)}）")
    return content


async def get_chat_response(
    message: str,
    history: list[dict] = [],
    system_prompt: str | None = None,
) -> LLMResult:
    """
    获取聊天回复（含完整元信息）

    供 Agent 主入口调用，返回 LLMResult（含 Message + model + usage）。
    内部调用 OpenAI API 并解析完整响应。

    与 call_llm() 的区别：
    - call_llm() 返回纯文本，供 Flow 使用
    - get_chat_response() 返回 LLMResult，供 API 层使用（需要 model/usage）

    Args:
        message: 用户当前输入
        history: 对话历史
        system_prompt: 系统提示词（可选，为 None 时使用默认）

    Returns:
        LLMResult: 包含 Message、模型名称、token 用量
    """
    from app.prompts.system import SYSTEM_PROMPT as DEFAULT_PROMPT

    prompt = system_prompt or DEFAULT_PROMPT

    messages = _build_messages(prompt, message, history)

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=0.7,
        max_tokens=800,
    )

    choice = response.choices[0]
    usage = None
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    reply_message = Message(
        role=MessageRole.ASSISTANT,
        content=sanitize_reply(choice.message.content or ""),
    )

    return LLMResult(
        message=reply_message,
        model=response.model,
        usage=usage,
    )
