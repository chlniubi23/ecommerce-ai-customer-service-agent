"""Agent-to-Agent Collaboration Framework - Phase 6 Stage 6."""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any

from app.workflow.agent_registry import agent_registry
from app.workflow.decision_tracer import decision_tracer
from app.workflow.governance import workflow_governance
from app.workflow.models import (
    AgentHandoff,
    AgentHandoffType,
    TraceEventType,
)
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class AgentHandoffManager:
    """Preserve workflow context while moving work between agents."""

    def handoff(
        self,
        *,
        workflow_id: str,
        from_agent: str,
        to_agent: str,
        workflow_state: dict[str, Any],
        context_state: dict[str, Any],
        handoff_reason: str,
        handoff_type: AgentHandoffType = AgentHandoffType.HANDOFF,
        conversation_history: list[dict[str, Any]] | None = None,
        decision_trace_reference: str = "",
        checkpoint_reference: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AgentHandoff:
        agent_registry.initialize_defaults()
        handoff = AgentHandoff(
            handoff_id=f"ahandoff_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            from_agent=from_agent,
            to_agent=to_agent,
            handoff_type=handoff_type,
            handoff_reason=handoff_reason,
            workflow_state=copy.deepcopy(workflow_state),
            context_state=copy.deepcopy(context_state),
            conversation_history=copy.deepcopy(conversation_history or []),
            decision_trace_reference=decision_trace_reference,
            checkpoint_reference=checkpoint_reference,
            handoff_time=datetime.now(),
            metadata=metadata or {},
        )
        passed, results = workflow_governance.validate_agent_handoff(handoff, agent_registry)
        handoff.metadata["governance"] = [result.to_dict() for result in results]
        if not passed:
            decision_tracer.trace_event(
                event_type=TraceEventType.AGENT_HANDOFF,
                workflow_id=workflow_id,
                node="agent_handoff_manager",
                reason="agent handoff rejected",
                payload={"handoff_id": handoff.handoff_id, "governance": handoff.metadata["governance"]},
            )
            raise ValueError("Invalid agent handoff")

        self._persist(handoff)
        self._update_agent_state(handoff)
        event_type = {
            AgentHandoffType.HANDOFF: TraceEventType.AGENT_HANDOFF,
            AgentHandoffType.TRANSFER: TraceEventType.AGENT_TRANSFER,
            AgentHandoffType.DELEGATION: TraceEventType.AGENT_HANDOFF,
            AgentHandoffType.ESCALATION: TraceEventType.AGENT_ESCALATION,
        }[handoff_type]
        decision_tracer.trace_event(
            event_type=event_type,
            workflow_id=workflow_id,
            node="agent_handoff_manager",
            reason=handoff_reason,
            payload={
                "handoff_id": handoff.handoff_id,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "handoff_type": handoff_type.value,
                "checkpoint_reference": checkpoint_reference,
                "context_preserved": bool(handoff.context_state),
            },
            trace_reference=checkpoint_reference or decision_trace_reference,
        )
        logger.info("[AgentHandoff] workflow=%s %s->%s", workflow_id, from_agent, to_agent)
        return handoff

    def transfer(self, **kwargs) -> AgentHandoff:
        kwargs["handoff_type"] = AgentHandoffType.TRANSFER
        return self.handoff(**kwargs)

    def delegate(self, **kwargs) -> AgentHandoff:
        kwargs["handoff_type"] = AgentHandoffType.DELEGATION
        return self.handoff(**kwargs)

    def escalate(self, **kwargs) -> AgentHandoff:
        kwargs["handoff_type"] = AgentHandoffType.ESCALATION
        kwargs.setdefault("to_agent", "agent_supervisor")
        return self.handoff(**kwargs)

    def get_handoff(self, handoff_id: str) -> AgentHandoff | None:
        record = workflow_repository.load("agent_handoff", handoff_id)
        return self._from_payload(record.get("payload", {})) if record else None

    def list_handoffs(self, workflow_id: str) -> list[AgentHandoff]:
        return [
            self._from_payload(record.get("payload", {}))
            for record in workflow_repository.query(record_type="agent_handoff", workflow_id=workflow_id)
        ]

    def _persist(self, handoff: AgentHandoff) -> None:
        workflow_repository.save(
            "agent_handoff",
            handoff.handoff_id,
            handoff.workflow_id,
            handoff,
            metadata={
                "from_agent": handoff.from_agent,
                "to_agent": handoff.to_agent,
                "handoff_type": handoff.handoff_type.value,
            },
            preserve_created_at=False,
        )

    def _update_agent_state(self, handoff: AgentHandoff) -> None:
        current = workflow_repository.load("agent_state", handoff.workflow_id)
        payload = current.get("payload", {}) if current else {}
        path = list(payload.get("agent_execution_path", []))
        if not path or path[-1] != handoff.from_agent:
            path.append(handoff.from_agent)
        path.append(handoff.to_agent)
        collaboration = list(payload.get("collaboration_path", []))
        collaboration.append({
            "handoff_id": handoff.handoff_id,
            "from_agent": handoff.from_agent,
            "to_agent": handoff.to_agent,
            "handoff_type": handoff.handoff_type.value,
            "handoff_time": handoff.handoff_time.isoformat(),
        })
        workflow_repository.save(
            "agent_state",
            handoff.workflow_id,
            handoff.workflow_id,
            {
                **payload,
                "workflow_id": handoff.workflow_id,
                "current_agent": handoff.to_agent,
                "previous_agent": handoff.from_agent,
                "agent_execution_path": path,
                "collaboration_path": collaboration,
                "workflow_state": copy.deepcopy(handoff.workflow_state),
                "context_state": copy.deepcopy(handoff.context_state),
                "checkpoint_reference": handoff.checkpoint_reference,
                "updated_at": datetime.now().isoformat(),
            },
            metadata={"current_agent": handoff.to_agent},
        )

    def _from_payload(self, payload: dict[str, Any]) -> AgentHandoff:
        return AgentHandoff(
            handoff_id=payload["handoff_id"],
            workflow_id=payload["workflow_id"],
            from_agent=payload["from_agent"],
            to_agent=payload["to_agent"],
            handoff_type=AgentHandoffType(payload["handoff_type"]),
            handoff_reason=payload.get("handoff_reason", ""),
            workflow_state=payload.get("workflow_state", {}),
            context_state=payload.get("context_state", {}),
            conversation_history=payload.get("conversation_history", []),
            decision_trace_reference=payload.get("decision_trace_reference", ""),
            checkpoint_reference=payload.get("checkpoint_reference", ""),
            handoff_time=datetime.fromisoformat(payload["handoff_time"]),
            status=payload.get("status", "completed"),
            metadata=payload.get("metadata", {}),
        )


agent_handoff_manager = AgentHandoffManager()
