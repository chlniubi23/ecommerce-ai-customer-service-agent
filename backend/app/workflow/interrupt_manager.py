"""
Workflow Interrupt Engine - Stage 5 工作流中断机制

支持：
- Missing Slot
- Waiting User Input
- Waiting External Tool
- Waiting Human Agent
- Timeout
- Manual Pause
- Business Rule Pause
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
from app.workflow.lifecycle_manager import lifecycle_manager
from app.workflow.models import (
    CheckpointType,
    InterruptReason,
    TraceEventType,
    WorkflowInterrupt,
    WorkflowStatus,
    WorkflowType,
)
from app.workflow.registry import workflow_registry
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class WorkflowInterruptManager:
    """统一中断管理器"""

    REASON_STATUS = {
        InterruptReason.MISSING_SLOT: WorkflowStatus.WAITING_USER,
        InterruptReason.WAITING_USER_INPUT: WorkflowStatus.WAITING_USER,
        InterruptReason.WAITING_EXTERNAL_TOOL: WorkflowStatus.WAITING_TOOL,
        InterruptReason.WAITING_HUMAN_AGENT: WorkflowStatus.WAITING_HUMAN,
        InterruptReason.TIMEOUT: WorkflowStatus.INTERRUPTED,
        InterruptReason.MANUAL_PAUSE: WorkflowStatus.INTERRUPTED,
        InterruptReason.BUSINESS_RULE_PAUSE: WorkflowStatus.INTERRUPTED,
    }

    def create_interrupt(
        self,
        *,
        workflow_id: str,
        branch_id: str,
        state: dict[str, Any],
        interrupt_reason: InterruptReason,
        current_node: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowInterrupt:
        """创建中断点并保存恢复准备信息"""
        current_node = current_node or state.get("current_node", "")
        workflow_type = self._workflow_type_from_state(state)

        checkpoint = workflow_checkpoint_manager.create_checkpoint(
            workflow_id=workflow_id,
            branch_id=branch_id,
            current_node=current_node,
            state=state,
            checkpoint_type=CheckpointType.RECOVERY,
            metadata={"interrupt_reason": interrupt_reason.value},
        )

        interrupt = WorkflowInterrupt(
            interrupt_id=f"int_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            branch_id=branch_id,
            workflow_type=workflow_type,
            current_node=current_node,
            workflow_state=copy.deepcopy(state),
            interrupt_reason=interrupt_reason,
            interrupt_time=datetime.now(),
            checkpoint_reference=checkpoint.checkpoint_id,
            status=self.REASON_STATUS[interrupt_reason],
            metadata=metadata or {},
        )

        passed, results = workflow_governance.validate_interrupt(interrupt)
        if not passed:
            reason = "; ".join(r.message for r in results if not r.passed)
            decision_tracer.trace_event(
                event_type=TraceEventType.INTERRUPT,
                workflow_id=workflow_id,
                branch_id=branch_id,
                node=current_node,
                reason=f"interrupt rejected: {reason}",
                payload={"governance": [r.to_dict() for r in results]},
            )
            raise ValueError(f"Invalid interrupt: {reason}")

        state["workflow_status"] = interrupt.status.value
        state["interrupt_info"] = interrupt.to_dict()

        current_status = lifecycle_manager.get_status(workflow_id)
        if current_status == WorkflowStatus.CREATED:
            lifecycle_manager.activate(workflow_id, reason="activate before interrupt")
            current_status = lifecycle_manager.get_status(workflow_id)
        elif current_status == WorkflowStatus.RESUMING:
            lifecycle_manager.activate(workflow_id, reason="activate after resume before interrupt")
            current_status = lifecycle_manager.get_status(workflow_id)

        lifecycle_manager.transition(
            workflow_id=workflow_id,
            action=self._status_action(interrupt.status),
            from_status=current_status,
            target_status=interrupt.status,
            reason=interrupt_reason.value,
            metadata={"target_status": interrupt.status.value},
        )

        branch_manager.update_execution_state(
            workflow_id,
            current_node=current_node,
            status=interrupt.status,
            error=None,
        )

        workflow_repository.save(
            "interrupt",
            interrupt.interrupt_id,
            workflow_id,
            interrupt,
            metadata={
                "branch_id": branch_id,
                "reason": interrupt_reason.value,
                "checkpoint_id": checkpoint.checkpoint_id,
            },
        )
        workflow_repository.save(
            "workflow_state",
            workflow_id,
            workflow_id,
            state,
            metadata={"status": interrupt.status.value, "resumable": True},
        )
        decision_tracer.trace_event(
            event_type=TraceEventType.INTERRUPT,
            workflow_id=workflow_id,
            branch_id=branch_id,
            node=current_node,
            reason=interrupt_reason.value,
            payload={
                "interrupt_id": interrupt.interrupt_id,
                "workflow_id": workflow_id,
                "branch_id": branch_id,
                "workflow_type": workflow_type.value,
                "current_node": current_node,
                "interrupt_reason": interrupt_reason.value,
                "workflow_status": interrupt.status.value,
                "checkpoint_reference": checkpoint.checkpoint_id,
                "record_type": "interrupt",
            },
            trace_reference=checkpoint.checkpoint_id,
        )
        logger.info(
            f"[Interrupt] workflow={workflow_id} reason={interrupt_reason.value} "
            f"checkpoint={checkpoint.checkpoint_id}"
        )
        return interrupt

    def prepare_resume(self, interrupt_id: str) -> dict[str, Any] | None:
        """加载中断记录，为 Resume 做准备"""
        record = workflow_repository.load("interrupt", interrupt_id)
        if not record:
            return None
        payload = record.get("payload", {})
        checkpoint_id = payload.get("checkpoint_reference", "")
        checkpoint = workflow_checkpoint_manager.load_checkpoint(checkpoint_id)
        if not checkpoint:
            return None
        return {
            "interrupt": payload,
            "checkpoint": checkpoint.to_dict(),
            "state": checkpoint.state_snapshot,
        }

    def get_interrupt(self, interrupt_id: str) -> dict[str, Any] | None:
        record = workflow_repository.load("interrupt", interrupt_id)
        return record.get("payload") if record else None

    def list_interrupts(self, workflow_id: str) -> list[dict[str, Any]]:
        return [
            record.get("payload", {})
            for record in workflow_repository.query(record_type="interrupt", workflow_id=workflow_id)
        ]

    def _workflow_type_from_state(self, state: dict[str, Any]) -> WorkflowType:
        intent = state.get("current_intent", "")
        return workflow_registry.find_by_intent(intent) or WorkflowType.GENERAL

    def _status_action(self, status: WorkflowStatus):
        # WAITING_* 状态不是公开 LifecycleAction，但仍需走统一 transition。
        # 这里用 INTERRUPT 动作承载状态变化，并通过 metadata 标明目标状态。
        from app.workflow.models import LifecycleAction
        return LifecycleAction.INTERRUPT


workflow_interrupt_manager = WorkflowInterruptManager()
