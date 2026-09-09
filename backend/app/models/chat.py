"""
聊天请求数据模型

职责：
- 定义聊天 API 的请求体结构
- 提供请求数据验证

架构位置：
- 仅包含请求模型（ChatRequest）
- 响应模型已迁移至 base_response.py（统一信封）
- 消息模型已迁移至 message.py（标准 Message）
- 旧的 ChatResponse / ErrorResponse / ChatMessage 已废弃

扩展规划：
- Phase 4: 增加 session_id 字段
- Phase 5: 增加 user_id 字段
"""

from pydantic import BaseModel, Field
from app.models.message import MessageRole


class HistoryMessage(BaseModel):
    """
    对话历史中的精简消息

    仅包含 role 和 content，用于请求传输。
    相比完整 Message，减少不必要的字段传输。

    Attributes:
        role: 消息角色
        content: 消息内容
    """
    role: MessageRole
    content: str = Field(..., min_length=1, max_length=50000)


class ChatRequest(BaseModel):
    """
    聊天请求模型

    前端发送的请求体结构。
    包含用户消息、对话历史和会话 ID。

    Attributes:
        message: 用户当前输入的消息
        history: 对话历史（可选），用于上下文理解
        session_id: 会话 ID（可选），用于多轮对话状态恢复
    """
    message: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="用户输入的消息内容"
    )
    history: list[HistoryMessage] = Field(
        default=[],
        description="对话历史记录，用于保持上下文连贯"
    )
    session_id: str = Field(
        default="",
        description="会话 ID，用于多轮对话状态恢复"
    )
