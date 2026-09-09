"""
企业级 AI Message 数据模型

职责：
- 定义标准化的消息数据结构
- 支持前后端一致的消息协议
- 预留 Agent 系统所需的扩展字段

设计理念：
- Message 是整个 Agent 系统的核心数据单元
- 所有消息（用户输入、AI 回复、Tool 结果、System 指令）都用同一结构
- 通过 type 字段区分消息用途，通过 metadata 携带扩展信息
- 当前阶段只使用基础字段，扩展字段全部 Optional，不影响现有逻辑

架构位置：
- 模型层核心，被 services/、api/、前端 types/ 共同引用
- 替代原有 chat.py 中的 ChatMessage

为什么企业项目需要这样设计：
1. id 字段：消息持久化、去重、前端 key 绑定的基础
2. type 字段：Tool Calling 返回 tool 类型消息，Agent 返回 reasoning 类型
3. timestamp 统一 ISO 格式：前后端时区一致，数据库可直接存储
4. metadata 字典：任意扩展信息的载体，不需要改模型结构
5. status 字段：流式响应、长时间 Tool 调用时标记消息状态

扩展路径：
- Phase 2 (Tool Calling):
    type="tool" 的消息携带工具调用结果
    metadata 增加 tool_name, tool_input, tool_output
- Phase 3 (RAG):
    metadata 增加 sources（引用来源列表）
- Phase 4 (LangGraph):
    metadata 增加 node_name（当前执行节点）
    type="reasoning" 用于展示思维链
- Phase 5 (Memory):
    通过 id + session_id 实现消息持久化
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """
    消息角色枚举

    定义消息的发送者身份。
    遵循 OpenAI Chat Completion API 规范。

    Values:
        USER: 用户发送的消息
        ASSISTANT: AI 助手的回复
        SYSTEM: 系统指令（如 system prompt）

    扩展规划：
    - Phase 2: 增加 TOOL = "tool"（工具执行结果）
    """
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(str, Enum):
    """
    消息类型枚举

    区分消息的语义用途。
    同一个 role 可以有不同 type。

    例如 role=assistant 的消息：
    - type=text: 普通文本回复
    - type=tool_call: 发起工具调用（Phase 2）
    - type=reasoning: 思维链展示（Phase 4）

    Values:
        TEXT: 普通文本消息（当前阶段唯一使用的类型）

    扩展规划：
    - Phase 2: TOOL_CALL = "tool_call"（AI 发起工具调用）
    - Phase 2: TOOL_RESULT = "tool_result"（工具返回结果）
    - Phase 4: REASONING = "reasoning"（Agent 推理过程）
    """
    TEXT = "text"


class MessageStatus(str, Enum):
    """
    消息状态枚举

    标记消息在处理流程中的当前状态。
    用于前端展示加载态、错误态等。

    Values:
        COMPLETED: 消息已完成（当前阶段所有消息都是此状态）

    扩展规划：
    - Phase 2: PENDING = "pending"（等待 Tool 执行）
    - Phase 2: STREAMING = "streaming"（流式输出中）
    - ERROR = "error"（处理失败）
    """
    COMPLETED = "completed"


class Message(BaseModel):
    """
    标准 AI Message 模型

    整个 Agent 系统的核心数据单元。
    前后端共用同一结构定义，确保数据一致性。

    基础字段（当前阶段使用）：
        id: 消息唯一标识
        role: 消息角色
        type: 消息类型
        content: 消息文本内容
        timestamp: 消息创建时间
        status: 消息状态

    扩展字段（当前阶段预留，全部 Optional）：
        metadata: 扩展信息字典

    使用示例：
        # 用户消息
        Message(role="user", content="怎么退货？")

        # AI 回复
        Message(role="assistant", content="您好，退货流程如下...")

        # 未来 Tool 消息
        Message(
            role="assistant",
            type="tool_call",
            content="正在查询订单...",
            metadata={"tool_name": "query_order", "tool_input": {"order_id": "123"}}
        )
    """

    # ========== 基础字段 ==========

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:16],
        description="消息唯一标识，16位十六进制字符串。用于持久化、去重、前端 key 绑定"
    )

    role: MessageRole = Field(
        ...,
        description="消息角色：user / assistant / system"
    )

    type: MessageType = Field(
        default=MessageType.TEXT,
        description="消息类型：text / tool_call / tool_result / reasoning"
    )

    content: str = Field(
        ...,
        min_length=0,
        max_length=50000,
        description="消息文本内容"
    )

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="消息创建时间，ISO 8601 UTC 格式"
    )

    status: MessageStatus = Field(
        default=MessageStatus.COMPLETED,
        description="消息状态：completed / pending / streaming / error"
    )

    # ========== 扩展字段 ==========

    metadata: Optional[dict] = Field(
        default=None,
        description=(
            "扩展元信息。当前阶段可选，未来用于携带：\n"
            "- tool_name / tool_input / tool_output (Tool Calling)\n"
            "- sources (RAG 引用来源)\n"
            "- node_name (LangGraph 节点)\n"
            "- reasoning_steps (思维链)"
        )
    )


class AgentTraceData(BaseModel):
    """
    Agent Trace 摘要数据（传给前端 Debug Panel）

    仅包含前端展示所需的关键字段，不传完整 trace steps。
    完整 trace 保留在后端日志中。

    Attributes:
        trace_id: 追踪唯一 ID
        intent: 识别的意图类型
        confidence: 置信度
        selected_flow: 选中的 Flow
        selected_prompt: 使用的 Prompt
        duration_ms: 总耗时（毫秒）
        intent_desc: 意图中文描述

    扩展规划：
    - Phase 3: 增加 tool_calls 列表
    - Phase 4: 增加 workflow_steps
    - Phase 5: 增加 reasoning
    """
    trace_id: str = Field(..., description="追踪唯一 ID")
    intent: str = Field(..., description="识别的意图类型")
    confidence: float = Field(..., description="意图置信度")
    selected_flow: str = Field(..., description="选中的 Flow Handler")
    selected_prompt: str = Field(..., description="使用的 Prompt 标识")
    duration_ms: int = Field(..., description="Agent 总耗时（毫秒）")
    intent_desc: str = Field(default="", description="意图中文描述")
    reasoning: str = Field(default="", description="Agent 内部推理摘要")
    tool_calls: list[dict] = Field(default_factory=list, description="工具调用记录")
    session_id: str = Field(default="", description="会话 ID")
    current_state: str = Field(default="", description="FSM 当前状态")
    waiting_for: str = Field(default="", description="当前等待的 Slot")
    collected_slots: dict = Field(default_factory=dict, description="已收集的 Slot 值")
    suspended_flows: list = Field(default_factory=list, description="被挂起的 Flow 列表")
    retry_count: int = Field(default=0, description="当前 Slot 重试次数")
    # Phase 5.3: Memory + Context 增强字段
    memory_count: int = Field(default=0, description="注入 Prompt 的历史消息数")
    retrieval_query: str = Field(default="", description="实际用于 RAG 检索的增强 Query")
    rag_used: bool = Field(default=False, description="是否使用了 RAG 回答")
    rag_chunks: int = Field(default=0, description="RAG 检索到的 chunk 数")
    rag_sources: list[str] = Field(default_factory=list, description="RAG 来源文档列表")
    # Phase 5.4: Tool Calling 增强字段
    selected_tool: str = Field(default="", description="选中的工具名称")
    tool_args: dict = Field(default_factory=dict, description="工具调用参数")
    tool_result: dict = Field(default_factory=dict, description="工具返回结果")
    tool_latency_ms: float = Field(default=0.0, description="工具执行耗时（毫秒）")
    tool_success: bool = Field(default=False, description="工具执行是否成功")
    tool_error: str = Field(default="", description="工具执行错误信息")
    workflow_steps: int = Field(default=0, description="Workflow 执行步骤数")


class ChatData(BaseModel):
    """
    聊天响应业务数据

    替代原有 ChatResponse 中的平铺字段。
    作为 BaseResponse[ChatData] 中 data 字段的类型。

    Attributes:
        reply: AI 回复的 Message 对象（完整消息结构）
        trace: Agent 执行追踪摘要（可选，开发模式返回）

    设计说明：
    - reply 使用完整 Message 对象而非纯文本
    - trace 仅开发模式返回，生产环境可省略
    - 前端收到后可直接追加到消息列表，无需再构造 Message

    扩展规划：
    - Phase 3: 增加 tool_outputs 字段（工具执行结果列表）
    - Phase 4: 增加 workflow_steps 字段（工作流执行步骤）
    """
    reply: Message = Field(
        ...,
        description="AI 回复的完整消息对象"
    )
    trace: Optional[AgentTraceData] = Field(
        default=None,
        description="Agent 执行追踪摘要（开发模式返回）"
    )
