"""
Human Handoff System - Stage 5 AI 与人工客服协同

支持：
- AI -> Human
- Human -> AI
- Handoff Request / Approval / Processing / Completion / AI Resume
- 转人工期间保持 workflow 上下文
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any

from app.workflow.decision_tracer import decision_tracer
from app.workflow.interrupt_manager import workflow_interrupt_manager
from app.workflow.models import (
    HandoffStatus,
    HumanHandoff,
    InterruptReason,
    TraceEventType,
    WorkflowStatus,
)
from app.workflow.repository import workflow_repository
from app.workflow.resume_manager import resume_manager

logger = logging.getLogger(__name__)


class HumanHandoffManager:
    """人工转接管理器"""

    def request_handoff(
        self,
        *,
        workflow_id: str,
        branch_id: str,
        state: dict[str, Any],
        handoff_reason: str,
        assigned_agent: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> HumanHandoff:
        """AI -> Human：创建转人工请求并中断 workflow"""
        interrupt = workflow_interrupt_manager.create_interrupt(
            workflow_id=workflow_id,
            branch_id=branch_id,
            state=state,
            interrupt_reason=InterruptReason.WAITING_HUMAN_AGENT,
            current_node=state.get("current_node", "human_handoff"),
            metadata={"handoff_reason": handoff_reason},
        )
        handoff = HumanHandoff(
            handoff_id=f"handoff_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            branch_id=branch_id,
            handoff_reason=handoff_reason,
            handoff_time=datetime.now(),
            handoff_status=HandoffStatus.REQUESTED,
            assigned_agent=assigned_agent,
            workflow_state=copy.deepcopy(state),
            metadata={
                **(metadata or {}),
                "interrupt_id": interrupt.interrupt_id,
                "checkpoint_reference": interrupt.checkpoint_reference,
            },
        )
        self._save_and_trace(handoff, "handoff requested")
        return handoff

    def approve_handoff(self, handoff_id: str, assigned_agent: str) -> HumanHandoff:
        """Handoff Approval"""
        handoff = self._load(handoff_id)
        handoff.handoff_status = HandoffStatus.APPROVED
        handoff.assigned_agent = assigned_agent
        self._save_and_trace(handoff, "handoff approved")
        return handoff

    def start_processing(self, handoff_id: str) -> HumanHandoff:
        """Human Processing"""
        handoff = self._load(handoff_id)
        handoff.handoff_status = HandoffStatus.IN_PROGRESS
        self._save_and_trace(handoff, "human processing started")
        return handoff

    def complete_handoff(
        self,
        handoff_id: str,
        completion_note: str = "",
        resume_ai: bool = True,
    ) -> HumanHandoff:
        """Human Completion，可选择立即 AI Resume"""
        handoff = self._load(handoff_id)
        handoff.handoff_status = HandoffStatus.COMPLETED
        handoff.resume_time = datetime.now()
        handoff.metadata["completion_note"] = completion_note
        self._save_and_trace(handoff, "handoff completed")

        if resume_ai:
            checkpoint_id = handoff.metadata.get("checkpoint_reference", "")
            if checkpoint_id:
                resume = resume_manager.human_resume(
                    checkpoint_id,
                    assigned_agent=handoff.assigned_agent,
                )
                handoff.metadata["resume_id"] = resume.resume_id
                handoff.workflow_state["workflow_status"] = WorkflowStatus.RESUMING.value
                self._save_and_trace(handoff, "ai resumed after handoff")
        return handoff

    def reject_handoff(self, handoff_id: str, reason: str = "") -> HumanHandoff:
        handoff = self._load(handoff_id)
        handoff.handoff_status = HandoffStatus.REJECTED
        handoff.metadata["reject_reason"] = reason
        self._save_and_trace(handoff, "handoff rejected")
        return handoff

    def get_handoff(self, handoff_id: str) -> HumanHandoff | None:
        record = workflow_repository.load("handoff", handoff_id)
        if not record:
            return None
        return self._from_payload(record.get("payload", {}))

    def list_handoffs(self, workflow_id: str) -> list[HumanHandoff]:
        return [
            self._from_payload(record.get("payload", {}))
            for record in workflow_repository.query(record_type="handoff", workflow_id=workflow_id)
        ]

    def _save_and_trace(self, handoff: HumanHandoff, reason: str) -> None:
        workflow_repository.save(
            "handoff",
            handoff.handoff_id,
            handoff.workflow_id,
            handoff,
            metadata={
                "status": handoff.handoff_status.value,
                "assigned_agent": handoff.assigned_agent,
            },
        )
        decision_tracer.trace_event(
            event_type=TraceEventType.HANDOFF,
            workflow_id=handoff.workflow_id,
            branch_id=handoff.branch_id,
            node="human_handoff_manager",
            reason=reason,
            payload={
                "handoff_id": handoff.handoff_id,
                "workflow_id": handoff.workflow_id,
                "branch_id": handoff.branch_id,
                "handoff_reason": handoff.handoff_reason,
                "handoff_status": handoff.handoff_status.value,
                "assigned_agent": handoff.assigned_agent,
                "checkpoint_reference": handoff.metadata.get("checkpoint_reference"),
                "resume_id": handoff.metadata.get("resume_id"),
                "record_type": "handoff",
            },
            trace_reference=handoff.metadata.get("checkpoint_reference"),
        )
        logger.info(
            f"[Handoff] {reason}: id={handoff.handoff_id} "
            f"workflow={handoff.workflow_id} status={handoff.handoff_status.value}"
        )

    def _load(self, handoff_id: str) -> HumanHandoff:
        handoff = self.get_handoff(handoff_id)
        if not handoff:
            raise ValueError(f"Handoff not found: {handoff_id}")
        return handoff

    def _from_payload(self, payload: dict[str, Any]) -> HumanHandoff:
        return HumanHandoff(
            handoff_id=payload["handoff_id"],
            workflow_id=payload["workflow_id"],
            branch_id=payload.get("branch_id", "main"),
            handoff_reason=payload.get("handoff_reason", ""),
            handoff_time=datetime.fromisoformat(payload["handoff_time"]),
            handoff_status=HandoffStatus(payload.get("handoff_status", HandoffStatus.REQUESTED.value)),
            assigned_agent=payload.get("assigned_agent", ""),
            resume_time=datetime.fromisoformat(payload["resume_time"]) if payload.get("resume_time") else None,
            workflow_state=payload.get("workflow_state", {}),
            metadata=payload.get("metadata", {}),
        )


human_handoff_manager = HumanHandoffManager()
