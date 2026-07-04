"""
Multi-Agent Coordinator - 多 Agent 协作引擎

职责：
- 检测复杂跨域请求（如"查订单物流并退款"）
- 并行调度多个 Agent/Flow 协作处理
- 汇总多 Agent 结果，生成统一回复
- 处理 Agent 间的依赖关系和数据传递

设计理念：
- 不修改现有 Flow，在 agent.py 上层编排
- 检测到多意图/多任务时自动激活
- 结果合并由 LLM 做自然语言综合
- 对前端透明，返回统一的 AgentResult
"""

import asyncio
import logging
import re
import time
from typing import Any

from app.agents.complaint_intent import is_followup_request
from app.database.connection import DatabaseAccessError
from app.database.repositories import ComplaintRepository
from app.flows.base import FlowResult
from app.models.message import Message, MessageRole
from app.services.llm import call_llm
from app.tools.executors.tool_executor import tool_executor
from app.tools.tool_registry import tool_registry

logger = logging.getLogger(__name__)


# 多意图检测规则：一条消息中同时包含多个领域关键词
DOMAIN_PATTERNS = {
    "logistics": re.compile(r"物流|快递|配送|运输|到哪|发货|签收|运单"),
    "order": re.compile(r"订单|下单|支付|收货|待发货"),
    "refund": re.compile(r"退款|退货|退钱|售后|退换|换货"),
    "complaint": re.compile(r"投诉|差评|赔付|补偿|态度恶劣"),
    "product": re.compile(r"商品|库存|有货|价格|尺码|参数"),
    "coupon": re.compile(r"优惠|券|折扣|满减|活动"),
}

# 各域对应的工具
DOMAIN_TOOL_MAP = {
    "logistics": "logistics_query",
    "order": "query_order",
    "refund": "refund_apply",
    "complaint": "complaint_create",
    "product": "query_inventory",
}

SYSTEM_CONTEXT_MARKER = "[系统补充上下文"
EXPLICIT_COMPLAINT_CREATE_PATTERN = re.compile(
    r"(创建|提交|发起|新建|我要|帮我|需要).{0,12}(投诉|工单|客诉)|"
    r"(投诉|客诉).{0,12}(创建|提交|发起|新建|立案)",
)


def _user_visible_input(text: str) -> str:
    """Return only the user's visible message, excluding frontend-added context."""
    return text.split(SYSTEM_CONTEXT_MARKER, 1)[0].strip()


def _should_create_complaint(user_input: str) -> bool:
    """Only create complaint records for explicit user creation requests."""
    visible = _user_visible_input(user_input)
    if re.search(r"(查询|查看|总结|汇总|跟进|进度|记录|情况).{0,12}(投诉|工单|客诉)", visible):
        return False
    return bool(EXPLICIT_COMPLAINT_CREATE_PATTERN.search(visible))

# 域间依赖：某些域需要其他域的数据才能执行
DOMAIN_DEPENDENCIES = {
    "refund": ["order"],       # 退款依赖订单信息
    "complaint": ["order"],    # 投诉依赖订单信息
    "logistics": ["order"],    # 物流查询可能需要从订单获取信息
}

SYNTHESIZE_PROMPT = """你是电商平台资深 AI 客服。你刚同时处理了用户的多个需求，现在把结果用一段简短、口语的话告诉用户。

要求：
1. 像真人客服发消息那样，自然连贯地说，别分成"第一第二"
2. 先说最重要的结果，再补关键信息和下一步
3. 某个环节失败就顺带提一句替代办法
4. 发现关联问题主动提醒（如物流异常可以帮你退款）
5. 全程纯文本、控制在几句话内，别罗列数据
"""


def detect_multi_intent(user_input: str) -> list[str]:
    """
    检测用户消息中包含的多个领域意图

    Returns:
        检测到的域列表（超过1个表示需要多Agent协作）
    """
    detected = []
    visible_input = _user_visible_input(user_input)
    for domain, pattern in DOMAIN_PATTERNS.items():
        if pattern.search(visible_input):
            detected.append(domain)
    return detected


def should_coordinate(user_input: str) -> bool:
    """判断是否需要启动多Agent协作"""
    domains = detect_multi_intent(user_input)
    return len(domains) >= 2


def _extract_order_id(text: str) -> str | None:
    """从文本提取订单号"""
    patterns = [
        r'(?:订单号?|order[_\s]?(?:id)?)[：:\s]*([A-Za-z0-9_\-]{4,40})',
        r'\b((?:ORD|ord)[A-Za-z0-9_\-]{4,40})\b',
        r'\b(\d{5,20})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


async def coordinate(
    user_input: str,
    history: list[dict],
    domains: list[str] | None = None,
) -> FlowResult:
    """
    多 Agent 协作执行

    策略：
    1. 提取公共参数（order_id）
    2. 按依赖关系排序执行顺序
    3. 并行执行无依赖的工具
    4. 串行执行有依赖的工具
    5. LLM 综合所有结果生成回复
    """
    start = time.perf_counter()

    if domains is None:
        domains = detect_multi_intent(user_input)

    logger.info(f"[Coordinator] 多Agent协作启动，检测到域: {domains}")

    # 提取公共参数
    visible_input = _user_visible_input(user_input)
    order_id = _extract_order_id(visible_input)
    if not order_id:
        order_id = _extract_order_id(user_input)
    all_tool_calls: list[dict[str, Any]] = []
    context_parts: list[str] = []

    # 按依赖排序：无依赖的先执行
    independent = [d for d in domains if d not in DOMAIN_DEPENDENCIES]
    dependent = [d for d in domains if d in DOMAIN_DEPENDENCIES]

    # Phase 1: 并行执行无依赖域
    if independent:
        tasks = []
        for domain in independent:
            tool_name = DOMAIN_TOOL_MAP.get(domain)
            if tool_name and order_id:
                tasks.append(_execute_domain_tool(domain, tool_name, order_id, user_input))
            elif tool_name and domain == "product":
                # 商品查询不需要 order_id
                tasks.append(_execute_product_tool(user_input))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"[Coordinator] 域执行异常: {result}")
                    context_parts.append(f"[部分查询异常] {str(result)}")
                elif result:
                    domain_name, exec_result, ctx = result
                    all_tool_calls.append(exec_result.to_trace_dict())
                    if exec_result.success:
                        context_parts.append(f"[{domain_name}查询结果]\n{exec_result.to_context_string()}")
                    else:
                        context_parts.append(f"[{domain_name}查询失败] {exec_result.error}")

    # Phase 2: 串行执行有依赖域
    for domain in dependent:
        tool_name = DOMAIN_TOOL_MAP.get(domain)
        if not tool_name:
            continue

        if domain == "refund" and order_id:
            reason = _extract_refund_reason(user_input)
            exec_result = await tool_executor.execute_by_name(
                tool_name, order_id=order_id, reason=reason
            )
        elif domain == "complaint" and order_id:
            # AI 绝不在多 Agent 协作里静默创建投诉。三种情形分开处理：
            # 1) 跟进/已投诉过 → 读真实投诉记录（只读），绝不再要求"提交"
            # 2) 明确要创建 → 引导用户确认后再建单
            # 3) 其它模糊诉求 → 引导确认
            if is_followup_request(user_input) or not _should_create_complaint(user_input):
                complaint = None
                try:
                    complaint = ComplaintRepository().get_latest_by_order_id(order_id)
                except DatabaseAccessError as exc:
                    logger.warning(f"[Coordinator] complaint lookup failed: {exc}")
                if complaint:
                    all_tool_calls.append({
                        "tool_name": "complaint_lookup",
                        "tool_input": {"order_id": order_id},
                        "tool_output": {
                            "complaint_id": complaint.get("complaint_id"),
                            "complaint_status": complaint.get("complaint_status"),
                            "priority": complaint.get("priority"),
                        },
                        "success": True,
                        "latency_ms": 0,
                    })
                    context_parts.append(
                        f"[complaint处理结果]\n已查到该订单的真实投诉记录，请据此告知处理进展：\n{complaint}"
                    )
                    continue
                if is_followup_request(user_input):
                    context_parts.append(
                        f"[complaint处理结果]\n未查到订单 {order_id} 的投诉记录，"
                        "请向用户确认投诉编号或订单号，不要谎称已提交。"
                    )
                    continue
                context_parts.append(
                    "[complaint处理结果]\n已读取你的投诉相关诉求；如需正式创建投诉工单，请回复“确认提交投诉”。"
                )
            else:
                context_parts.append(
                    "[complaint处理结果]\n已识别到你想创建投诉。为避免误建，请明确回复“确认提交投诉”，"
                    "我确认后再正式创建工单。"
                )
            continue
        elif order_id:
            exec_result = await tool_executor.execute_by_name(
                tool_name, order_id=order_id
            )
        else:
            continue

        all_tool_calls.append(exec_result.to_trace_dict())
        if exec_result.success:
            context_parts.append(f"[{domain}处理结果]\n{exec_result.to_context_string()}")
        else:
            context_parts.append(f"[{domain}处理失败] {exec_result.error}")

    # Phase 3: LLM 综合所有结果
    combined_context = "\n\n".join(context_parts) if context_parts else "未能获取到有效信息"
    user_message = f"用户原始请求：{visible_input}\n\n各Agent处理结果：\n{combined_context}"

    content = await call_llm(
        system_prompt=SYNTHESIZE_PROMPT,
        user_message=user_message,
        history=history,
        temperature=0.5,
        max_tokens=2000,
    )

    duration = (time.perf_counter() - start) * 1000
    logger.info(
        f"[Coordinator] 多Agent协作完成，域: {domains}, "
        f"工具调用: {len(all_tool_calls)}次, 耗时: {duration:.0f}ms"
    )

    message = Message(role=MessageRole.ASSISTANT, content=content)
    message.metadata = {
        "coordinator": True,
        "domains": domains,
        "tool_count": len(all_tool_calls),
    }

    return FlowResult(
        message=message,
        tool_calls=all_tool_calls,
    )


async def _execute_domain_tool(
    domain: str,
    tool_name: str,
    order_id: str,
    user_input: str,
) -> tuple[str, Any, str]:
    """执行单个域的工具"""
    exec_result = await tool_executor.execute_by_name(tool_name, order_id=order_id)
    return (domain, exec_result, "")


async def _execute_product_tool(user_input: str) -> tuple[str, Any, str] | None:
    """商品查询工具（不需要order_id）"""
    import re as _re
    keyword = None
    quote_match = _re.search(r'[""「」《》](.+?)[""「」《》]', user_input)
    if quote_match:
        keyword = quote_match.group(1)
    if not keyword:
        categories = ["耳机", "手机", "键盘", "鼠标", "音箱", "手表", "平板", "笔记本"]
        for cat in categories:
            if cat in user_input:
                keyword = cat
                break
    if not keyword:
        return None
    exec_result = await tool_executor.execute_by_name("query_inventory", product_name=keyword)
    return ("product", exec_result, "")


def _extract_refund_reason(text: str) -> str:
    """提取退款原因"""
    reason_keywords = {
        "坏了": "商品损坏", "质量": "质量问题", "不想要": "不想要了",
        "买错": "买错了", "不合适": "商品不合适", "没收到": "未收到商品",
        "假": "怀疑假货", "破损": "商品破损", "发错": "发错商品",
        "物流异常": "物流异常", "配送": "配送问题",
    }
    for keyword, reason in reason_keywords.items():
        if keyword in text:
            return reason
    return "用户申请退款"
