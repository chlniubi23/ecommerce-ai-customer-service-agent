"""Supervisor Agent Framework - Phase 6 Stage 6."""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any

from app.workflow.agent_registry import agent_registry
from app.workflow.agent_router import agent_router_engine
from app.workflow.decision_tracer import decision_tracer
from app.workflow.governance import workflow_governance
from app.workflow.models import (
    AgentRoute,
    AgentRouteType,
    AgentStatus,
    TraceEventType,
)
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """Coordinate multi-agent execution with global governance visibility."""

    supervisor_agent_id = "agent_supervisor"

    def monitor_selection(self, route: AgentRoute) -> dict[str, Any]:
        decision = {
            "decision_id": f"sdec_{uuid.uuid4().hex[:12]}",
            "workflow_id": route.workflow_id,
            "supervisor_agent": self.supervisor_agent_id,
            "decision_type": "selection_monitoring",
            "selected_agents": route.selected_agents,
            "valid": route.valid,
            "created_at": datetime.now().isoformat(),
        }
        self._persist_and_trace(decision, reason="agent selection monitored")
        return decision

    def monitor_execution(
        self,
        *,
        workflow_id: str,
        agent_state: dict[str, Any],
    ) -> dict[str, Any]:
        current_agent = agent_state.get("current_agent", "")
        agent = agent_registry.get_agent(current_agent)
        passed, results = workflow_governance.validate_agent_availability(agent)
        decision = {
            "decision_id": f"sdec_{uuid.uuid4().hex[:12]}",
            "workflow_id": workflow_id,
            "supervisor_agent": self.supervisor_agent_id,
            "decision_type": "execution_monitoring",
            "current_agent": current_agent,
            "valid": passed,
            "governance": [result.to_dict() for result in results],
            "created_at": datetime.now().isoformat(),
        }
        self._persist_and_trace(decision, reason="agent execution monitored")
        return decision

    def handle_failure(
        self,
        *,
        workflow_id: str,
        failed_agent: str,
        workflow_state: dict[str, Any],
        context_state: dict[str, Any] | None = None,
        reason: str = "",
    ) -> AgentRoute:
        if agent_registry.get_agent(failed_agent):
            agent_registry.update_status(failed_agent, AgentStatus.FAILED)
        route = agent_router_engine.route(
            workflow_id=workflow_id,
            state=workflow_state,
            context=context_state or {},
            required_capabilities=[],
            allow_multi=False,
            escalate_to_supervisor=True,
        )
        route.route_type = AgentRouteType.SUPERVISOR_ESCALATION
        route.metadata["failure_reason"] = reason
        route.metadata["failed_agent"] = failed_agent
        workflow_repository.save(
            "agent_route",
            route.route_id,
            workflow_id,
            route,
            metadata={"supervisor_recovery": True},
        )
        decision = {
            "decision_id": f"sdec_{uuid.uuid4().hex[:12]}",
            "workflow_id": workflow_id,
            "supervisor_agent": self.supervisor_agent_id,
            "decision_type": "failure_recovery",
            "failed_agent": failed_agent,
            "new_agent": route.current_agent,
            "reason": reason,
            "created_at": datetime.now().isoformat(),
        }
        self._persist_and_trace(decision, reason="agent failure recovery")
        decision_tracer.trace_event(
            event_type=TraceEventType.AGENT_RECOVERY,
            workflow_id=workflow_id,
            node="supervisor_agent",
            reason=reason or "agent recovered",
            payload=decision,
        )
        return route

    def redistribute_task(
        self,
        *,
        workflow_id: str,
        workflow_state: dict[str, Any],
        context_state: dict[str, Any] | None = None,
    ) -> AgentRoute:
        return agent_router_engine.route(
            workflow_id=workflow_id,
            state=copy.deepcopy(workflow_state),
            context=copy.deepcopy(context_state or {}),
            allow_multi=True,
            escalate_to_supervisor=True,
        )

    def _persist_and_trace(self, decision: dict[str, Any], *, reason: str) -> None:
        workflow_repository.save(
            "supervisor_decision",
            decision["decision_id"],
            decision["workflow_id"],
            decision,
            metadata={"decision_type": decision.get("decision_type", "")},
            preserve_created_at=False,
        )
        decision_tracer.trace_event(
            event_type=TraceEventType.SUPERVISOR_DECISION,
            workflow_id=decision["workflow_id"],
            node="supervisor_agent",
            reason=reason,
            payload=decision,
        )


supervisor_agent = SupervisorAgent()
