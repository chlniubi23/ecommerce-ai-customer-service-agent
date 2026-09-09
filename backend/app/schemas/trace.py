"""
Agent Execution Trace Schema - Agent 执行追踪数据结构

职责：
- 定义 Agent 完整执行链路的结构化数据
- 记录每个决策步骤的输入、输出和耗时
- 为前端 Debug Panel 和后端日志提供统一数据源

设计理念：
- 每次 Agent 执行生成一个完整的 AgentTrace
- Trace 内部按步骤（Step）记录，每步有类型、耗时、结果
- 所有字段强类型化，可序列化为 JSON 传给前端
- 预留扩展字段，后续支持 Tool Calling、LangGraph、Multi-Agent

架构位置：
- schemas/ 层，被 agents/agent.py 构建
- 被 api/ 层序列化为 JSON 返回前端
- 被 trace logger 格式化为控制台日志

为什么企业项目需要 Trace：
1. 可观测性：Agent 内部"黑箱"变"白盒"，每步可审计
2. 调试效率：问题定位从"猜"变为"查"
3. 性能分析：每步耗时可测量，瓶颈可定位
4. 合规审计：决策过程有据可查
5. 后续集成 OpenTelemetry / LangSmith 等可观测平台

扩展规划：
- Phase 3 (Tool Calling): steps 中增加 tool_call 类型
- Phase 4 (LangGraph): steps 映射到 Graph 的 node 执行
- Phase 5 (Multi-Agent): 增加 agent_id 标识哪个 Agent 执行
- Phase 6: 持久化到数据库，支持回放和分析
"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Any


class TraceStepType(str, Enum):
    """
    Trace 步骤类型

    标识 Agent 执行链路中每一步的类别。

    当前支持：
    - INTENT_CLASSIFICATION: 意图分类步骤
    - ROUTING: 路由决策步骤
    - FLOW_EXECUTION: Flow 执行步骤（含 Prompt + LLM 调用）

    扩展规划：
    - TOOL_CALL: 工具调用步骤
    - RAG_RETRIEVAL: RAG 检索步骤
    - MEMORY_LOAD: 记忆加载步骤
    - REASONING: 推理/思考步骤
    - AGENT_DELEGATION: 多 Agent 委派步骤
    """
    INTENT_CLASSIFICATION = "intent_classification"
    ROUTING = "routing"
    FLOW_EXECUTION = "flow_execution"
    TOOL_CALL = "tool_call"
    TOOL_DECISION = "tool_decision"
    WORKFLOW = "workflow"
    RAG_RETRIEVAL = "rag_retrieval"


class TraceStep(BaseModel):
    """
    单个 Trace 步骤

    记录 Agent 执行链路中某一步的完整信息。

    Attributes:
        step_type: 步骤类型（分类/路由/执行）
        name: 步骤名称（人类可读）
        duration_ms: 步骤耗时（毫秒）
        input_data: 步骤输入数据
        output_data: 步骤输出数据
        metadata: 扩展元信息（后续 Tool Calling / RAG 等）

    使用示例：
        TraceStep(
            step_type=TraceStepType.INTENT_CLASSIFICATION,
            name="IntentClassifier",
            duration_ms=320,
            input_data={"user_input": "我要退款"},
            output_data={"intent": "refund", "confidence": 0.96},
        )
    """
    step_type: TraceStepType = Field(
        ...,
        description="步骤类型"
    )
    name: str = Field(
        ...,
        description="步骤名称（如 IntentClassifier, AgentRouter, RefundFlow）"
    )
    duration_ms: float = Field(
        default=0.0,
        description="步骤执行耗时（毫秒）"
    )
    input_data: dict[str, Any] = Field(
        default_factory=dict,
        description="步骤输入（结构化数据）"
    )
    output_data: dict[str, Any] = Field(
        default_factory=dict,
        description="步骤输出（结构化数据）"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="扩展元信息（tool_calls, reasoning 等）"
    )


class AgentTrace(BaseModel):
    """
    Agent 完整执行追踪

    一次 Agent 调用的完整执行链路记录。
    包含输入、各步骤详情、最终输出和总耗时。

    Attributes:
        trace_id: 追踪唯一标识（与响应 trace_id 一致）
        user_input: 用户原始输入
        steps: 执行步骤列表（按时间顺序）
        total_duration_ms: 总耗时（毫秒）
        final_intent: 最终决策的意图类型
        final_confidence: 最终置信度
        selected_flow: 选中的 Flow 名称
        selected_prompt: 使用的 Prompt 标识
        final_response: AI 最终回复（截取前 100 字）

    扩展规划：
    - Phase 3: 增加 tool_calls 字段
    - Phase 4: 增加 workflow_graph 字段（LangGraph 可视化）
    - Phase 5: 增加 memory_state 字段
    - Phase 6: 增加 agent_id（Multi-Agent 场景）
    """
    trace_id: str = Field(
        ...,
        description="追踪唯一 ID"
    )
    user_input: str = Field(
        ...,
        description="用户原始输入"
    )
    steps: list[TraceStep] = Field(
        default_factory=list,
        description="执行步骤列表（时间顺序）"
    )
    total_duration_ms: float = Field(
        default=0.0,
        description="Agent 总耗时（毫秒）"
    )

    # ===== 决策摘要（方便快速查看）=====
    final_intent: str = Field(
        default="",
        description="最终决策的意图类型"
    )
    final_confidence: float = Field(
        default=0.0,
        description="意图分类置信度"
    )
    selected_flow: str = Field(
        default="",
        description="选中的 Flow Handler 名称"
    )
    selected_prompt: str = Field(
        default="",
        description="使用的 Prompt 标识"
    )
    final_response: str = Field(
        default="",
        description="AI 最终回复（截取前 100 字）"
    )

    # ===== Reasoning =====
    reasoning: str = Field(
        default="",
        description="Agent 内部推理摘要（解释为什么做出此决策）"
    )

    # ===== Tool Calls =====
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="工具调用记录列表"
    )

    # ===== Session / FSM =====
    session_id: str = Field(
        default="",
        description="会话 ID"
    )
    current_state: str = Field(
        default="",
        description="FSM 当前状态"
    )
    waiting_for: str = Field(
        default="",
        description="当前等待的 Slot"
    )
    collected_slots: dict[str, Any] = Field(
        default_factory=dict,
        description="已收集的 Slot 值"
    )

    # ===== Interrupt / Recovery =====
    suspended_flows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="被挂起的 Flow 快照列表"
    )
    retry_count: int = Field(
        default=0,
        description="当前 Slot 连续无效输入次数"
    )

    # ===== 扩展预留 =====
    # Phase 5+
    # workflow_steps: list[dict] = Field(default_factory=list)
    # memory_state: dict = Field(default_factory=dict)
    # agent_id: str = Field(default="main")
