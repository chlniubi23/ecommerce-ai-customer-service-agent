"""
统一 API 响应模型

职责：
- 定义所有 API 接口的统一返回结构
- 提供成功/失败响应的标准化构建方法
- 确保前端可以用统一逻辑解析所有接口

设计理念：
- 所有 API 返回同一个信封结构: { success, data, error, metadata }
- 前端只需检查 success 字段即可判断请求是否成功
- data 字段使用泛型，不同接口返回不同业务数据
- error 字段结构化，包含错误码和描述
- metadata 字段携带请求级元信息（追踪、耗时等）

架构位置：
- 模型层基础设施，被所有 API 路由引用
- 所有路由的返回值都必须经过此模块包装

扩展规划：
- Phase 2 (Tool Calling): metadata 增加 tool_calls 执行记录
- Phase 3 (RAG): metadata 增加 retrieval_sources 引用来源
- Phase 4 (LangGraph): metadata 增加 workflow_state 工作流状态
- Phase 5 (Memory): metadata 增加 session_id / conversation_id

为什么企业项目需要这样设计：
1. 统一前端解析逻辑，降低前后端协作成本
2. 错误码标准化，便于国际化和监控告警
3. trace_id 贯穿请求链路，支持分布式追踪
4. metadata 可扩展，不影响已有业务字段
"""

import uuid
from datetime import datetime, timezone
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel, Field

# 泛型类型变量，用于 data 字段的类型参数化
T = TypeVar("T")


class ErrorDetail(BaseModel):
    """
    结构化错误信息

    统一的错误描述模型，替代之前的纯字符串错误。
    前端可根据 code 做分支处理，根据 message 做用户提示。

    Attributes:
        code: 错误码，大写下划线格式（如 LLM_SERVICE_ERROR）
              用于前端程序化判断错误类型
        message: 人类可读的错误描述，可直接展示给用户
        detail: 技术细节，仅开发环境返回，生产环境为 null

    扩展规划：
    - 后续可增加 field_errors 字段，支持表单级字段校验错误
    - 后续可增加 retry_after 字段，支持限流重试提示
    """
    code: str = Field(
        ...,
        description="错误码，大写下划线格式，如 LLM_SERVICE_ERROR"
    )
    message: str = Field(
        ...,
        description="人类可读的错误描述"
    )
    detail: Optional[str] = Field(
        default=None,
        description="技术细节，仅开发环境返回"
    )


class ResponseMetadata(BaseModel):
    """
    响应元信息

    携带请求级别的追踪和诊断信息。
    当前阶段只包含基础字段，后续按需扩展。

    Attributes:
        trace_id: 请求唯一标识，用于日志追踪和问题排查
        timestamp: 响应生成的 UTC 时间戳
        model: 本次请求使用的 LLM 模型名称（可选）
        usage: Token 使用统计（可选）

    扩展规划（预留字段，当前不实现，后续按需添加）：
    - execution_time_ms: 请求处理耗时（毫秒）
    - tool_calls: Tool Calling 执行记录列表
    - retrieval_sources: RAG 检索到的文档来源
    - workflow_state: LangGraph 工作流当前状态
    - session_id: 会话标识
    """
    trace_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:16],
        description="请求唯一标识，16位十六进制字符串"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="响应生成时间，ISO 8601 UTC 格式"
    )
    model: Optional[str] = Field(
        default=None,
        description="本次请求使用的 LLM 模型"
    )
    usage: Optional[dict] = Field(
        default=None,
        description="Token 使用统计"
    )


class BaseResponse(BaseModel, Generic[T]):
    """
    统一 API 响应信封

    所有 API 接口的返回值都使用此结构包装。
    通过泛型 T 参数化 data 字段的类型。

    Attributes:
        success: 请求是否成功
        data: 业务数据，成功时为具体类型，失败时为 None
        error: 错误信息，成功时为 None，失败时为 ErrorDetail
        metadata: 请求级元信息

    示例 - 成功响应:
        {
            "success": true,
            "data": {"reply": "您好！", "model": "deepseek-v4-flash"},
            "error": null,
            "metadata": {"trace_id": "a1b2c3d4e5f6g7h8", "timestamp": "..."}
        }

    示例 - 失败响应:
        {
            "success": false,
            "data": null,
            "error": {"code": "LLM_SERVICE_ERROR", "message": "..."},
            "metadata": {"trace_id": "a1b2c3d4e5f6g7h8", "timestamp": "..."}
        }
    """
    success: bool = Field(..., description="请求是否成功")
    data: Optional[T] = Field(default=None, description="业务数据")
    error: Optional[ErrorDetail] = Field(default=None, description="错误信息")
    metadata: ResponseMetadata = Field(
        default_factory=ResponseMetadata,
        description="请求级元信息"
    )


def success_response(
    data: T,
    model: Optional[str] = None,
    usage: Optional[dict] = None,
) -> BaseResponse[T]:
    """
    构建成功响应

    工厂函数，简化成功响应的创建过程。
    所有 API 路由在返回成功结果时应调用此函数。

    Args:
        data: 业务数据对象
        model: LLM 模型名称（可选，聊天接口使用）
        usage: Token 使用统计（可选）

    Returns:
        BaseResponse[T]: 标准化的成功响应

    示例:
        return success_response(
            data=ChatData(reply="你好"),
            model="deepseek-v4-flash"
        )
    """
    return BaseResponse(
        success=True,
        data=data,
        error=None,
        metadata=ResponseMetadata(model=model, usage=usage),
    )


def error_response(
    code: str,
    message: str,
    detail: Optional[str] = None,
) -> BaseResponse:
    """
    构建错误响应

    工厂函数，简化错误响应的创建过程。
    所有 API 路由在返回错误时应调用此函数，
    而非直接 raise HTTPException。

    Args:
        code: 错误码（大写下划线格式）
        message: 人类可读的错误描述
        detail: 技术细节（可选，仅开发环境）

    Returns:
        BaseResponse: 标准化的错误响应

    示例:
        return error_response(
            code="LLM_SERVICE_ERROR",
            message="AI 服务暂时不可用",
            detail=str(e)
        )
    """
    return BaseResponse(
        success=False,
        data=None,
        error=ErrorDetail(code=code, message=message, detail=detail),
        metadata=ResponseMetadata(),
    )
