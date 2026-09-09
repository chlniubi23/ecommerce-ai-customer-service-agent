"""
Workflow Recovery Manager - Stage 5 恢复记录与持久化

与 app.state.recovery 的区别：
- state.recovery 负责 GraphState 级恢复策略
- workflow.recovery_manager 负责 Workflow 级 Recovery Persistence / Trace / Repository
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any

from app.workflow.checkpoint_manager import workflow_checkpoint_manager
from app.workflow.decision_tracer import decision_tracer
from app.workflow.models import TraceEventType, WorkflowRecovery
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class WorkflowRecoveryStage5Manager:
    """Workflow 级恢复记录管理器"""

    def create_recovery(
        self,
        *,
        workflow_id: str,
        checkpoint_reference: str,
        recovery_reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowRecovery:
        checkpoint = workflow_checkpoint_manager.load_checkpoint(checkpoint_reference)
        if not checkpoint:
            raise ValueError(f"Checkpoint not found: {checkpoint_reference}")
        recovery = WorkflowRecovery(
            recovery_id=f"rec_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            checkpoint_reference=checkpoint_reference,
            recovery_reason=recovery_reason,
            recovered_state=copy.deepcopy(checkpoint.state_snapshot),
            created_at=datetime.now(),
            status="created",
            metadata=metadata or {},
        )
        workflow_repository.save(
            "recovery",
            recovery.recovery_id,
            workflow_id,
            recovery,
            metadata={"checkpoint_reference": checkpoint_reference},
        )
        decision_tracer.trace_event(
            event_type=TraceEventType.RECOVERY,
            workflow_id=workflow_id,
            branch_id=checkpoint.branch_id,
            node=checkpoint.current_node,
            reason=recovery_reason,
            payload={
                "recovery_id": recovery.recovery_id,
                "workflow_id": workflow_id,
                "checkpoint_reference": checkpoint_reference,
                "recovery_reason": recovery_reason,
                "status": recovery.status,
                "record_type": "recovery",
                "recovered_node": checkpoint.current_node,
            },
            trace_reference=checkpoint_reference,
        )
        logger.info(f"[WorkflowRecovery] created id={recovery.recovery_id} workflow={workflow_id}")
        return recovery

    def mark_completed(self, recovery_id: str) -> dict[str, Any] | None:
        return workflow_repository.update(
            "recovery",
            recovery_id,
            {"payload": {"status": "completed"}},
        )

    def get_recovery(self, recovery_id: str) -> dict[str, Any] | None:
        record = workflow_repository.load("recovery", recovery_id)
        return record.get("payload") if record else None


workflow_recovery_stage5_manager = WorkflowRecoveryStage5Manager()
