"""
Session Manager - 会话记忆管理

职责：
- 管理用户会话状态（内存存储）
- 保存当前 Flow、FSM 状态、Slots、对话历史
- 支持 Flow 中断挂起 / 恢复（Suspend / Resume）
- 支持无效输入重试计数（Recovery）

数据结构：
  session_id → Session {
    current_flow,       # 当前所在 Flow（如 "refund"）
    current_state,      # FSM 当前状态（如 "WAIT_ORDER_ID"）
    waiting_for,        # 当前等待填充的 Slot（如 "order_id"）
    slots,              # 已收集的 Slot 值
    history,            # 对话历史
    suspended_flows,    # 被挂起的 Flow 栈
    retry_count,        # 当前 Slot 连续无效输入次数
    updated_at          # 最后更新时间
  }

扩展规划：
- Phase 5: 替换为 Redis 存储
- Phase 6: 持久化到数据库
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class SuspendedFlow:
    """
    被挂起的 Flow 快照

    当用户中途切换意图时，当前 Flow 状态被保存到此结构中，
    待新 Flow 完成后可恢复。
    """
    flow_name: str
    state: str
    waiting_for: str
    slots: dict[str, Any]
    timestamp: float


# 连续无效输入的最大重试次数
MAX_RETRY_COUNT = 3


class Session(BaseModel):
    """
    会话状态

    保存一个用户会话的完整上下文。
    FSM、Slot Filling、Flow 恢复都依赖此数据。
    支持 Flow 挂起/恢复 和无效输入重试计数。
    """
    session_id: str = Field(..., description="会话唯一 ID")
    current_flow: str = Field(default="", description="当前所在 Flow（如 refund, logistics_query）")
    current_state: str = Field(default="", description="FSM 当前状态（如 WAIT_ORDER_ID）")
    waiting_for: str = Field(default="", description="当前等待用户提供的 Slot 名称")
    slots: dict[str, Any] = Field(default_factory=dict, description="已收集的 Slot 值")
    history: list[dict[str, str]] = Field(default_factory=list, description="对话历史")
    suspended_flows: list[dict[str, Any]] = Field(default_factory=list, description="被挂起的 Flow 栈")
    retry_count: int = Field(default=0, description="当前 Slot 连续无效输入次数")
    pending_complaint: dict[str, Any] | None = Field(default=None, description="等待用户确认后才创建的投诉草稿")
    pending_refund: dict[str, Any] | None = Field(default=None, description="等待用户确认后才申请的退款草稿")
    updated_at: float = Field(default_factory=time.time, description="最后更新时间戳")

    def is_active(self) -> bool:
        """会话是否有进行中的流程"""
        return bool(self.current_flow and self.current_state)

    def is_completed(self) -> bool:
        """当前流程是否已完成"""
        return self.current_state in ("DONE", "")

    def clear_flow(self) -> None:
        """清除当前流程状态（流程完成后调用）"""
        self.current_flow = ""
        self.current_state = ""
        self.waiting_for = ""
        self.slots = {}
        self.retry_count = 0
        self.updated_at = time.time()

    def suspend_current_flow(self) -> None:
        """挂起当前 Flow（保存快照到 suspended_flows 栈）"""
        if not self.current_flow:
            return
        snapshot = {
            "flow_name": self.current_flow,
            "state": self.current_state,
            "waiting_for": self.waiting_for,
            "slots": dict(self.slots),
            "timestamp": time.time(),
        }
        self.suspended_flows.append(snapshot)
        logger.info(f"[Session] 挂起 Flow: {self.current_flow} (state={self.current_state})")
        self.current_flow = ""
        self.current_state = ""
        self.waiting_for = ""
        self.slots = {}
        self.retry_count = 0
        self.updated_at = time.time()

    def has_suspended_flow(self) -> bool:
        """是否有被挂起的 Flow"""
        return len(self.suspended_flows) > 0

    def resume_suspended_flow(self) -> dict[str, Any] | None:
        """恢复最近挂起的 Flow（从栈顶弹出）"""
        if not self.suspended_flows:
            return None
        snapshot = self.suspended_flows.pop()
        self.current_flow = snapshot["flow_name"]
        self.current_state = snapshot["state"]
        self.waiting_for = snapshot["waiting_for"]
        self.slots = snapshot["slots"]
        self.retry_count = 0
        self.updated_at = time.time()
        logger.info(f"[Session] 恢复 Flow: {self.current_flow} (state={self.current_state})")
        return snapshot

    def increment_retry(self) -> int:
        """增加重试计数，返回当前计数"""
        self.retry_count += 1
        self.updated_at = time.time()
        return self.retry_count

    def reset_retry(self) -> None:
        """重置重试计数（成功提取 Slot 后调用）"""
        self.retry_count = 0

    def update_slot(self, key: str, value: Any) -> None:
        """更新 Slot 值"""
        self.slots[key] = value
        self.updated_at = time.time()

    def add_history(self, role: str, content: str) -> None:
        """添加对话历史"""
        self.history.append({"role": role, "content": content})
        # 限制历史长度，保留最近 20 轮
        if len(self.history) > 40:
            self.history = self.history[-40:]
        self.updated_at = time.time()


# ===== Session Store =====
# 内存存储，Phase 5 替换为 Redis
_session_store: dict[str, Session] = {}

# Session 过期时间（秒）：30 分钟
SESSION_TTL = 1800


class SessionManager:
    """
    会话管理器

    提供 Session 的 CRUD 操作。
    当前使用内存 dict 存储，后续可替换为 Redis。

    使用方式：
        session = session_manager.get_or_create("session-123")
        session.current_flow = "refund"
        session_manager.save(session)
    """

    def get(self, session_id: str) -> Session | None:
        """获取会话，过期返回 None"""
        session = _session_store.get(session_id)
        if session is None:
            return None
        # 检查过期
        if time.time() - session.updated_at > SESSION_TTL:
            logger.info(f"[SessionManager] 会话过期: {session_id}")
            del _session_store[session_id]
            return None
        return session

    def get_or_create(self, session_id: str) -> Session:
        """获取或创建会话"""
        session = self.get(session_id)
        if session is None:
            session = Session(session_id=session_id)
            _session_store[session_id] = session
            logger.info(f"[SessionManager] 创建新会话: {session_id}")
        return session

    def save(self, session: Session) -> None:
        """保存会话"""
        session.updated_at = time.time()
        _session_store[session.session_id] = session

    def delete(self, session_id: str) -> None:
        """删除会话"""
        _session_store.pop(session_id, None)

    def list_active(self) -> list[str]:
        """列出所有活跃会话 ID"""
        now = time.time()
        return [
            sid for sid, s in _session_store.items()
            if now - s.updated_at <= SESSION_TTL
        ]


# 全局单例
session_manager = SessionManager()
