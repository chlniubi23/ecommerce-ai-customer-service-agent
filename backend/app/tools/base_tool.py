"""
BaseTool - 工具抽象基类

职责：
- 定义所有 Tool 的统一接口
- 提供 ToolResult 标准返回结构
- 确保工具模块化、可扩展

设计理念：
- 所有 Tool 继承 BaseTool，实现 execute()
- ToolRegistry 只依赖 BaseTool 接口
- 每个 Tool 自描述：name + description + input_schema
- input_schema 用于 LLM Function Calling 和参数校验

架构位置：
- tools/ 层基础设施，被所有具体 Tool 继承
- 被 tool_registry.py 和 tool_router.py 使用

扩展规划：
- Phase 4 (LangGraph): BaseTool 可适配为 LangGraph ToolNode
- Phase 5 (Multi-Agent): Tool 可被多个 Agent 共享
- 未来: 增加 async_execute() 支持并行工具调用
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """
    工具执行结果

    所有 Tool.execute() 必须返回此结构。
    包含执行状态、结果数据和可选的错误信息。

    Attributes:
        success: 是否执行成功
        data: 执行结果数据（JSON 可序列化的 dict）
        error: 错误信息（仅失败时有值）
        tool_name: 执行的工具名称（自动填充）

    使用示例：
        成功: ToolResult(success=True, data={"status": "运输中"})
        失败: ToolResult(success=False, error="订单号不存在")
    """
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    tool_name: str = ""

    def to_context_string(self) -> str:
        """
        将工具结果转换为 LLM 可用的上下文字符串

        用于注入到 system prompt 或 user message 中，
        让 LLM 基于真实数据生成回复。

        Returns:
            str: 格式化的上下文文本
        """
        if not self.success:
            return f"[工具调用失败] {self.tool_name}: {self.error}"

        parts = [f"[{self.tool_name} 查询结果]"]
        for key, value in self.data.items():
            parts.append(f"- {key}: {value}")
        return "\n".join(parts)


class BaseTool(ABC):
    """
    工具抽象基类

    所有业务工具（物流查询、退款申请、商品查询等）
    必须继承此类并实现以下属性和方法。

    必须实现：
    - name: 工具唯一标识
    - description: 工具描述（供 LLM 和 ToolRouter 理解用途）
    - input_schema: 输入参数 JSON Schema（供参数校验和 LLM Function Calling）
    - execute(): 工具执行逻辑

    使用示例：
        class LogisticsTool(BaseTool):
            name = "logistics_query"
            description = "查询物流配送状态"
            input_schema = {"order_id": {"type": "string", "description": "订单号"}}

            async def execute(self, **kwargs) -> ToolResult:
                order_id = kwargs.get("order_id")
                ...
                return ToolResult(success=True, data={...})
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识（英文，snake_case）"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述（自然语言，供 LLM 理解）"""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """
        输入参数 Schema

        格式：{ "param_name": { "type": "string", "description": "...", "required": True } }
        用于：
        1. 参数校验
        2. LLM Function Calling 的 parameters 定义
        3. Debug Panel 展示
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        执行工具逻辑

        Args:
            **kwargs: 工具输入参数（由 input_schema 定义）

        Returns:
            ToolResult: 执行结果
        """
        ...

    def get_required_params(self) -> list[str]:
        """获取所有必需参数名"""
        return [
            name for name, schema in self.input_schema.items()
            if schema.get("required", False)
        ]

    def validate_params(self, **kwargs: Any) -> str | None:
        """
        校验输入参数

        Returns:
            None: 校验通过
            str: 缺失的参数提示（校验失败）
        """
        missing = [
            name for name in self.get_required_params()
            if name not in kwargs or kwargs[name] is None or kwargs[name] == ""
        ]
        if missing:
            return f"缺少必要参数: {', '.join(missing)}"
        return None
