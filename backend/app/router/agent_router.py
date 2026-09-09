"""
Agent Router - 意图路由执行器

职责：
- 根据 IntentResult 从注册表查找对应 Flow
- 执行 Flow Handler 获取 AI 回复
- 处理路由未命中（fallback 到 GENERAL）
- 处理低置信度（降级到通用 Flow）

设计理念：
- Router 只做"查表 + 调度"，不包含业务逻辑
- 置信度策略：高置信走专用 Flow，低置信走通用 Flow
- 所有 Flow 注册在此完成，应用启动时调用 init_routes()

架构位置：
- router/ 层，被 agents/agent.py 调用
- 依赖 registry.py（注册表）和 flows/（具体 Flow）

数据流：
  IntentResult → agent_router.route() → Flow.handle() → Message

为什么企业项目需要这样设计：
1. 路由逻辑集中：所有路由决策在一处，方便审计和调试
2. 置信度降级：不确定的意图不会进入错误的业务流程
3. 初始化隔离：Flow 注册在 init_routes()，不污染模块导入

扩展规划：
- Phase 3 (Tool Calling): Flow 内部可调用 tools，Router 无需感知
- Phase 4 (LangGraph): route() 可替换为 Graph.invoke()
- 未来可增加路由中间件（限流、鉴权、日志增强）
"""

import logging
from typing import Any
from app.schemas.intent import IntentType, IntentResult, CONFIDENCE_HIGH
from app.models.message import Message
from app.router.registry import flow_registry

logger = logging.getLogger(__name__)


def init_routes() -> None:
    """
    初始化路由注册表

    在应用启动时调用，将所有 IntentType 映射到对应的 Flow Handler。
    新增业务场景时，只需在此添加一行注册。

    注意：import 放在函数内部，避免循环依赖
    """
    from app.flows.refund import RefundFlow
    from app.flows.logistics import LogisticsFlow
    from app.flows.order import OrderFlow
    from app.flows.product import ProductFlow
    from app.flows.knowledge import KnowledgeFlow
    from app.flows.coupon import CouponFlow
    from app.flows.ticket import TicketFlow
    from app.flows.human_transfer import HumanTransferFlow
    from app.flows.general import GeneralFlow

    flow_registry.register(IntentType.REFUND, RefundFlow)
    flow_registry.register(IntentType.LOGISTICS_QUERY, LogisticsFlow)
    flow_registry.register(IntentType.ORDER_QUERY, OrderFlow)
    flow_registry.register(IntentType.PRODUCT_QUERY, ProductFlow)
    flow_registry.register(IntentType.KNOWLEDGE_QUERY, KnowledgeFlow)
    flow_registry.register(IntentType.COUPON_QUERY, CouponFlow)
    flow_registry.register(IntentType.TICKET, TicketFlow)
    flow_registry.register(IntentType.HUMAN_TRANSFER, HumanTransferFlow)
    flow_registry.register(IntentType.GENERAL, GeneralFlow)

    logger.info(f"路由注册完成，已注册: {flow_registry.list_registered()}")


class RouteResult:
    """
    路由结果

    包含 AI 回复 Message、路由决策元信息和工具调用记录。
    Agent 据此构建 Trace。

    Attributes:
        message: Flow 返回的 AI 回复
        selected_flow: 最终选中的 Flow 类名
        downgraded: 是否发生了置信度降级
        original_intent: 降级前的原始意图（仅降级时有值）
        tool_calls: 工具调用记录列表
    """
    def __init__(
        self,
        message: Message,
        selected_flow: str,
        downgraded: bool = False,
        original_intent: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
    ):
        self.message = message
        self.selected_flow = selected_flow
        self.downgraded = downgraded
        self.original_intent = original_intent
        self.tool_calls = tool_calls or []


async def route(intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> RouteResult:
    """
    根据意图分类结果路由到对应的 Flow Handler

    路由策略：
    1. confidence >= CONFIDENCE_HIGH → 走专用 Flow
    2. confidence < CONFIDENCE_HIGH → 降级到 GENERAL Flow
    3. 未注册的 Intent → 降级到 GENERAL Flow

    Args:
        intent_result: 意图分类结果
        history: 对话历史

    Returns:
        RouteResult: 包含 Message 和路由元信息
    """
    intent = intent_result.intent
    confidence = intent_result.confidence
    downgraded = False
    original_intent = ""

    # 低置信度降级：不确定的意图走通用 Flow，避免误入错误业务
    if confidence < CONFIDENCE_HIGH and intent != IntentType.GENERAL:
        logger.info(
            f"置信度不足 ({confidence:.2f} < {CONFIDENCE_HIGH})，"
            f"从 {intent.value} 降级到 general"
        )
        original_intent = intent.value
        intent = IntentType.GENERAL
        downgraded = True

    # 从注册表查找 Flow
    flow = flow_registry.get(intent)

    if flow is None:
        # 兜底：未注册的 Intent，走 GENERAL
        logger.warning(f"未找到 {intent.value} 对应的 Flow，fallback to general")
        flow = flow_registry.get(IntentType.GENERAL)

    if flow is None:
        # 极端情况：连 GENERAL 都没注册（不应该发生）
        raise RuntimeError("GENERAL Flow 未注册，Agent Router 初始化异常")

    flow_name = flow.__class__.__name__
    logger.info(f"路由到 Flow: {intent.value} → {flow_name}")

    # 执行 Flow Handler
    flow_result = await flow.handle(intent_result, history, slots=slots)

    return RouteResult(
        message=flow_result.message,
        selected_flow=flow_name,
        downgraded=downgraded,
        original_intent=original_intent,
        tool_calls=flow_result.tool_calls,
    )
