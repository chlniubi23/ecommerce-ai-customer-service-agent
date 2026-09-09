"""
Conditional Edge Framework - 条件边框架

职责：
- 定义条件边规则
- 动态路由节点执行
- 支持多分支决策
- 支持嵌套条件判断

设计原则：
- Declarative：条件边声明式定义
- Composable：条件可组合
- State-driven：基于 GraphState 动态决策
- Extensible：条件规则可扩展

条件边类型：
1. Simple Condition：单条件判断
2. Composite Condition：组合条件（AND/OR/NOT）
3. Sequential Condition：连续条件判断
4. Branch Condition：多分支条件
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional
GraphState = dict  # legacy alias; LangGraph experiment layer (app.graph/app.state) removed

logger = logging.getLogger(__name__)


class ConditionOperator(str, Enum):
    """条件操作符"""
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class EdgeCondition:
    """
    边条件定义

    定义从一个节点到另一个节点的条件。
    """
    name: str                           # 条件名称
    description: str                    # 条件描述
    condition_fn: Callable[[GraphState], bool]  # 条件函数
    priority: int = 0                   # 优先级（数字越大优先级越高）
    metadata: dict = None               # 元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def evaluate(self, state: GraphState) -> bool:
        """
        评估条件

        Args:
            state: Graph 状态

        Returns:
            条件是否满足
        """
        try:
            result = self.condition_fn(state)
            logger.debug(f"[EdgeCondition] {self.name} = {result}")
            return result
        except Exception as e:
            logger.error(f"[EdgeCondition] 条件评估失败: {self.name}, error={e}")
            return False


class BaseCondition(ABC):
    """条件基类"""

    @abstractmethod
    def evaluate(self, state: GraphState) -> bool:
        """评估条件"""
        pass


class SimpleCondition(BaseCondition):
    """简单条件"""

    def __init__(self, condition_fn: Callable[[GraphState], bool], name: str = ""):
        self.condition_fn = condition_fn
        self.name = name or "simple_condition"

    def evaluate(self, state: GraphState) -> bool:
        return self.condition_fn(state)


class CompositeCondition(BaseCondition):
    """组合条件"""

    def __init__(
        self,
        operator: ConditionOperator,
        conditions: list[BaseCondition],
        name: str = "",
    ):
        self.operator = operator
        self.conditions = conditions
        self.name = name or f"composite_{operator.value}"

    def evaluate(self, state: GraphState) -> bool:
        results = [cond.evaluate(state) for cond in self.conditions]

        if self.operator == ConditionOperator.AND:
            return all(results)
        elif self.operator == ConditionOperator.OR:
            return any(results)
        elif self.operator == ConditionOperator.NOT:
            # NOT 只对第一个条件取反
            return not results[0] if results else False
        return False


@dataclass
class ConditionalEdge:
    """
    条件边

    定义从源节点到目标节点的条件路由。
    """
    from_node: str                      # 源节点
    to_node: str                        # 目标节点
    condition: EdgeCondition            # 条件
    edge_type: str = "conditional"      # 边类型
    metadata: dict = None               # 元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def should_route(self, state: GraphState) -> bool:
        """
        判断是否应该路由到目标节点

        Args:
            state: Graph 状态

        Returns:
            是否路由
        """
        return self.condition.evaluate(state)


class ConditionalEdgeRegistry:
    """
    条件边注册表

    管理所有条件边的注册和查找。
    """

    def __init__(self):
        self._edges: dict[str, list[ConditionalEdge]] = {}

    def register(self, edge: ConditionalEdge) -> None:
        """
        注册条件边

        Args:
            edge: 条件边
        """
        if edge.from_node not in self._edges:
            self._edges[edge.from_node] = []

        self._edges[edge.from_node].append(edge)
        logger.info(
            f"[EdgeRegistry] 注册条件边: {edge.from_node} -> {edge.to_node} "
            f"(condition={edge.condition.name})"
        )

    def get_edges(self, from_node: str) -> list[ConditionalEdge]:
        """
        获取从指定节点出发的所有条件边

        Args:
            from_node: 源节点

        Returns:
            条件边列表
        """
        return self._edges.get(from_node, [])

    def find_next_node(self, from_node: str, state: GraphState) -> Optional[str]:
        """
        查找下一个节点

        根据条件边规则和状态，查找下一个应该执行的节点。
        按条件优先级排序，返回第一个满足条件的目标节点。

        Args:
            from_node: 源节点
            state: Graph 状态

        Returns:
            下一个节点名称，如果没有满足条件的边则返回 None
        """
        edges = self.get_edges(from_node)
        if not edges:
            return None

        # 按优先级排序
        sorted_edges = sorted(edges, key=lambda e: e.condition.priority, reverse=True)

        # 查找第一个满足条件的边
        for edge in sorted_edges:
            if edge.should_route(state):
                logger.info(
                    f"[EdgeRegistry] 条件路由: {from_node} -> {edge.to_node} "
                    f"(condition={edge.condition.name})"
                )
                return edge.to_node

        return None

    def clear(self) -> None:
        """清空注册表"""
        self._edges.clear()


# ===== 预定义条件函数 =====

def slots_not_ready(state: GraphState) -> bool:
    """Slot 未就绪"""
    has_fsm = state.get("has_fsm", False)
    slots_ready = state.get("slots_ready", True)
    return has_fsm and not slots_ready


def slots_ready(state: GraphState) -> bool:
    """Slot 已就绪"""
    slots_ready_flag = state.get("slots_ready", True)
    return slots_ready_flag


def rag_eligible(state: GraphState) -> bool:
    """RAG 候选"""
    return state.get("rag_eligible", False)


def rag_hit(state: GraphState) -> bool:
    """RAG 命中"""
    rag_used = state.get("rag_used", False)
    rag_chunks = state.get("rag_chunks", 0)
    return rag_used and rag_chunks > 0


def rag_miss(state: GraphState) -> bool:
    """RAG 未命中"""
    return not rag_hit(state)


def tool_success(state: GraphState) -> bool:
    """工具执行成功"""
    return state.get("tool_success", False)


def tool_failure(state: GraphState) -> bool:
    """工具执行失败"""
    return not tool_success(state)


def high_confidence_intent(state: GraphState) -> bool:
    """高置信度意图"""
    confidence = state.get("intent_confidence", 0.0)
    return confidence >= 0.85


def low_confidence_intent(state: GraphState) -> bool:
    """低置信度意图"""
    confidence = state.get("intent_confidence", 0.0)
    return confidence < 0.6


# ===== 条件边工厂函数 =====

def create_router_edges() -> list[ConditionalEdge]:
    """
    创建 Router 节点的条件边

    Router 节点后的路由逻辑：
    1. Slot 未就绪 → slot_node
    2. RAG 候选 → rag_node
    3. 默认 → tool_node
    """
    return [
        ConditionalEdge(
            from_node="router_node",
            to_node="slot_node",
            condition=EdgeCondition(
                name="slots_not_ready",
                description="Slots not ready, need slot filling",
                condition_fn=slots_not_ready,
                priority=10,
            ),
        ),
        ConditionalEdge(
            from_node="router_node",
            to_node="rag_node",
            condition=EdgeCondition(
                name="rag_eligible",
                description="RAG eligible, attempt knowledge retrieval",
                condition_fn=rag_eligible,
                priority=5,
            ),
        ),
        ConditionalEdge(
            from_node="router_node",
            to_node="tool_node",
            condition=EdgeCondition(
                name="default_tool",
                description="Default route to tool execution",
                condition_fn=lambda state: True,  # 默认条件，总是满足
                priority=0,
            ),
        ),
    ]


def create_rag_edges() -> list[ConditionalEdge]:
    """
    创建 RAG 节点的条件边

    RAG 节点后的路由逻辑：
    1. RAG 命中 → response_node
    2. RAG 未命中 → tool_node
    """
    return [
        ConditionalEdge(
            from_node="rag_node",
            to_node="response_node",
            condition=EdgeCondition(
                name="rag_hit",
                description="RAG hit, direct response",
                condition_fn=rag_hit,
                priority=10,
            ),
        ),
        ConditionalEdge(
            from_node="rag_node",
            to_node="tool_node",
            condition=EdgeCondition(
                name="rag_miss",
                description="RAG miss, fallback to tool",
                condition_fn=rag_miss,
                priority=5,
            ),
        ),
    ]


def create_slot_edges() -> list[ConditionalEdge]:
    """
    创建 Slot 节点的条件边

    Slot 节点后的路由逻辑：
    1. Slot 已就绪 → tool_node
    2. Slot 仍未就绪 → slot_response_node
    """
    return [
        ConditionalEdge(
            from_node="slot_node",
            to_node="tool_node",
            condition=EdgeCondition(
                name="slots_ready",
                description="Slots filled, resume workflow",
                condition_fn=slots_ready,
                priority=10,
            ),
        ),
        ConditionalEdge(
            from_node="slot_node",
            to_node="slot_response_node",
            condition=EdgeCondition(
                name="slots_still_waiting",
                description="Still waiting for slots",
                condition_fn=slots_not_ready,
                priority=5,
            ),
        ),
    ]


# 全局单例
conditional_edge_registry = ConditionalEdgeRegistry()


def initialize_conditional_edges() -> None:
    """
    初始化条件边

    注册所有预定义的条件边。
    """
    logger.info("[ConditionalEdge] 开始初始化条件边...")

    # 注册 Router 条件边
    for edge in create_router_edges():
        conditional_edge_registry.register(edge)

    # 注册 RAG 条件边
    for edge in create_rag_edges():
        conditional_edge_registry.register(edge)

    # 注册 Slot 条件边
    for edge in create_slot_edges():
        conditional_edge_registry.register(edge)

    logger.info("[ConditionalEdge] 条件边初始化完成")
