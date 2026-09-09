"""
Agent Trace Logger - 结构化追踪日志

职责：
- 将 AgentTrace 格式化为企业级控制台日志
- 统一日志格式，杜绝 print 混乱输出
- 提供清晰的 Agent 执行链路可视化

设计理念：
- 日志格式统一，模块化标签（[IntentClassifier]、[AgentRouter] 等）
- 使用标准 logging 模块，不用 print
- 单一输出入口：trace 完成后一次性输出，避免日志交错
- 结构化数据 + 人类可读格式并存

架构位置：
- core/ 层基础设施，被 agents/agent.py 调用
- 不包含业务逻辑，纯日志格式化

为什么企业项目需要 Trace Logger：
1. 统一格式：所有开发者看到相同格式的日志
2. 模块标签：快速定位是哪个组件输出的
3. 可检索：结构化日志可被 ELK/Datadog 等采集
4. 可配置：生产环境可关闭详细 trace

扩展规划：
- Phase 3: 增加 tool_call 步骤的格式化
- Phase 4: 支持输出到 OpenTelemetry Span
- Phase 5: 支持输出到 LangSmith / LangFuse
"""

import logging
from app.schemas.trace import AgentTrace, TraceStep, TraceStepType

# 专用 logger，可独立配置级别和处理器
logger = logging.getLogger("agent.trace")


def log_trace(trace: AgentTrace) -> None:
    """
    将完整的 AgentTrace 格式化输出到控制台

    输出格式示例：
    ╔══════════════════════════════════════════
    ║ Agent Trace [trace_id]
    ╠══════════════════════════════════════════
    ║ Input: 我的耳机坏了，我想退款
    ╠──────────────────────────────────────────
    ║ [IntentClassifier]        320ms
    ║   intent = refund
    ║   confidence = 0.96
    ╠──────────────────────────────────────────
    ║ [AgentRouter]             2ms
    ║   selected_flow = RefundFlow
    ╠──────────────────────────────────────────
    ║ [FlowHandler]             1200ms
    ║   prompt = refund_prompt
    ║   response = 好的，我理解您需要...
    ╠══════════════════════════════════════════
    ║ Total: 1522ms
    ╚══════════════════════════════════════════

    Args:
        trace: 完整的 Agent 执行追踪数据
    """
    lines = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════")
    lines.append(f"║ Agent Trace [{trace.trace_id}]")
    lines.append("╠══════════════════════════════════════════════════════")
    lines.append(f"║ Input: {trace.user_input[:80]}")

    for step in trace.steps:
        lines.append("╠──────────────────────────────────────────────────────")
        lines.append(f"║ [{step.name}]  {step.duration_ms:.0f}ms")
        _format_step_details(step, lines)

    # Reasoning 块
    if trace.reasoning:
        lines.append("╠──────────────────────────────────────────────────────")
        lines.append("║ [Reasoning]")
        for reasoning_line in trace.reasoning.split("\n"):
            lines.append(f"║   {reasoning_line}")

    lines.append("╠══════════════════════════════════════════════════════")
    lines.append(f"║ Total: {trace.total_duration_ms:.0f}ms")
    lines.append("╚══════════════════════════════════════════════════════")

    # 一次性输出，避免多行日志交错
    logger.info("\n".join(lines))


def _format_step_details(step: TraceStep, lines: list[str]) -> None:
    """
    格式化单个步骤的详细信息

    根据步骤类型，选择性输出关键字段。

    Args:
        step: Trace 步骤
        lines: 输出行列表（原地追加）
    """
    if step.step_type == TraceStepType.INTENT_CLASSIFICATION:
        intent = step.output_data.get("intent", "unknown")
        confidence = step.output_data.get("confidence", 0.0)
        lines.append(f"║   intent = {intent}")
        lines.append(f"║   confidence = {confidence:.2f}")

    elif step.step_type == TraceStepType.ROUTING:
        flow = step.output_data.get("selected_flow", "unknown")
        downgraded = step.output_data.get("downgraded", False)
        lines.append(f"║   selected_flow = {flow}")
        if downgraded:
            original = step.output_data.get("original_intent", "")
            lines.append(f"║   ⚠ downgraded from {original} (low confidence)")

    elif step.step_type == TraceStepType.FLOW_EXECUTION:
        prompt = step.output_data.get("prompt", "unknown")
        response_preview = step.output_data.get("response_preview", "")
        lines.append(f"║   prompt = {prompt}")
        lines.append(f"║   response = {response_preview[:60]}")

    elif step.step_type == TraceStepType.TOOL_CALL:
        success = step.metadata.get("success", False)
        status = "✅" if success else "❌"
        lines.append(f"║   {status} tool = {step.name}")
        if step.input_data:
            lines.append(f"║   input = {step.input_data}")
        if step.output_data:
            output_preview = str(step.output_data)[:100]
            lines.append(f"║   output = {output_preview}")

    # 通用 metadata 输出（跳过已处理的）
    skip_keys = {"success"}
    for key, value in step.metadata.items():
        if key not in skip_keys:
            lines.append(f"║   [{key}] = {value}")
