"""
路由注册表 - Flow 映射管理

职责：
- 维护 IntentType → Flow Handler 的映射关系
- 提供注册和查找接口
- 确保每个 Intent 都有对应的处理器

设计理念：
- 注册表模式（Registry Pattern）
- 新增 Intent 只需：1) 加枚举值 2) 写 Flow 3) 注册一行
- Router 代码完全不需要改动
- 类似于 Web 框架的 URL → View 路由表

架构位置：
- router/ 层核心，被 agent_router.py 使用
- 在应用启动时由 router/agent_router.py 初始化注册

为什么企业项目需要注册表模式：
1. 开闭原则：对扩展开放（加新 Flow），对修改关闭（不改 Router）
2. 解耦：Router 不 import 任何具体 Flow
3. 可测试：可以注册 Mock Flow 做单元测试
4. 后续 LangGraph：注册表可映射到 Graph 的 node 定义

扩展规划：
- Phase 3: 注册表增加 middleware 支持（前置 RAG 检索）
- Phase 4: 注册表支持优先级和条件路由
"""

import logging
from typing import Type
from app.schemas.intent import IntentType
from app.flows.base import BaseFlow

logger = logging.getLogger(__name__)


class FlowRegistry:
    """
    Flow 注册表

    维护 IntentType 到 Flow Handler 类的映射。
    支持注册、查找、列举操作。

    使用示例：
        registry = FlowRegistry()
        registry.register(IntentType.REFUND, RefundFlow)
        flow = registry.get(IntentType.REFUND)
    """

    def __init__(self):
        """初始化空注册表"""
        self._registry: dict[IntentType, BaseFlow] = {}

    def register(self, intent: IntentType, flow_class: Type[BaseFlow]) -> None:
        """
        注册 Intent → Flow 映射

        Args:
            intent: 意图类型
            flow_class: 对应的 Flow Handler 类（会被实例化）
        """
        instance = flow_class()
        self._registry[intent] = instance
        logger.info(f"注册 Flow: {intent.value} → {flow_class.__name__}")

    def get(self, intent: IntentType) -> BaseFlow | None:
        """
        根据 Intent 查找对应的 Flow Handler

        Args:
            intent: 意图类型

        Returns:
            对应的 Flow 实例，未找到返回 None
        """
        return self._registry.get(intent)

    def list_registered(self) -> list[str]:
        """列出所有已注册的 Intent"""
        return [intent.value for intent in self._registry.keys()]


# 全局单例注册表
# 应用启动时初始化，整个生命周期复用
flow_registry = FlowRegistry()
