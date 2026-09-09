"""
Workflow Checkpoint Manager - Stage 5 检查点体系

能力：
- Auto Checkpoint
- Manual Checkpoint
- Recovery Checkpoint
- 多版本历史
- 最近可恢复点查询
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any

from app.workflow.branch_manager import branch_manager
from app.workflow.decision_tracer import decision_tracer
from app.workflow.governance import workflow_governance
from app.workflow.models import (
    CheckpointType,
    TraceEventType,
    WorkflowCheckpoint,
    WorkflowStatus,
)
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class WorkflowCheckpointManager:
    """Workflow 检查点管理器"""

    def __init__(self):
        self._versions: dict[str, list[str]] = {}

    def create_checkpoint(
        self,
        *,
        workflow_id: str,
        branch_id: str,
        current_node: str,
        state: dict[str, Any],
        checkpoint_type: CheckpointType = CheckpointType.AUTO,
        decision_trace_reference: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowCheckpoint:
        """创建检查点"""
        version = len(self._versions.get(workflow_id, [])) + 1
        checkpoint = WorkflowCheckpoint(
            checkpoint_id=f"wcp_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            branch_id=branch_id,
            current_node=current_node,
            workflow_status=self._status_from_state(state),
            state_snapshot=copy.deepcopy(state),
            slot_state=copy.deepcopy({
                "slots_ready": state.get("slots_ready"),
                "collected_slots": state.get("collected_slots", {}),
                "waiting_for": state.get("waiting_for", ""),
                "slot_metadata": state.get("slot_metadata", {}),
            }),
            memory_context=copy.deepcopy(
                state.get("memory_context", state.get("memory_state", {}))
            ),
            workflow_context=copy.deepcopy(state.get("workflow_context", {})),
            decision_trace_reference=decision_trace_reference,
            timestamp=datetime.now(),
            branch_state=self._branch_snapshot(workflow_id, branch_id),
            trace_state=self._trace_snapshot(workflow_id),
            checkpoint_type=checkpoint_type,
            version=version,
            metadata=metadata or {},
        )

        passed, results = workflow_governance.validate_checkpoint(checkpoint)
        if not passed:
            reason = "; ".join(r.message for r in results if not r.passed)
            decision_tracer.trace_event(
                event_type=TraceEventType.CHECKPOINT,
                workflow_id=workflow_id,
                branch_id=branch_id,
                node=current_node,
                reason=f"checkpoint rejected: {reason}",
                payload={"governance": [r.to_dict() for r in results]},
            )
            raise ValueError(f"Invalid checkpoint: {reason}")

        self._versions.setdefault(workflow_id, []).append(checkpoint.checkpoint_id)
        workflow_repository.save(
            "checkpoint",
            checkpoint.checkpoint_id,
            workflow_id,
            checkpoint,
            metadata={
                "branch_id": branch_id,
                "checkpoint_type": checkpoint_type.value,
                "version": version,
            },
        )
        decision_tracer.trace_event(
            event_type=TraceEventType.CHECKPOINT,
            workflow_id=workflow_id,
            branch_id=branch_id,
            node=current_node,
            reason=f"{checkpoint_type.value} checkpoint created",
            payload={
                "checkpoint_id": checkpoint.checkpoint_id,
                "workflow_id": workflow_id,
                "branch_id": branch_id,
                "current_node": current_node,
                "checkpoint_type": checkpoint_type.value,
                "version": version,
                "record_type": "checkpoint",
                "snapshot_complete": bool(checkpoint.branch_state and checkpoint.trace_state),
                "branch_snapshot": {
                    "workflow_id": checkpoint.branch_state.get("workflow_id", workflow_id),
                    "execution_id": checkpoint.branch_state.get("execution_id", ""),
                    "branch_status": checkpoint.branch_state.get("branch_status", ""),
                },
                "trace_snapshot": {
                    "event_count": checkpoint.trace_state.get("audit_metadata", {}).get("event_count", 0),
                    "event_sequence": checkpoint.trace_state.get("event_sequence", []),
                },
            },
            trace_reference=decision_trace_reference,
        )
        logger.info(
            f"[WorkflowCheckpoint] created id={checkpoint.checkpoint_id} "
            f"workflow={workflow_id} version={version}"
        )
        return checkpoint

    def auto_checkpoint(self, workflow_id: str, branch_id: str, current_node: str, state: dict[str, Any]) -> WorkflowCheckpoint:
        return self.create_checkpoint(
            workflow_id=workflow_id,
            branch_id=branch_id,
            current_node=current_node,
            state=state,
            checkpoint_type=CheckpointType.AUTO,
        )

    def manual_checkpoint(self, workflow_id: str, branch_id: str, current_node: str, state: dict[str, Any]) -> WorkflowCheckpoint:
        return self.create_checkpoint(
            workflow_id=workflow_id,
            branch_id=branch_id,
            current_node=current_node,
            state=state,
            checkpoint_type=CheckpointType.MANUAL,
        )

    def recovery_checkpoint(self, workflow_id: str, branch_id: str, current_node: str, state: dict[str, Any]) -> WorkflowCheckpoint:
        return self.create_checkpoint(
            workflow_id=workflow_id,
            branch_id=branch_id,
            current_node=current_node,
            state=state,
            checkpoint_type=CheckpointType.RECOVERY,
        )

    def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        """加载检查点"""
        record = workflow_repository.load("checkpoint", checkpoint_id)
        if not record:
            return None
        payload = record.get("payload", {})
        return self._from_payload(payload)

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """删除检查点"""
        deleted = workflow_repository.delete("checkpoint", checkpoint_id)
        if deleted:
            for ids in self._versions.values():
                if checkpoint_id in ids:
                    ids.remove(checkpoint_id)
        return deleted

    def history(self, workflow_id: str) -> list[WorkflowCheckpoint]:
        """检查点版本历史"""
        records = workflow_repository.query(record_type="checkpoint", workflow_id=workflow_id)
        checkpoints = [self._from_payload(record["payload"]) for record in records]
        return sorted([cp for cp in checkpoints if cp], key=lambda cp: cp.version)

    def latest_recoverable(self, workflow_id: str) -> WorkflowCheckpoint | None:
        """最近可恢复点查询"""
        checkpoints = self.history(workflow_id)
        if not checkpoints:
            return None
        return checkpoints[-1]

    def _status_from_state(self, state: dict[str, Any]) -> WorkflowStatus:
        raw = state.get("workflow_status") or state.get("status") or WorkflowStatus.ACTIVE.value
        try:
            return WorkflowStatus(raw)
        except ValueError:
            return WorkflowStatus.ACTIVE

    def _from_payload(self, payload: dict[str, Any]) -> WorkflowCheckpoint | None:
        if not payload:
            return None
        return WorkflowCheckpoint(
            checkpoint_id=payload["checkpoint_id"],
            workflow_id=payload["workflow_id"],
            branch_id=payload["branch_id"],
            current_node=payload["current_node"],
            workflow_status=WorkflowStatus(payload["workflow_status"]),
            state_snapshot=payload.get("state_snapshot", {}),
            slot_state=payload.get("slot_state", {}),
            memory_context=payload.get("memory_context", {}),
            workflow_context=payload.get("workflow_context", {}),
            decision_trace_reference=payload.get("decision_trace_reference", ""),
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            branch_state=payload.get("branch_state", {}),
            trace_state=payload.get("trace_state", {}),
            checkpoint_type=CheckpointType(payload.get("checkpoint_type", CheckpointType.AUTO.value)),
            version=int(payload.get("version", 1)),
            metadata=payload.get("metadata", {}),
        )

    def _branch_snapshot(self, workflow_id: str, branch_id: str) -> dict[str, Any]:
        """创建自包含 Branch Snapshot，不要求恢复时仍有 BranchManager 内存状态。"""
        execution = branch_manager.get_execution(workflow_id)
        if not execution:
            return {
                "workflow_id": workflow_id,
                "execution_id": "",
                "branch_id": branch_id,
                "branch_status": WorkflowStatus.ACTIVE.value,
                "branch_type": "unknown",
                "execution_state": {},
                "execution_path": [],
                "routing_context": {},
                "branch_metadata": {"source": "checkpoint_manager", "reconstructed": True},
            }
        data = execution.to_dict()
        return {
            "workflow_id": execution.context.workflow_id,
            "execution_id": execution.execution_id,
            "branch_id": execution.branch.branch_id,
            "branch_status": execution.context.status.value,
            "branch_type": execution.branch.branch_type.value,
            "execution_state": data,
            "execution_path": list(execution.context.visited_nodes),
            "routing_context": {
                "current_node": execution.context.current_node,
                "current_branch": execution.context.current_branch,
                "next_nodes": list(execution.branch.next_nodes),
                "parent_execution": execution.parent_execution,
                "child_executions": list(execution.child_executions),
            },
            "branch_metadata": dict(execution.branch.metadata),
        }

    def _trace_snapshot(self, workflow_id: str) -> dict[str, Any]:
        """创建自包含 Trace Snapshot，支持重启后的 replay/audit。"""
        timeline = [event.to_dict() for event in decision_tracer.get_timeline(workflow_id)]
        interrupt_timeline = [
            event.to_dict()
            for event in decision_tracer.get_interrupt_timeline(workflow_id)
        ]
        return {
            "trace_events": timeline,
            "trace_timeline": timeline,
            "event_sequence": [event["event_id"] for event in timeline],
            "audit_metadata": {
                "event_count": len(timeline),
                "captured_at": datetime.now().isoformat(),
                "source": "checkpoint_manager",
            },
            "replay_metadata": {
                "workflow_id": workflow_id,
                "event_count": len(timeline),
                "interrupt_event_count": len(interrupt_timeline),
            },
        }


workflow_checkpoint_manager = WorkflowCheckpointManager()
