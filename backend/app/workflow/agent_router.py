"""Multi-Agent Routing Engine - Phase 6 Stage 6."""

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
    AgentDefinition,
    AgentRoute,
    AgentRouteType,
    AgentStatus,
    TraceEventType,
    WorkflowType,
)
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class AgentRouterEngine:
    """Route requests to one or more agents without replacing workflow runtime."""

    def route(
        self,
        *,
        workflow_id: str,
        state: dict[str, Any],
        context: dict[str, Any] | None = None,
        required_capabilities: list[str] | None = None,
        allow_multi: bool = False,
        escalate_to_supervisor: bool = True,
    ) -> AgentRoute:
        agent_registry.initialize_defaults()
        context = context or {}
        intent = state.get("current_intent", "")
        workflow_type = self._workflow_type_from_state(state)
        required = required_capabilities or [
            capability.capability_id
            for capability in agent_registry.query_capabilities(
                intent=intent,
                workflow_type=workflow_type,
            )
        ]
        confidence = float(state.get("intent_confidence", 0.0))
        if not required and (not workflow_type or confidence < 0.85):
            candidates = []
        else:
            candidates = agent_registry.match_agents(
                intent=intent,
                workflow_type=workflow_type,
                required_capabilities=required,
            )
        selected = self._select_agents(candidates, allow_multi=allow_multi)
        route_type = AgentRouteType.MULTI if allow_multi and len(selected) > 1 else AgentRouteType.SINGLE
        routing_reason = "capability_based"

        fallback_agent = ""
        supervisor_agent = "agent_supervisor" if escalate_to_supervisor else ""
        if not selected:
            fallback = agent_registry.get_agent("agent_general")
            selected = [fallback] if fallback else []
            fallback_agent = fallback.agent_id if fallback else ""
            route_type = AgentRouteType.FALLBACK
            routing_reason = "fallback"

        if not selected and escalate_to_supervisor:
            supervisor = agent_registry.get_agent("agent_supervisor")
            selected = [supervisor] if supervisor else []
            route_type = AgentRouteType.SUPERVISOR_ESCALATION
            routing_reason = "supervisor_escalation"

        route = AgentRoute(
            route_id=f"aroute_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            selected_agents=[agent.agent_id for agent in selected if agent],
            current_agent=selected[0].agent_id if selected else "",
            fallback_agent=fallback_agent,
            supervisor_agent=supervisor_agent,
            route_type=route_type,
            routing_reason=routing_reason,
            required_capabilities=required,
            workflow_state=copy.deepcopy(state),
            context=copy.deepcopy(context),
            confidence=confidence,
            created_at=datetime.now(),
            metadata={
                "intent": intent,
                "workflow_type": workflow_type.value if workflow_type else "",
                "candidate_agents": [agent.agent_id for agent in candidates],
            },
        )

        passed, results = workflow_governance.validate_agent_route(route, agent_registry)
        route.valid = passed
        route.metadata["governance"] = [result.to_dict() for result in results]
        if not passed:
            decision_tracer.trace_event(
                event_type=TraceEventType.AGENT_ROUTED,
                workflow_id=workflow_id,
                node="agent_router",
                reason="agent route rejected",
                payload={"route_id": route.route_id, "governance": route.metadata["governance"]},
            )
            raise ValueError("Invalid agent route")

        workflow_repository.save(
            "agent_route",
            route.route_id,
            workflow_id,
            route,
            metadata={
                "current_agent": route.current_agent,
                "route_type": route.route_type.value,
            },
            preserve_created_at=False,
        )
        workflow_repository.save(
            "agent_state",
            workflow_id,
            workflow_id,
            {
                "workflow_id": workflow_id,
                "current_agent": route.current_agent,
                "selected_agents": route.selected_agents,
                "route_id": route.route_id,
                "agent_execution_path": [route.current_agent] if route.current_agent else [],
                "collaboration_path": [],
                "workflow_state": copy.deepcopy(state),
                "context_state": copy.deepcopy(context),
                "updated_at": datetime.now().isoformat(),
            },
            metadata={"route_id": route.route_id},
        )
        decision_tracer.trace_event(
            event_type=TraceEventType.AGENT_SELECTED,
            workflow_id=workflow_id,
            node="agent_router",
            reason=f"selected {route.current_agent}",
            payload={
                "route_id": route.route_id,
                "selected_agents": route.selected_agents,
                "required_capabilities": route.required_capabilities,
                "route_type": route.route_type.value,
            },
        )
        decision_tracer.trace_event(
            event_type=TraceEventType.AGENT_ROUTED,
            workflow_id=workflow_id,
            node="agent_router",
            reason=route.routing_reason,
            payload=route.to_dict(),
        )
        logger.info("[AgentRouter] workflow=%s agent=%s", workflow_id, route.current_agent)
        return route

    def dispatch(self, route: AgentRoute) -> dict[str, Any]:
        return {
            "workflow_id": route.workflow_id,
            "agent_id": route.current_agent,
            "selected_agents": route.selected_agents,
            "route_id": route.route_id,
            "workflow_state": copy.deepcopy(route.workflow_state),
            "context": copy.deepcopy(route.context),
        }

    def _select_agents(self, candidates: list[AgentDefinition], *, allow_multi: bool) -> list[AgentDefinition]:
        available = [
            agent for agent in candidates
            if agent.status in (AgentStatus.ACTIVE, AgentStatus.REGISTERED)
        ]
        if allow_multi:
            return available
        return available[:1]

    def _workflow_type_from_state(self, state: dict[str, Any]) -> WorkflowType | None:
        raw = state.get("workflow_type") or state.get("current_intent")
        intent_map = {
            "refund": WorkflowType.REFUND,
            "logistics_query": WorkflowType.LOGISTICS,
            "product_query": WorkflowType.PRODUCT,
            "complaint": WorkflowType.COMPLAINT,
            "general": WorkflowType.GENERAL,
        }
        if raw in intent_map:
            return intent_map[raw]
        try:
            return WorkflowType(raw)
        except Exception:
            return None


agent_router_engine = AgentRouterEngine()
