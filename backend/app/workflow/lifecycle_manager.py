"""
Workflow Lifecycle Manager - Stage 5 生命周期管理

定义并管理标准生命周期：
CREATED -> ACTIVE -> INTERRUPTED/WAITING_* -> RESUMING -> ACTIVE -> COMPLETED

所有状态转换必须经过 Workflow Governance 校验。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from app.workflow.decision_tracer import decision_tracer
from app.workflow.governance import workflow_governance
from app.workflow.models import (
    LifecycleAction,
    LifecycleTransition,
    TraceEventType,
    WorkflowStatus,
)
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class LifecycleTransitionError(Exception):
    """生命周期非法转换错误"""


class LifecycleManager:
    """统一 Workflow 生命周期管理器"""

    ACTION_TARGETS = {
        LifecycleAction.CREATE: WorkflowStatus.CREATED,
        LifecycleAction.ACTIVATE: WorkflowStatus.ACTIVE,
        LifecycleAction.INTERRUPT: WorkflowStatus.INTERRUPTED,
        LifecycleAction.RESUME: WorkflowStatus.RESUMING,
        LifecycleAction.COMPLETE: WorkflowStatus.COMPLETED,
        LifecycleAction.CANCEL: WorkflowStatus.CANCELLED,
        LifecycleAction.FAIL: WorkflowStatus.FAILED,
    }

    def __init__(self):
        self._current_status: dict[str, WorkflowStatus] = {}

    def create(self, workflow_id: str, actor: str = "system", reason: str = "") -> LifecycleTransition:
        return self.transition(
            workflow_id=workflow_id,
            action=LifecycleAction.CREATE,
            from_status=WorkflowStatus.CREATED,
            actor=actor,
            reason=reason or "workflow created",
            allow_same=True,
        )

    def activate(self, workflow_id: str, actor: str = "system", reason: str = "") -> LifecycleTransition:
        return self.transition(workflow_id, LifecycleAction.ACTIVATE, actor=actor, reason=reason)

    def interrupt(self, workflow_id: str, actor: str = "system", reason: str = "") -> LifecycleTransition:
        return self.transition(workflow_id, LifecycleAction.INTERRUPT, actor=actor, reason=reason)

    def resume(self, workflow_id: str, actor: str = "system", reason: str = "") -> LifecycleTransition:
        return self.transition(workflow_id, LifecycleAction.RESUME, actor=actor, reason=reason)

    def complete(self, workflow_id: str, actor: str = "system", reason: str = "") -> LifecycleTransition:
        return self.transition(workflow_id, LifecycleAction.COMPLETE, actor=actor, reason=reason)

    def cancel(self, workflow_id: str, actor: str = "system", reason: str = "") -> LifecycleTransition:
        return self.transition(workflow_id, LifecycleAction.CANCEL, actor=actor, reason=reason)

    def fail(self, workflow_id: str, actor: str = "system", reason: str = "") -> LifecycleTransition:
        return self.transition(workflow_id, LifecycleAction.FAIL, actor=actor, reason=reason)

    def transition(
        self,
        workflow_id: str,
        action: LifecycleAction,
        from_status: WorkflowStatus | None = None,
        target_status: WorkflowStatus | None = None,
        actor: str = "system",
        reason: str = "",
        metadata: dict[str, Any] | None = None,
        allow_same: bool = False,
    ) -> LifecycleTransition:
        """执行生命周期转换"""
        current = from_status or self._current_status.get(workflow_id, WorkflowStatus.CREATED)
        target = target_status or self.ACTION_TARGETS[action]

        if allow_same and current == target:
            passed = True
            validation = None
        else:
            passed, validation = workflow_governance.validate_lifecycle_transition(current, target)

        transition = LifecycleTransition(
            transition_id=f"life_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            action=action,
            from_status=current,
            to_status=target,
            timestamp=datetime.now(),
            actor=actor,
            reason=reason,
            valid=passed,
            metadata={
                **(metadata or {}),
                "governance": validation.to_dict() if validation else {"passed": True},
            },
        )

        workflow_repository.save(
            "lifecycle",
            transition.transition_id,
            workflow_id,
            transition,
            metadata={"action": action.value, "valid": passed},
        )

        decision_tracer.trace_event(
            event_type=TraceEventType.LIFECYCLE,
            workflow_id=workflow_id,
            node="lifecycle_manager",
            reason=reason or action.value,
            payload={
                "transition_id": transition.transition_id,
                "workflow_id": workflow_id,
                "action": action.value,
                "from_status": current.value,
                "to_status": target.value,
                "valid": passed,
                "actor": actor,
                "record_type": "lifecycle",
                "governance": transition.metadata.get("governance"),
            },
        )

        if not passed:
            logger.error(
                f"[Lifecycle] rejected workflow={workflow_id} "
                f"{current.value}->{target.value}"
            )
            raise LifecycleTransitionError(
                f"Invalid lifecycle transition: {current.value} -> {target.value}"
            )

        self._current_status[workflow_id] = target
        logger.info(
            f"[Lifecycle] workflow={workflow_id} {current.value}->{target.value} action={action.value}"
        )
        return transition

    def get_status(self, workflow_id: str) -> WorkflowStatus:
        """获取内存中的当前状态；无记录时默认为 CREATED"""
        return self._current_status.get(workflow_id, WorkflowStatus.CREATED)

    def set_status(self, workflow_id: str, status: WorkflowStatus) -> None:
        """从持久化恢复后重建当前状态"""
        self._current_status[workflow_id] = status


lifecycle_manager = LifecycleManager()
