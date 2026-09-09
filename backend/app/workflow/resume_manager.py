"""
Workflow Resume Engine - Stage 5 工作流恢复系统

支持：
- User Resume
- System Resume
- Auto Resume
- Human Resume

恢复不重新启动 Workflow，而是从有效 Checkpoint 的 current_node / state 继续。
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any

from app.workflow.branch_manager import branch_manager
from app.workflow.checkpoint_manager import workflow_checkpoint_manager
from app.workflow.decision_tracer import decision_tracer
from app.workflow.governance import workflow_governance
from app.workflow.lifecycle_manager import LifecycleTransitionError, lifecycle_manager
from app.workflow.models import (
    ResumeType,
    TraceEventType,
    WorkflowResume,
    WorkflowStatus,
)
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class ResumeManager:
    """Workflow 恢复管理器"""

    def resume_from_checkpoint(
        self,
        *,
        checkpoint_id: str,
        resume_type: ResumeType,
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowResume:
        """从任意有效 Checkpoint 恢复 Workflow"""
        checkpoint = workflow_checkpoint_manager.load_checkpoint(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        workflow_state = copy.deepcopy(checkpoint.state_snapshot)
        branch_state = copy.deepcopy(checkpoint.branch_state) or self._reconstruct_branch_state(
            checkpoint.workflow_id,
            checkpoint.branch_id,
        )
        slot_state = copy.deepcopy(checkpoint.slot_state)
        context_state = {
            "workflow_context": copy.deepcopy(checkpoint.workflow_context),
            "memory_context": copy.deepcopy(checkpoint.memory_context),
        }
        trace_state = copy.deepcopy(checkpoint.trace_state) or {
            "decision_trace_reference": checkpoint.decision_trace_reference,
            "timeline": [
                event.to_dict()
                for event in decision_tracer.get_timeline(checkpoint.workflow_id)
            ],
        }
        if checkpoint.trace_state:
            trace_state.setdefault("decision_trace_reference", checkpoint.decision_trace_reference)

        workflow_state["workflow_status"] = WorkflowStatus.RESUMING.value
        workflow_state["resume_from_checkpoint"] = checkpoint_id
        workflow_state["current_node"] = checkpoint.current_node
        workflow_state["collected_slots"] = slot_state.get("collected_slots", {})
        workflow_state["workflow_context"] = checkpoint.workflow_context

        resume = WorkflowResume(
            resume_id=f"res_{uuid.uuid4().hex[:12]}",
            workflow_id=checkpoint.workflow_id,
            branch_id=checkpoint.branch_id,
            checkpoint_reference=checkpoint_id,
            resume_type=resume_type,
            workflow_state=workflow_state,
            branch_state=branch_state,
            slot_state=slot_state,
            context_state=context_state,
            trace_state=trace_state,
            resume_time=datetime.now(),
            metadata=metadata or {},
        )
        resume.valid, errors = self.validate_resume(resume)
        resume.validation_errors = errors

        passed, results = workflow_governance.validate_resume(resume)
        if not passed:
            reason = "; ".join(r.message for r in results if not r.passed)
            decision_tracer.trace_event(
                event_type=TraceEventType.RESUME,
                workflow_id=checkpoint.workflow_id,
                branch_id=checkpoint.branch_id,
                node=checkpoint.current_node,
                reason=f"resume rejected: {reason}",
                payload={"governance": [r.to_dict() for r in results]},
                trace_reference=checkpoint_id,
            )
            raise ValueError(f"Invalid resume: {reason}")

        try:
            current = lifecycle_manager.get_status(checkpoint.workflow_id)
            if current in (WorkflowStatus.CREATED, WorkflowStatus.ACTIVE, WorkflowStatus.RUNNING):
                lifecycle_manager.set_status(checkpoint.workflow_id, WorkflowStatus.INTERRUPTED)
            lifecycle_manager.resume(
                checkpoint.workflow_id,
                actor=actor,
                reason=f"{resume_type.value} resume from {checkpoint_id}",
            )
        except LifecycleTransitionError:
            raise

        branch_manager.update_execution_state(
            checkpoint.workflow_id,
            current_node=checkpoint.current_node,
            status=WorkflowStatus.RESUMING,
            collected_slots=slot_state.get("collected_slots", {}),
        )

        workflow_repository.save(
            "resume",
            resume.resume_id,
            checkpoint.workflow_id,
            resume,
            metadata={
                "checkpoint_id": checkpoint_id,
                "resume_type": resume_type.value,
                "valid": resume.valid,
            },
        )
        workflow_repository.save(
            "workflow_state",
            checkpoint.workflow_id,
            checkpoint.workflow_id,
            workflow_state,
            metadata={"status": WorkflowStatus.RESUMING.value, "resumable": False},
        )
        decision_tracer.trace_event(
            event_type=TraceEventType.RESUME,
            workflow_id=checkpoint.workflow_id,
            branch_id=checkpoint.branch_id,
            node=checkpoint.current_node,
            reason=f"{resume_type.value} resume",
            payload={
                "resume_id": resume.resume_id,
                "workflow_id": resume.workflow_id,
                "branch_id": resume.branch_id,
                "checkpoint_reference": checkpoint_id,
                "resume_type": resume_type.value,
                "valid": resume.valid,
                "record_type": "resume",
                "recovered_node": resume.workflow_state.get("current_node"),
                "workflow_status": resume.workflow_state.get("workflow_status"),
                "branch_snapshot": {
                    "workflow_id": resume.branch_state.get("workflow_id", resume.workflow_id),
                    "execution_id": resume.branch_state.get("execution_id", ""),
                    "branch_status": resume.branch_state.get("branch_status", ""),
                },
                "trace_event_count": resume.trace_state.get("audit_metadata", {}).get(
                    "event_count",
                    len(resume.trace_state.get("trace_events", resume.trace_state.get("timeline", []))),
                ),
            },
            trace_reference=checkpoint_id,
        )
        logger.info(
            f"[Resume] workflow={checkpoint.workflow_id} checkpoint={checkpoint_id} "
            f"type={resume_type.value}"
        )
        return resume

    def user_resume(self, checkpoint_id: str) -> WorkflowResume:
        return self.resume_from_checkpoint(checkpoint_id=checkpoint_id, resume_type=ResumeType.USER, actor="user")

    def system_resume(self, checkpoint_id: str) -> WorkflowResume:
        return self.resume_from_checkpoint(checkpoint_id=checkpoint_id, resume_type=ResumeType.SYSTEM)

    def auto_resume(self, workflow_id: str) -> WorkflowResume:
        checkpoint = workflow_checkpoint_manager.latest_recoverable(workflow_id)
        if not checkpoint:
            raise ValueError(f"No recoverable checkpoint for workflow: {workflow_id}")
        return self.resume_from_checkpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            resume_type=ResumeType.AUTO,
        )

    def human_resume(self, checkpoint_id: str, assigned_agent: str = "") -> WorkflowResume:
        return self.resume_from_checkpoint(
            checkpoint_id=checkpoint_id,
            resume_type=ResumeType.HUMAN,
            actor=assigned_agent or "human",
            metadata={"assigned_agent": assigned_agent},
        )

    def validate_resume(self, resume: WorkflowResume) -> tuple[bool, list[str]]:
        """Resume Validation"""
        errors: list[str] = []
        if not resume.checkpoint_reference:
            errors.append("missing checkpoint_reference")
        if not resume.workflow_state:
            errors.append("missing workflow_state")
        if not resume.branch_id:
            errors.append("missing branch_id")
        if "current_node" not in resume.workflow_state:
            errors.append("workflow_state missing current_node")
        return len(errors) == 0, errors

    def _reconstruct_branch_state(self, workflow_id: str, branch_id: str) -> dict[str, Any]:
        execution = branch_manager.get_execution(workflow_id)
        if not execution:
            return {"workflow_id": workflow_id, "branch_id": branch_id, "reconstructed": True}
        return execution.to_dict()


resume_manager = ResumeManager()
