"""
Workflow Context Recovery - 工作流上下文恢复

职责：
- 用户中断后恢复会话
- Workflow 暂停后恢复
- Slot 补全后恢复原工作流
- 工具执行完成后恢复
- 跨轮会话恢复

设计原则：
- Context Preservation：上下文完整保存
- Seamless Resume：无缝恢复执行
- State Consistency：状态一致性保证
- Traceable：恢复过程可追踪
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
GraphState = dict  # legacy alias; LangGraph experiment layer (app.graph/app.state) removed
from app.workflow.models import WorkflowType, WorkflowStatus

logger = logging.getLogger(__name__)


@dataclass
class RecoveryPoint:
    """
    恢复点

    保存工作流的恢复信息。
    """
    recovery_id: str                           # 恢复点 ID
    session_id: str                            # 会话 ID
    workflow_type: WorkflowType                # 工作流类型
    workflow_status: WorkflowStatus            # 工作流状态
    current_node: str                          # 当前节点
    next_node: str                             # 下一个节点
    workflow_path: list[str]                   # 执行路径
    state_snapshot: dict[str, Any]             # 状态快照
    recovery_reason: str                       # 恢复原因
    created_at: datetime = field(default_factory=datetime.now)
    recovered_at: Optional[datetime] = None
    is_recovered: bool = False

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "recovery_id": self.recovery_id,
            "session_id": self.session_id,
            "workflow_type": self.workflow_type.value,
            "workflow_status": self.workflow_status.value,
            "current_node": self.current_node,
            "next_node": self.next_node,
            "workflow_path": self.workflow_path,
            "recovery_reason": self.recovery_reason,
            "created_at": self.created_at.isoformat(),
            "recovered_at": self.recovered_at.isoformat() if self.recovered_at else None,
            "is_recovered": self.is_recovered,
        }


class WorkflowRecoveryManager:
    """
    工作流恢复管理器

    管理工作流的保存和恢复。
    """

    def __init__(self):
        # 恢复点存储（按 session_id 存储）
        self._recovery_points: dict[str, RecoveryPoint] = {}
        # 恢复历史
        self._recovery_history: list[RecoveryPoint] = []

    def create_recovery_point(
        self,
        session_id: str,
        state: GraphState,
        reason: str,
    ) -> RecoveryPoint:
        """
        创建恢复点

        Args:
            session_id: 会话 ID
            state: Graph 状态
            reason: 恢复原因

        Returns:
            RecoveryPoint: 恢复点
        """
        # 生成恢复点 ID
        recovery_id = f"recovery_{session_id}_{int(datetime.now().timestamp())}"

        # 获取工作流信息
        current_intent = state.get("current_intent", "")
        from app.workflow.registry import workflow_registry
        workflow_type = workflow_registry.find_by_intent(current_intent) or WorkflowType.GENERAL

        # 创建状态快照
        state_snapshot = self._create_state_snapshot(state)

        # 创建恢复点
        recovery_point = RecoveryPoint(
            recovery_id=recovery_id,
            session_id=session_id,
            workflow_type=workflow_type,
            workflow_status=WorkflowStatus(state.get("workflow_status", "running")),
            current_node=state.get("current_node", ""),
            next_node=state.get("next_node", ""),
            workflow_path=list(state.get("workflow_path", [])),
            state_snapshot=state_snapshot,
            recovery_reason=reason,
        )

        # 存储恢复点
        self._recovery_points[session_id] = recovery_point

        logger.info(
            f"[RecoveryManager] 创建恢复点: {recovery_id} "
            f"(session={session_id}, reason={reason}, node={recovery_point.current_node})"
        )

        return recovery_point

    def get_recovery_point(self, session_id: str) -> Optional[RecoveryPoint]:
        """
        获取恢复点

        Args:
            session_id: 会话 ID

        Returns:
            RecoveryPoint: 恢复点
        """
        return self._recovery_points.get(session_id)

    def has_recovery_point(self, session_id: str) -> bool:
        """
        检查是否有恢复点

        Args:
            session_id: 会话 ID

        Returns:
            是否有恢复点
        """
        return session_id in self._recovery_points

    def recover_workflow(self, session_id: str) -> Optional[dict]:
        """
        恢复工作流

        Args:
            session_id: 会话 ID

        Returns:
            恢复的状态，如果没有恢复点则返回 None
        """
        recovery_point = self.get_recovery_point(session_id)
        if not recovery_point:
            logger.warning(f"[RecoveryManager] 未找到恢复点: {session_id}")
            return None

        # 标记已恢复
        recovery_point.is_recovered = True
        recovery_point.recovered_at = datetime.now()

        # 添加到恢复历史
        self._recovery_history.append(recovery_point)

        # 构建恢复状态
        recovered_state = dict(recovery_point.state_snapshot)
        recovered_state["workflow_status"] = "running"
        recovered_state["recovery_info"] = {
            "recovered": True,
            "recovery_id": recovery_point.recovery_id,
            "recovery_reason": recovery_point.recovery_reason,
            "recovered_at": recovery_point.recovered_at.isoformat(),
        }

        logger.info(
            f"[RecoveryManager] 恢复工作流: {recovery_point.recovery_id} "
            f"(session={session_id}, node={recovery_point.current_node})"
        )

        return recovered_state

    def clear_recovery_point(self, session_id: str) -> None:
        """
        清除恢复点

        Args:
            session_id: 会话 ID
        """
        if session_id in self._recovery_points:
            del self._recovery_points[session_id]
            logger.info(f"[RecoveryManager] 清除恢复点: {session_id}")

    def pause_workflow(self, session_id: str, state: GraphState) -> RecoveryPoint:
        """
        暂停工作流

        创建暂停恢复点。

        Args:
            session_id: 会话 ID
            state: Graph 状态

        Returns:
            RecoveryPoint: 恢复点
        """
        return self.create_recovery_point(
            session_id=session_id,
            state=state,
            reason="workflow_paused",
        )

    def handle_slot_completion(self, session_id: str, state: GraphState) -> RecoveryPoint:
        """
        处理 Slot 补全后的恢复

        Args:
            session_id: 会话 ID
            state: Graph 状态

        Returns:
            RecoveryPoint: 恢复点
        """
        return self.create_recovery_point(
            session_id=session_id,
            state=state,
            reason="slot_completion",
        )

    def handle_tool_completion(self, session_id: str, state: GraphState) -> RecoveryPoint:
        """
        处理工具执行完成后的恢复

        Args:
            session_id: 会话 ID
            state: Graph 状态

        Returns:
            RecoveryPoint: 恢复点
        """
        return self.create_recovery_point(
            session_id=session_id,
            state=state,
            reason="tool_completion",
        )

    def handle_user_interrupt(self, session_id: str, state: GraphState) -> RecoveryPoint:
        """
        处理用户中断

        Args:
            session_id: 会话 ID
            state: Graph 状态

        Returns:
            RecoveryPoint: 恢复点
        """
        return self.create_recovery_point(
            session_id=session_id,
            state=state,
            reason="user_interrupt",
        )

    def get_recovery_stats(self) -> dict:
        """
        获取恢复统计信息

        Returns:
            统计信息字典
        """
        total_recovery_points = len(self._recovery_points)
        total_recovered = len(self._recovery_history)

        # 按恢复原因统计
        reason_counts = {}
        for recovery in self._recovery_history:
            reason = recovery.recovery_reason
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        return {
            "active_recovery_points": total_recovery_points,
            "total_recovered": total_recovered,
            "recovery_reason_distribution": reason_counts,
        }

    def _create_state_snapshot(self, state: GraphState) -> dict[str, Any]:
        """
        创建状态快照

        保存关键状态字段。

        Args:
            state: Graph 状态

        Returns:
            状态快照
        """
        key_fields = [
            "user_input",
            "conversation_history",
            "session_id",
            "current_intent",
            "intent_confidence",
            "selected_agent",
            "selected_prompt",
            "slots_ready",
            "collected_slots",
            "waiting_for",
            "selected_tool",
            "tool_args",
            "tool_result",
            "tool_success",
            "rag_context",
            "rag_used",
            "workflow_status",
            "current_node",
            "next_node",
            "workflow_path",
            "trace_id",
        ]

        snapshot = {}
        for field in key_fields:
            if field in state:
                value = state[field]
                # 深拷贝可变对象
                if isinstance(value, (list, dict)):
                    import copy
                    snapshot[field] = copy.deepcopy(value)
                else:
                    snapshot[field] = value

        return snapshot

    def merge_recovered_state(
        self,
        current_state: GraphState,
        recovered_state: dict,
    ) -> GraphState:
        """
        合并恢复状态

        将恢复的状态与当前状态合并。

        Args:
            current_state: 当前状态
            recovered_state: 恢复的状态

        Returns:
            合并后的状态
        """
        merged_state = dict(current_state)

        # 恢复关键字段
        restore_fields = [
            "current_intent",
            "intent_confidence",
            "selected_agent",
            "collected_slots",
            "workflow_path",
            "rag_context",
        ]

        for field in restore_fields:
            if field in recovered_state:
                merged_state[field] = recovered_state[field]

        # 添加恢复信息
        merged_state["recovery_info"] = recovered_state.get("recovery_info", {})

        logger.debug(f"[RecoveryManager] 合并恢复状态: restored_fields={restore_fields}")

        return merged_state


# 全局单例
workflow_recovery_manager = WorkflowRecoveryManager()
