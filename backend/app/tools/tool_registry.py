"""
Tool Registry - 工具注册中心

职责：
- 维护所有可用 Tool 的注册表
- 提供按名称查找工具的能力
- 应用启动时统一注册所有工具

设计理念：
- Registry Pattern，与 FlowRegistry 设计一致
- 新增工具只需：1) 写 Tool 类 2) 注册一行
- ToolRouter 通过 Registry 获取工具，不直接 import 具体 Tool
- 支持按 Intent 查找关联的工具列表

架构位置：
- tools/ 层基础设施
- 被 tool_router.py 和 agent.py 使用

扩展规划：
- Phase 4: 支持工具优先级和条件注册
- Phase 5: 支持动态注册/注销（热插拔）
"""

import logging
from typing import Type, Any
from app.tools.base_tool import BaseTool
from app.tools.schemas.function_schemas import get_tool_schema

logger = logging.getLogger(__name__)


# Agent → Tool 权限映射
# 每个 Agent 只能调用其授权的 Tool
AGENT_TOOL_PERMISSIONS: dict[str, list[str]] = {
    "LogisticsAgent": ["logistics_query", "query_order"],
    "RefundAgent": ["refund_apply", "query_order", "logistics_query"],
    "OrderAgent": ["query_order"],
    "ProductAgent": ["product_query", "query_inventory"],
    "TicketAgent": ["create_ticket"],
    "ComplaintAgent": ["complaint_create", "create_ticket", "query_order", "logistics_query", "refund_apply"],
    "SupervisorAgent": [
        "product_query",
        "query_inventory",
        "query_order",
        "logistics_query",
        "refund_apply",
        "complaint_create",
        "create_ticket",
        "transfer_human",
        "knowledge_search",
    ],
    "KnowledgeAgent": ["knowledge_search"],
    "HumanAgent": ["transfer_human"],
    "InventoryAgent": ["query_inventory"],
    "GeneralAgent": ["transfer_human", "create_ticket", "complaint_create"],
}


class ToolRegistry:
    """
    工具注册表（增强版）

    维护 tool_name → Tool 实例 的映射。
    同时维护 intent → [tool_name] 的关联，支持按意图查找工具。
    新增：schema 元数据、Agent 权限查询、工具描述。

    使用示例：
        registry = ToolRegistry()
        registry.register(LogisticsTool, intents=["logistics_query"])
        tool = registry.get("logistics_query")
        tools = registry.get_by_intent("logistics_query")
        schema = registry.get_schema("query_logistics")
        agent_tools = registry.get_agent_tools("LogisticsAgent")
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._intent_tools: dict[str, list[str]] = {}

    def register(
        self,
        tool_class: Type[BaseTool],
        intents: list[str] | None = None,
    ) -> None:
        """
        注册工具

        Args:
            tool_class: 工具类（会被实例化）
            intents: 关联的意图列表（可选）
        """
        instance = tool_class()
        name = instance.name
        self._tools[name] = instance
        logger.info(f"注册 Tool: {name} → {tool_class.__name__}")

        if intents:
            for intent in intents:
                if intent not in self._intent_tools:
                    self._intent_tools[intent] = []
                self._intent_tools[intent].append(name)

    def get(self, tool_name: str) -> BaseTool | None:
        """按工具名称查找"""
        return self._tools.get(tool_name)

    def get_by_intent(self, intent: str) -> list[BaseTool]:
        """
        按意图查找关联的工具列表

        Args:
            intent: 意图类型值（如 "logistics_query"）

        Returns:
            关联的 Tool 实例列表，未找到返回空列表
        """
        tool_names = self._intent_tools.get(intent, [])
        return [self._tools[name] for name in tool_names if name in self._tools]

    def get_schema(self, tool_name: str) -> dict | None:
        """获取工具的 OpenAI Function Calling Schema"""
        return get_tool_schema(tool_name)

    def get_tool_description(self, tool_name: str) -> str:
        """获取工具描述"""
        tool = self._tools.get(tool_name)
        if tool:
            return tool.description
        return ""

    def get_tool_metadata(self, tool_name: str) -> dict[str, Any]:
        """获取工具完整元数据（名称 + 描述 + schema + 关联意图）"""
        tool = self._tools.get(tool_name)
        if not tool:
            return {}
        schema = self.get_schema(tool_name) or {}
        intents = [
            intent for intent, names in self._intent_tools.items()
            if tool_name in names
        ]
        return {
            "name": tool_name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "function_schema": schema,
            "intents": intents,
        }

    def get_agent_tools(self, agent_name: str) -> list[BaseTool]:
        """获取指定 Agent 有权调用的工具列表"""
        allowed_names = AGENT_TOOL_PERMISSIONS.get(agent_name, [])
        return [self._tools[n] for n in allowed_names if n in self._tools]

    def get_agent_tool_names(self, agent_name: str) -> list[str]:
        """获取指定 Agent 有权调用的工具名列表"""
        allowed = AGENT_TOOL_PERMISSIONS.get(agent_name, [])
        return [n for n in allowed if n in self._tools]

    def list_registered(self) -> list[str]:
        """列出所有已注册的工具名"""
        return list(self._tools.keys())

    def list_intent_mappings(self) -> dict[str, list[str]]:
        """列出所有 intent → tool 映射"""
        return dict(self._intent_tools)


# 全局单例
tool_registry = ToolRegistry()


def init_tools() -> None:
    """
    初始化工具注册表

    应用启动时调用，将所有工具注册到全局 Registry。
    新增工具时，只需在此添加一行注册。

    注意：import 放在函数内部，避免循环依赖。
    """
    # 已有 Tool
    from app.tools.logistics_tool import LogisticsTool
    from app.tools.refund_tool import RefundTool
    from app.tools.product_tool import ProductTool
    from app.tools.complaint_tool import ComplaintCreateTool
    from app.tools.knowledge_search_tool import KnowledgeSearchTool
    # Phase 5.4 新增 Tool
    from app.tools.implementations.order_query_tool import OrderQueryTool
    from app.tools.implementations.ticket_tool import TicketTool
    from app.tools.implementations.human_transfer_tool import HumanTransferTool
    from app.tools.implementations.inventory_tool import InventoryTool
    from app.tools.implementations.coupon_query_tool import CouponQueryTool

    # 原有工具
    tool_registry.register(LogisticsTool, intents=["logistics_query"])
    tool_registry.register(RefundTool, intents=["refund"])
    tool_registry.register(ProductTool, intents=["product_query"])
    tool_registry.register(ComplaintCreateTool, intents=["complaint_create", "complaint", "ticket"])
    tool_registry.register(KnowledgeSearchTool, intents=["knowledge_query"])
    # 新增工具
    tool_registry.register(OrderQueryTool, intents=["order_query"])
    tool_registry.register(TicketTool, intents=["ticket", "complaint"])
    tool_registry.register(HumanTransferTool, intents=["human_transfer", "general"])
    tool_registry.register(InventoryTool, intents=["inventory_query", "product_query"])
    tool_registry.register(CouponQueryTool, intents=["coupon_query"])

    logger.info(f"工具注册完成，已注册: {tool_registry.list_registered()}")
    logger.info(f"意图映射: {tool_registry.list_intent_mappings()}")
