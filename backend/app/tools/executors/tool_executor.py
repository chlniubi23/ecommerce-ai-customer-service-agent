"""
ToolExecutor - 工具统一执行器

职责：
- 统一执行所有 Tool，提供一致的执行入口
- 参数校验（基于 Tool input_schema）
- 超时控制（asyncio.wait_for）
- 错误处理（异常捕获 + 友好提示）
- Trace 记录（执行时间、输入输出、成功/失败）

设计理念：
- 所有 Tool 调用都通过 Executor，不直接调 tool.execute()
- Executor 返回 ToolExecutionResult，包含完整执行信息
- 支持单工具执行和批量顺序执行
- 日志和 Trace 在 Executor 层统一记录

架构位置：
- tools/executors/ 层，被 workflows/ 和 agent.py 调用
- 依赖 tool_registry 获取工具实例
"""

import time
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 10.0


@dataclass
class ToolExecutionResult:
    """
    工具执行结果（含 Trace 信息）

    比 ToolResult 多了执行时间、参数记录等 Trace 字段。
    用于 Workflow 编排和 Agent Trace 构建。

    Attributes:
        tool_name: 执行的工具名称
        tool_args: 传入的参数
        tool_result: 工具返回的原始 ToolResult
        success: 是否成功
        error: 错误信息
        latency_ms: 执行耗时（毫秒）
        timed_out: 是否超时
    """
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: ToolResult | None = None
    success: bool = False
    error: str = ""
    latency_ms: float = 0.0
    timed_out: bool = False

    def to_trace_dict(self) -> dict[str, Any]:
        """转换为 Trace 可用的 dict"""
        return {
            "tool_name": self.tool_name,
            "tool_input": self.tool_args,
            "tool_output": self.tool_result.data if self.tool_result and self.tool_result.success else {"error": self.error},
            "success": self.success,
            "latency_ms": round(self.latency_ms, 2),
            "timed_out": self.timed_out,
        }

    def to_context_string(self) -> str:
        """转换为 LLM 可用的上下文字符串"""
        if self.tool_result:
            return self.tool_result.to_context_string()
        return f"[工具调用失败] {self.tool_name}: {self.error}"


class ToolExecutor:
    """
    工具统一执行器

    使用示例：
        executor = ToolExecutor()
        result = await executor.execute(tool, order_id="123456")
        result = await executor.execute_by_name("query_logistics", order_id="123456")
        results = await executor.execute_sequence([
            (tool1, {"order_id": "123456"}),
            (tool2, {"order_id": "123456"}),
        ])
    """

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    async def execute(
        self,
        tool: BaseTool,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> ToolExecutionResult:
        """
        执行单个工具

        Args:
            tool: 工具实例
            timeout: 超时秒数（None 使用默认值）
            **kwargs: 工具参数

        Returns:
            ToolExecutionResult: 包含完整执行信息的结果
        """
        effective_timeout = timeout or self.timeout
        tool_name = tool.name

        logger.info(f"[ToolExecutor] 执行 {tool_name}, 参数: {kwargs}, 超时: {effective_timeout}s")

        # 1. 参数校验
        validation_error = tool.validate_params(**kwargs)
        if validation_error:
            logger.warning(f"[ToolExecutor] {tool_name} 参数校验失败: {validation_error}")
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_args=kwargs,
                success=False,
                error=validation_error,
            )

        # 2. 执行工具（带超时控制）
        start_time = time.perf_counter()
        try:
            tool_result = await asyncio.wait_for(
                tool.execute(**kwargs),
                timeout=effective_timeout,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                f"[ToolExecutor] {tool_name} 执行完成: "
                f"success={tool_result.success}, latency={latency_ms:.1f}ms"
            )

            return ToolExecutionResult(
                tool_name=tool_name,
                tool_args=kwargs,
                tool_result=tool_result,
                success=tool_result.success,
                error=tool_result.error if not tool_result.success else "",
                latency_ms=latency_ms,
            )

        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            error_msg = f"工具 {tool_name} 执行超时（{effective_timeout}秒）"
            logger.error(f"[ToolExecutor] {error_msg}")

            return ToolExecutionResult(
                tool_name=tool_name,
                tool_args=kwargs,
                success=False,
                error=error_msg,
                latency_ms=latency_ms,
                timed_out=True,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            error_msg = f"工具 {tool_name} 执行异常: {str(e)}"
            logger.error(f"[ToolExecutor] {error_msg}", exc_info=True)

            return ToolExecutionResult(
                tool_name=tool_name,
                tool_args=kwargs,
                success=False,
                error=error_msg,
                latency_ms=latency_ms,
            )

    async def execute_by_name(
        self,
        tool_name: str,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> ToolExecutionResult:
        """
        通过工具名称执行（从 Registry 查找）

        Args:
            tool_name: 工具注册名称
            timeout: 超时秒数
            **kwargs: 工具参数
        """
        from app.tools.tool_registry import tool_registry

        tool = tool_registry.get(tool_name)
        if tool is None:
            logger.error(f"[ToolExecutor] 工具未找到: {tool_name}")
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_args=kwargs,
                success=False,
                error=f"工具 '{tool_name}' 未注册",
            )

        return await self.execute(tool, timeout=timeout, **kwargs)

    async def execute_sequence(
        self,
        steps: list[tuple[BaseTool, dict[str, Any]]],
        stop_on_failure: bool = True,
    ) -> list[ToolExecutionResult]:
        """
        顺序执行多个工具

        Args:
            steps: [(tool, params), ...] 执行步骤列表
            stop_on_failure: 失败时是否中断后续步骤

        Returns:
            执行结果列表
        """
        results: list[ToolExecutionResult] = []

        for tool, params in steps:
            result = await self.execute(tool, **params)
            results.append(result)

            if not result.success and stop_on_failure:
                logger.warning(
                    f"[ToolExecutor] 顺序执行中断: {tool.name} 失败 - {result.error}"
                )
                break

        return results


# 全局单例
tool_executor = ToolExecutor()
