"""
Enhanced Flow Execution Engine

职责：
- 增强单 Agent 工作能力：多工具编排、失败重试、上下文增强
- 为每个 Flow 提供 retry + fallback + multi-tool 能力
- 自动根据工具结果决定是否需要补充查询

设计理念：
- 装饰器模式，不修改现有 Flow 代码
- 失败自动重试（最多2次），换参数/换工具
- 工具结果不够丰富时，自动补充关联查询
- 所有增强对上层透明
"""

import logging
import time
from typing import Any

from app.flows.base import FlowResult
from app.models.message import Message, MessageRole
from app.services.llm import call_llm
from app.tools.executors.tool_executor import tool_executor, ToolExecutionResult
from app.tools.tool_registry import tool_registry

logger = logging.getLogger(__name__)

# 工具间的关联关系：当一个工具调用成功后，可自动补充哪些关联工具
TOOL_ENRICHMENT_MAP = {
    "query_order": ["logistics_query"],       # 查订单时自动补充物流
    "logistics_query": ["query_order"],       # 查物流时自动补充订单状态
    "refund_apply": ["query_order"],          # 退款时自动补充订单信息
    "complaint_create": ["query_order"],      # 投诉时自动补充订单信息
}

# 工具失败时的降级策略
TOOL_FALLBACK_MAP = {
    "logistics_query": "query_order",  # 物流查不到，降级查订单
    "refund_apply": "query_order",     # 退款失败，降级查订单确认状态
}

MAX_RETRY = 2


async def enhanced_tool_execute(
    tool_name: str,
    params: dict[str, Any],
    enrich: bool = True,
) -> tuple[list[ToolExecutionResult], str]:
    """
    增强工具执行：重试 + 降级 + 自动补充关联数据

    Returns:
        (所有工具结果列表, 合并后的上下文字符串)
    """
    results: list[ToolExecutionResult] = []
    context_parts: list[str] = []

    # 主工具执行（带重试）
    main_result = await _execute_with_retry(tool_name, params)
    results.append(main_result)

    if main_result.success:
        context_parts.append(main_result.to_context_string())

        # 自动补充关联数据
        if enrich and tool_name in TOOL_ENRICHMENT_MAP:
            order_id = params.get("order_id", "")
            if order_id:
                for enrich_tool_name in TOOL_ENRICHMENT_MAP[tool_name]:
                    enrich_result = await tool_executor.execute_by_name(
                        enrich_tool_name, order_id=order_id
                    )
                    if enrich_result.success:
                        results.append(enrich_result)
                        context_parts.append(enrich_result.to_context_string())
                        logger.info(f"[EnhancedFlow] 自动补充 {enrich_tool_name} 成功")
    else:
        # 主工具失败 → 尝试降级工具
        fallback_name = TOOL_FALLBACK_MAP.get(tool_name)
        if fallback_name and "order_id" in params:
            logger.info(f"[EnhancedFlow] {tool_name} 失败，降级到 {fallback_name}")
            fallback_result = await tool_executor.execute_by_name(
                fallback_name, order_id=params["order_id"]
            )
            results.append(fallback_result)
            if fallback_result.success:
                context_parts.append(fallback_result.to_context_string())
                context_parts.append(f"[注意] {tool_name} 查询失败({main_result.error})，已用 {fallback_name} 补充信息")
            else:
                context_parts.append(f"[工具调用失败] {tool_name}: {main_result.error}")
        else:
            context_parts.append(f"[工具调用失败] {tool_name}: {main_result.error}")

    return results, "\n\n".join(context_parts)


async def _execute_with_retry(
    tool_name: str,
    params: dict[str, Any],
) -> ToolExecutionResult:
    """带重试的工具执行"""
    for attempt in range(MAX_RETRY):
        result = await tool_executor.execute_by_name(tool_name, **params)
        if result.success:
            return result
        if attempt < MAX_RETRY - 1:
            logger.warning(
                f"[EnhancedFlow] {tool_name} 第{attempt+1}次失败: {result.error}，重试..."
            )
    return result


ANALYSIS_PROMPT = """你是一位资深电商客服 AI。基于以下工具查询结果，给用户一个简短、口语、像真人客服的回答。

要求：
1. 先一句话给结论（如：货在路上了 / 退款已提交 / 订单正常）
2. 再补最关键的 1-2 条信息（如预计到达、到账时间、异常提醒）
3. 主动发现异常（如已付款超3天未发货、物流停滞）并提醒，但别长篇大论
4. 工具查询失败就如实说，给个替代办法
5. 全程纯文本、不超过几句话，别罗列原始数据

{domain_prompt}"""


async def enhanced_flow_handle(
    user_input: str,
    history: list[dict],
    tool_name: str,
    tool_params: dict[str, Any],
    domain_prompt: str,
    enrich: bool = True,
) -> FlowResult:
    """
    增强版 Flow 处理：多工具 + 重试 + 分析总结

    替代原有 Flow 的简单 tool→LLM 模式，提供：
    - 工具调用带重试和降级
    - 自动补充关联数据
    - LLM 综合分析多工具结果
    """
    start = time.perf_counter()

    # 增强工具执行
    results, context_string = await enhanced_tool_execute(
        tool_name, tool_params, enrich=enrich
    )

    # 构建增强 prompt
    system_prompt = ANALYSIS_PROMPT.format(domain_prompt=domain_prompt)
    user_message = f"{user_input}\n\n{context_string}" if context_string else user_input

    # LLM 综合分析
    content = await call_llm(
        system_prompt=system_prompt,
        user_message=user_message,
        history=history,
        temperature=0.5,
    )

    tool_calls = [r.to_trace_dict() for r in results]
    duration = (time.perf_counter() - start) * 1000
    logger.info(f"[EnhancedFlow] 完成，耗时 {duration:.0f}ms，工具调用 {len(results)} 次")

    return FlowResult(
        message=Message(role=MessageRole.ASSISTANT, content=content),
        tool_calls=tool_calls,
    )
