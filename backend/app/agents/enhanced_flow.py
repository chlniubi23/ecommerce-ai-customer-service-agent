"""
Enhanced Flow Execution Engine

职责：
- 增强单 Agent 工作能力：多工具编排、失败重试、上下文增强
- 为每个 Flow 提供 retry + fallback + multi-tool 能力
- 自动根据工具结果决定是否需要补充查询

多来源信息整合（本轮改造）：
- TOOL_RESULT_CONTRACTS：主工具"回答完整性"契约，主工具成功但缺关键字段时
  自动执行关联工具补全（不因单一来源缺失而答"系统没有"）；
- enrich / 关联工具失败不再静默：向 LLM 上下文追加 [补全失败提示]，
  告知失败并提示可参考页面快照/历史记录；
- 页面快照兜底（A3）：实时查询缺失/失败而前端快照存在时，追加
  [页面快照补充]（来源：用户当前页面）；
- 所有上下文片段标注来源标签（[实时查询] / [补全查询]），供 LLM 交叉核对。

设计理念：
- 装饰器模式，不修改现有 Flow 代码
- 失败自动重试（最多2次），换参数/换工具
- 所有增强对上层透明
"""

import logging
import time
from typing import Any

from app.agents.context_facts import extract_context_facts, snapshot_lines_for_dimensions
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

# 主工具"回答完整性"契约：每个维度列出可接受的字段别名（任一命中即满足该维度）。
# 主工具成功但存在未满足维度 → 触发关联工具补全 + 页面快照兜底（修 D4）。
TOOL_RESULT_CONTRACTS: dict[str, dict[str, list[str]]] = {
    "query_order": {
        # 回答订单状态类问题需要物流信息（logistics/shipment 相关键）
        "logistics": ["logistics", "shipment", "carrier_name", "tracking_no", "current_status"],
        "order_status": ["order_status", "shipping_status", "receipt_status"],
    },
    "logistics_query": {
        # 回答物流问题需要订单状态（或由 enrich 的 query_order 补充）
        "order_status": ["order_status", "shipping_status", "receipt_status"],
    },
    "refund_apply": {
        "order_status": ["order_status", "shipping_status", "receipt_status"],
        "logistics": ["logistics", "shipment", "carrier_name", "tracking_no", "current_status"],
    },
}

# 契约维度中文名（用于失败提示文案）
DIMENSION_LABELS = {
    "logistics": "物流",
    "order_status": "订单状态",
    "refund": "退款",
    "complaint": "投诉",
}

# 工具失败时的降级策略
TOOL_FALLBACK_MAP = {
    "logistics_query": "query_order",  # 物流查不到，降级查订单
    "refund_apply": "query_order",     # 退款失败，降级查订单确认状态
}

MAX_RETRY = 2


def contract_missing_dimensions(tool_name: str, data: dict[str, Any] | None) -> list[str]:
    """检查主工具结果是否满足完整性契约，返回未满足的维度列表。"""
    contracts = TOOL_RESULT_CONTRACTS.get(tool_name)
    if not contracts or not isinstance(data, dict):
        return []
    keys = set(data.keys())
    # 兼容嵌套结构：logistics/shipment 子 dict 的键也算顶层可用
    for nested_key in ("logistics", "shipment"):
        nested = data.get(nested_key)
        if isinstance(nested, dict):
            keys.update(nested.keys())
    missing = []
    for dimension, aliases in contracts.items():
        if not any(alias in keys for alias in aliases):
            missing.append(dimension)
    return missing


async def enhanced_tool_execute(
    tool_name: str,
    params: dict[str, Any],
    enrich: bool = True,
    page_facts: dict[str, str] | None = None,
) -> tuple[list[ToolExecutionResult], str]:
    """
    增强工具执行：重试 + 降级 + 完整性契约补全 + 页面快照兜底

    Args:
        tool_name: 主工具名
        params: 主工具参数
        enrich: 是否启用关联补全
        page_facts: 前端页面快照事实（extract_context_facts 的返回值，兜底来源）

    Returns:
        (所有工具结果列表, 合并后的上下文字符串，含来源标签)
    """
    results: list[ToolExecutionResult] = []
    context_parts: list[str] = []
    facts = page_facts or {}

    # 主工具执行（带重试）
    main_result = await _execute_with_retry(tool_name, params)
    results.append(main_result)

    if main_result.success:
        context_parts.append(f"[实时查询]\n{main_result.to_context_string()}")

        # ===== 完整性契约 + 关联补全（修 D3/D4）=====
        # enrich 触发条件：order_id 非空（含从主工具结果中提取）或 主工具结果不满足契约
        main_data = main_result.tool_result.data if main_result.tool_result else {}
        enrich_order_id = str(params.get("order_id") or (main_data or {}).get("order_id") or "")
        missing_dimensions = contract_missing_dimensions(tool_name, main_data)
        should_enrich = enrich and tool_name in TOOL_ENRICHMENT_MAP and (
            enrich_order_id or missing_dimensions
        )

        if should_enrich:
            for enrich_tool_name in TOOL_ENRICHMENT_MAP[tool_name]:
                enrich_params: dict[str, Any] = (
                    {"order_id": enrich_order_id} if enrich_order_id else {}
                )
                enrich_result = await tool_executor.execute_by_name(
                    enrich_tool_name, **enrich_params
                )
                if enrich_result.success:
                    results.append(enrich_result)
                    context_parts.append(f"[补全查询]\n{enrich_result.to_context_string()}")
                    logger.info("[EnhancedFlow] 自动补充 %s 成功", enrich_tool_name)
                    # 用补全结果重新评估契约
                    merged_keys = dict(main_data or {})
                    merged_keys.update(enrich_result.tool_result.data or {})
                    missing_dimensions = contract_missing_dimensions(tool_name, merged_keys)
                else:
                    # 修 D3：失败不再静默，明确告知 LLM 失败与替代来源
                    context_parts.append(
                        f"[补全失败提示] {enrich_tool_name} 查询失败({enrich_result.error})；"
                        "若页面上下文/历史记录中有相关信息请据此回答，并如实告知用户当前查询不到"
                    )
                    logger.warning(
                        "[EnhancedFlow] 自动补充 %s 失败: %s", enrich_tool_name, enrich_result.error
                    )

        # ===== 页面快照兜底（A3）：契约仍有缺口 / 补全失败时用前端事实 =====
        if missing_dimensions:
            snapshot_lines = snapshot_lines_for_dimensions(facts, missing_dimensions)
            if snapshot_lines:
                context_parts.extend(snapshot_lines)
                logger.info(
                    "[EnhancedFlow] 页面快照兜底生效: dimensions=%s", missing_dimensions
                )
    else:
        # 主工具失败 → 尝试降级工具
        fallback_name = TOOL_FALLBACK_MAP.get(tool_name)
        if fallback_name and "order_id" in params:
            logger.info("[EnhancedFlow] %s 失败，降级到 %s", tool_name, fallback_name)
            fallback_result = await tool_executor.execute_by_name(
                fallback_name, order_id=params["order_id"]
            )
            results.append(fallback_result)
            if fallback_result.success:
                context_parts.append(f"[补全查询]\n{fallback_result.to_context_string()}")
                context_parts.append(
                    f"[注意] {tool_name} 查询失败({main_result.error})，已用 {fallback_name} 补充信息"
                )
            else:
                context_parts.append(f"[工具调用失败] {tool_name}: {main_result.error}")
        else:
            context_parts.append(f"[工具调用失败] {tool_name}: {main_result.error}")

        # 主工具失败时同样尝试页面快照兜底（覆盖"物流单号未同步但详情页可见"场景）
        snapshot_lines = snapshot_lines_for_dimensions(
            facts, list(TOOL_RESULT_CONTRACTS.get(tool_name, {}).keys())
        )
        if snapshot_lines:
            context_parts.extend(snapshot_lines)

    return results, "\n\n".join(context_parts)


async def _execute_with_retry(
    tool_name: str,
    params: dict[str, Any],
) -> ToolExecutionResult:
    """带重试的工具执行"""
    result = ToolExecutionResult(tool_name=tool_name, tool_args=params, success=False, error="未执行")
    for attempt in range(MAX_RETRY):
        result = await tool_executor.execute_by_name(tool_name, **params)
        if result.success:
            return result
        if attempt < MAX_RETRY - 1:
            logger.warning(
                f"[EnhancedFlow] {tool_name} 第{attempt+1}次失败: {result.error}，重试..."
            )
    return result


INFORMATION_INTEGRATION_RULES = """信息整合守则：
- 交叉核对所有来源（实时查询、补全查询、页面快照）后再回答；同一事实以实时查询为准，快照为辅。
- 某个信息在单一来源缺失时，先检查其他来源；都缺失才如实说"当前查询不到"，并给出替代方案。
- 严禁把"单一来源没有"说成"系统没有/未同步"；严禁编造单号、金额、日期。"""

ANALYSIS_PROMPT = """你是一位资深电商客服 AI。基于以下工具查询结果，给用户一个简短、口语、像真人客服的回答。

要求：
1. 先一句话给结论（如：货在路上了 / 退款已提交 / 订单正常）
2. 再补最关键的 1-2 条信息（如预计到达、到账时间、异常提醒）
3. 主动发现异常（如已付款超3天未发货、物流停滞）并提醒，但别长篇大论
4. 工具查询失败就如实说，给个替代办法
5. 全程纯文本、不超过几句话，别罗列原始数据

{domain_prompt}

""" + INFORMATION_INTEGRATION_RULES


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
    - 自动补充关联数据（完整性契约驱动）
    - 页面快照兜底（前端注入事实，user_input 含 [系统补充上下文] 时自动解析）
    - LLM 综合分析多工具结果
    """
    start = time.perf_counter()

    # 页面快照事实（A3）：从完整消息解析前端注入的结构化事实行
    page_facts = extract_context_facts(user_input)

    # 增强工具执行
    results, context_string = await enhanced_tool_execute(
        tool_name, tool_params, enrich=enrich, page_facts=page_facts
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
