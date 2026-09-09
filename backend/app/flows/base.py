"""
Flow 基类 - 业务流程处理器抽象

职责：
- 定义所有 Flow Handler 的统一接口
- 确保所有业务流程遵循同一协议
- 为 Router 提供类型安全的调度目标

设计理念：
- 所有 Flow 继承 BaseFlow，实现 handle() 方法
- Router 只依赖 BaseFlow 接口，不依赖具体实现
- 新增业务流程只需继承 BaseFlow + 注册到 Router

架构位置：
- flows/ 层基础设施，被所有具体 Flow 继承
- 被 router/ 层引用（依赖抽象，不依赖具体）

为什么企业项目需要抽象基类：
1. 统一接口：Router 可以安全调用任何 Flow 的 handle()
2. 强制规范：新 Flow 必须实现 handle()，否则运行时报错
3. 类型安全：IDE 可推断返回值类型
4. 后续 LangGraph：每个 Flow 可直接映射为 Graph 的一个 Node

扩展规划：
- Phase 3 (Tool Calling): handle() 内部可调用 tools
- Phase 4 (LangGraph): BaseFlow 可适配为 LangGraph Node
- Phase 5 (Memory): handle() 增加 session_context 参数
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from app.schemas.intent import IntentResult
from app.models.message import Message
from app.tools.base_tool import ToolResult


@dataclass
class FlowResult:
    """
    Flow 执行结果

    包含 AI 回复 Message 和可选的工具调用信息。
    Agent 层据此构建 Trace。

    Attributes:
        message: AI 回复的标准 Message 对象
        tool_calls: 工具调用记录列表（可能为空）
    """
    message: Message
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class BaseFlow(ABC):
    """
    业务流程处理器抽象基类

    所有具体的 Flow Handler（如 RefundFlow、LogisticsFlow）
    都必须继承此类并实现 handle() 方法。

    接口协议：
    - 输入: IntentResult（意图分类结果） + history（对话历史）
    - 输出: FlowResult（消息 + 工具调用记录）

    使用示例：
        class RefundFlow(BaseFlow):
            async def handle(self, intent_result, history) -> FlowResult:
                # 调用工具 → 拿到结果 → 结合结果调用 LLM
                return FlowResult(message=msg, tool_calls=[...])
    """

    @abstractmethod
    async def handle(
        self,
        intent_result: IntentResult,
        history: list[dict],
        slots: dict[str, Any] | None = None,
    ) -> FlowResult:
        """
        处理业务流程

        Args:
            intent_result: 意图分类结果，包含 intent、confidence、raw_input
            history: 对话历史（dict 列表，每项含 role + content）
            slots: FSM 收集的槽位值（多轮对话模式下由 Agent 传入）

        Returns:
            FlowResult: 包含 Message 和工具调用记录
        """
        ...
