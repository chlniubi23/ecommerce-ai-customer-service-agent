"""
Tool Decision Engine - 工具决策引擎

职责：
- 根据 Intent + 用户输入，决定调用哪些工具
- 从用户输入和对话历史中提取工具参数
- 支持单工具和多工具顺序决策
- 支持全部 6 种工具的参数提取

架构位置：
- tools/ 层，被 flows/ 和 workflows/ 调用
- 依赖 tool_registry.py 获取可用工具
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Any
from app.tools.base_tool import BaseTool
from app.tools.tool_registry import tool_registry

logger = logging.getLogger(__name__)


@dataclass
class ToolCallPlan:
    """
    工具调用计划

    Attributes:
        should_call: 是否应该调用工具
        tool: 选中的工具实例
        tool_name: 工具名称
        params: 提取的工具参数
        reason: 决策原因（供 Trace / Debug 使用）
    """
    should_call: bool = False
    tool: BaseTool | None = None
    tool_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


# ========== 参数提取器 ==========

def _extract_order_id(text: str) -> str | None:
    """从文本中提取订单号。

    优先级：
    1. 系统上下文标注的"本轮优先处理订单号"
    2. 明确标注的订单号（订单号: xxx / order id: xxx，需显式"号"或 id 标记；
       "订单ORD_xxx" 紧邻写法也接受）
    3. 形如 ORD_xxx 的业务订单号（仅大写 ORD 前缀，避免 OrderAgent/ordered
       这类英文单词里的子串误触发）
    4. 不把任意裸数字当订单号，避免手机号误入
    """
    explicit_patterns: list[tuple[str, int]] = [
        (r'本轮优先处理订单号[：:\s]*([A-Za-z0-9_\-]{4,40})', 0),
        (r'订单号[：:\s]*([A-Za-z0-9_\-]{4,40})', 0),
        (r'订单(ORD[A-Za-z0-9_\-]{4,40})', 0),
        (r'\border[_\s]?id\b[：:\s]+([A-Za-z0-9_\-]{4,40})', re.IGNORECASE),
    ]
    for pattern, flags in explicit_patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1)

    ord_match = re.search(r'\b(ORD[A-Za-z0-9_\-]{4,40})\b', text)
    if ord_match:
        return ord_match.group(1)

    return None


def _extract_order_id_from_history(history: list[dict] | None) -> str | None:
    """从对话历史中提取订单号"""
    if not history:
        return None
    for msg in reversed(history):
        oid = _extract_order_id(msg.get("content", ""))
        if oid:
            return oid
    return None


def _extract_product_keyword(text: str) -> str | None:
    """从文本中提取商品关键词"""
    quote_match = re.search(r'[""「」《》](.+?)[""「」《》]', text)
    if quote_match:
        return quote_match.group(1)

    categories = [
        "耳机", "手机", "手机壳", "充电宝", "充电器", "数据线",
        "键盘", "鼠标", "音箱", "手表", "平板", "笔记本",
        "背包", "鞋", "衣服", "裤子",
    ]
    for cat in categories:
        if cat in text:
            return cat
    return None


def _extract_refund_reason(text: str) -> str:
    """从文本中提取退款原因"""
    reason_keywords = {
        "坏了": "商品损坏", "质量": "质量问题", "不想要": "不想要了",
        "买错": "买错了", "不合适": "商品不合适", "没收到": "未收到商品",
        "假": "怀疑假货", "破损": "商品破损", "发错": "发错商品",
    }
    for keyword, reason in reason_keywords.items():
        if keyword in text:
            return reason
    return "用户申请退款"


def _extract_ticket_info(text: str) -> dict[str, str]:
    """从文本中提取工单信息"""
    category = "其他"
    cat_kw = {
        "售后": "售后", "物流": "物流", "投诉": "投诉", "咨询": "咨询",
        "退": "售后", "换": "售后", "催": "物流", "慢": "物流",
        "差评": "投诉", "态度": "投诉",
    }
    for kw, cat in cat_kw.items():
        if kw in text:
            category = cat
            break
    return {"description": text[:200], "category": category}


def _detect_human_transfer(text: str) -> bool:
    """检测是否需要转人工"""
    keywords = [
        "转人工", "人工客服", "人工服务", "真人", "活人",
        "找人", "不想跟机器", "不想和AI", "找客服",
    ]
    return any(kw in text for kw in keywords)


# ========== 核心决策函数 ==========

async def select_tool(
    intent: str,
    user_input: str,
    history: list[dict] | None = None,
) -> ToolCallPlan:
    """
    根据意图和用户输入，决定是否调用工具

    策略：
    1. 优先检测转人工意图（跨 Intent）
    2. 从 ToolRegistry 查找该意图关联的工具
    3. 根据意图类型提取参数
    4. 参数就绪 → 返回调用计划；参数不足 → 进入对话收集

    Args:
        intent: 意图类型值
        user_input: 用户原始输入
        history: 对话历史

    Returns:
        ToolCallPlan: 工具调用决策
    """
    # 1. 转人工检测（优先级最高，跨 intent）
    if _detect_human_transfer(user_input):
        tool = tool_registry.get("transfer_human")
        if tool:
            return ToolCallPlan(
                should_call=True,
                tool=tool,
                tool_name="transfer_human",
                params={"reason": user_input[:100]},
                reason="检测到转人工意图",
            )

    # 2. 从 Registry 查找关联工具
    tools = tool_registry.get_by_intent(intent)
    if not tools:
        return ToolCallPlan(
            should_call=False,
            reason=f"意图 {intent} 无关联工具",
        )

    # 3. 根据意图类型选择工具和提取参数
    if intent == "logistics_query":
        return _decide_logistics(user_input, history, tools)
    elif intent == "refund":
        return _decide_refund(user_input, history, tools)
    elif intent == "order_query":
        return _decide_order_query(user_input, history, tools)
    elif intent == "product_query":
        return _decide_product(user_input, history, tools)
    elif intent in ("ticket", "complaint", "complaint_create"):
        return _decide_ticket(user_input, tools)
    elif intent == "human_transfer":
        return _decide_human_transfer(user_input, tools)
    elif intent == "general":
        return _decide_general(user_input, tools)
    else:
        # 通用 fallback：取第一个工具，尝试提取 order_id
        return _decide_fallback(intent, user_input, history, tools)


async def select_tools_for_workflow(
    intent: str,
    user_input: str,
    history: list[dict] | None = None,
) -> list[ToolCallPlan]:
    """
    为 Workflow 选择多个工具（顺序执行）

    某些场景需要多个工具配合：
    - "订单123456物流异常，我要退款" → query_logistics + query_refund
    - "帮我查下订单和物流" → query_order + query_logistics
    """
    plans: list[ToolCallPlan] = []

    order_id = _extract_order_id(user_input) or _extract_order_id_from_history(history)

    # 物流异常 + 退款 → 双工具
    logistics_kw = any(kw in user_input for kw in ["物流", "快递", "配送", "运输", "没到"])
    refund_kw = any(kw in user_input for kw in ["退款", "退货", "退钱", "退"])

    if logistics_kw and refund_kw and order_id:
        logistics_tool = tool_registry.get("logistics_query")
        refund_tool = tool_registry.get("refund_apply")
        if logistics_tool:
            plans.append(ToolCallPlan(
                should_call=True, tool=logistics_tool, tool_name="logistics_query",
                params={"order_id": order_id}, reason="Workflow: 先查物流",
            ))
        if refund_tool:
            plans.append(ToolCallPlan(
                should_call=True, tool=refund_tool, tool_name="refund_apply",
                params={"order_id": order_id, "reason": _extract_refund_reason(user_input)},
                reason="Workflow: 再查退款",
            ))
        return plans

    # 单工具 fallback
    plan = await select_tool(intent, user_input, history)
    if plan.should_call:
        plans.append(plan)
    return plans


# ========== 各意图决策函数 ==========

def _decide_logistics(
    user_input: str, history: list[dict] | None, tools: list[BaseTool],
) -> ToolCallPlan:
    """物流查询工具决策"""
    tool = _find_tool(tools, "logistics_query")
    if not tool:
        return ToolCallPlan(should_call=False, reason="未找到物流工具")

    order_id = _extract_order_id(user_input) or _extract_order_id_from_history(history)
    if not order_id:
        return ToolCallPlan(
            should_call=False, tool=tool, tool_name=tool.name,
            reason="缺少订单号，进入对话收集",
        )

    return ToolCallPlan(
        should_call=True, tool=tool, tool_name=tool.name,
        params={"order_id": order_id}, reason=f"参数就绪，调用 {tool.name}",
    )


def _decide_refund(
    user_input: str, history: list[dict] | None, tools: list[BaseTool],
) -> ToolCallPlan:
    """退款工具决策"""
    tool = _find_tool(tools, "refund_apply")
    if not tool:
        return ToolCallPlan(should_call=False, reason="未找到退款工具")

    order_id = _extract_order_id(user_input) or _extract_order_id_from_history(history)
    if not order_id:
        return ToolCallPlan(
            should_call=False, tool=tool, tool_name=tool.name,
            reason="缺少订单号，进入对话收集",
        )

    return ToolCallPlan(
        should_call=True, tool=tool, tool_name=tool.name,
        params={"order_id": order_id, "reason": _extract_refund_reason(user_input)},
        reason=f"参数就绪，调用 {tool.name}",
    )


def _decide_order_query(
    user_input: str, history: list[dict] | None, tools: list[BaseTool],
) -> ToolCallPlan:
    """订单查询工具决策"""
    tool = _find_tool(tools, "query_order")
    if not tool:
        return ToolCallPlan(should_call=False, reason="未找到订单查询工具")

    order_id = _extract_order_id(user_input) or _extract_order_id_from_history(history)
    if not order_id:
        return ToolCallPlan(
            should_call=False, tool=tool, tool_name=tool.name,
            reason="缺少订单号，进入对话收集",
        )

    return ToolCallPlan(
        should_call=True, tool=tool, tool_name=tool.name,
        params={"order_id": order_id}, reason=f"参数就绪，调用 {tool.name}",
    )


def _decide_product(
    user_input: str, history: list[dict] | None, tools: list[BaseTool],
) -> ToolCallPlan:
    """商品/库存查询工具决策"""
    # 如果有库存相关关键词，优先用 inventory tool
    inventory_kw = any(kw in user_input for kw in ["库存", "有货", "还有", "多少", "剩余"])
    if inventory_kw:
        tool = _find_tool(tools, "query_inventory")
    else:
        tool = _find_tool(tools, "product_query") or _find_tool(tools, "query_inventory")

    if not tool:
        return ToolCallPlan(should_call=False, reason="未找到商品工具")

    keyword = _extract_product_keyword(user_input)
    if not keyword:
        return ToolCallPlan(
            should_call=False, tool=tool, tool_name=tool.name,
            reason="未提取到商品关键词",
        )

    param_key = "product_name" if tool.name == "query_inventory" else "keyword"
    return ToolCallPlan(
        should_call=True, tool=tool, tool_name=tool.name,
        params={param_key: keyword}, reason=f"参数就绪，调用 {tool.name}",
    )


def _extract_user_id(text: str) -> str | None:
    """从文本中提取用户 ID"""
    patterns = [
        r'(?:用户|user[_\s]?(?:id)?)[：:\s]*([A-Za-z0-9_\-]{4,40})',
        r'\b((?:USR|usr)[A-Za-z0-9_\-]{4,40})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _decide_ticket(user_input: str, tools: list[BaseTool]) -> ToolCallPlan:
    """工单创建工具决策"""
    tool = _find_tool(tools, "complaint_create") or _find_tool(tools, "create_ticket")
    if not tool:
        return ToolCallPlan(should_call=False, reason="未找到工单工具")

    info = _extract_ticket_info(user_input)
    if tool.name == "complaint_create":
        info = {
            "content": info["description"],
            "complaint_type": info["category"],
        }
        order_id = _extract_order_id(user_input)
        user_id = _extract_user_id(user_input)
        if order_id:
            info["order_id"] = order_id
        if user_id:
            info["user_id"] = user_id
    return ToolCallPlan(
        should_call=True, tool=tool, tool_name=tool.name,
        params=info, reason=f"创建工单: {info.get('category') or info.get('complaint_type')}",
    )


def _decide_human_transfer(user_input: str, tools: list[BaseTool]) -> ToolCallPlan:
    """转人工客服决策 - 直接调用 transfer_human"""
    tool = _find_tool(tools, "transfer_human")
    if not tool:
        return ToolCallPlan(should_call=False, reason="未找到转人工工具")

    return ToolCallPlan(
        should_call=True, tool=tool, tool_name=tool.name,
        params={"reason": user_input[:100]}, reason="用户请求转人工客服",
    )


def _decide_general(user_input: str, tools: list[BaseTool]) -> ToolCallPlan:
    """通用意图决策 - 一般不调工具"""
    return ToolCallPlan(should_call=False, reason="通用意图，不需要调用工具")


def _decide_fallback(
    intent: str, user_input: str, history: list[dict] | None, tools: list[BaseTool],
) -> ToolCallPlan:
    """兜底决策"""
    tool = tools[0]
    params: dict[str, Any] = {}

    order_id = _extract_order_id(user_input) or _extract_order_id_from_history(history)
    if order_id:
        params["order_id"] = order_id

    validation = tool.validate_params(**params)
    if validation:
        return ToolCallPlan(
            should_call=False, tool=tool, tool_name=tool.name,
            params=params, reason=f"参数不足: {validation}",
        )

    return ToolCallPlan(
        should_call=True, tool=tool, tool_name=tool.name,
        params=params, reason=f"Fallback 调用 {tool.name}",
    )


# ========== 辅助函数 ==========

def _find_tool(tools: list[BaseTool], name: str) -> BaseTool | None:
    """从工具列表中按名称查找"""
    for t in tools:
        if t.name == name:
            return t
    return tools[0] if tools else None
