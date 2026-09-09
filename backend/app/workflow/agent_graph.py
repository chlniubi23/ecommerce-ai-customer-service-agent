"""Agent Graph Layer - Phase 6 Stage 6."""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any

from app.workflow.decision_tracer import decision_tracer
from app.workflow.models import (
    AgentExecutionContext,
    AgentGraphEdge,
    AgentGraphNode,
    TraceEventType,
)
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class AgentGraph:
    """Workflow -> Agent -> Node extension layer over the existing graph runtime."""

    def __init__(self):
        self._nodes: dict[str, AgentGraphNode] = {}
        self._edges: dict[str, AgentGraphEdge] = {}

    def add_agent_node(self, node: AgentGraphNode) -> AgentGraphNode:
        self._nodes[node.node_id] = node
        workflow_repository.save(
            "agent_graph_node",
            node.node_id,
            "system",
            node,
            metadata={"agent_id": node.agent_id},
            preserve_created_at=False,
        )
        return node

    def add_agent_edge(self, edge: AgentGraphEdge) -> AgentGraphEdge:
        self._edges[edge.edge_id] = edge
        workflow_repository.save(
            "agent_graph_edge",
            edge.edge_id,
            "system",
            edge,
            metadata={"from_agent": edge.from_agent, "to_agent": edge.to_agent},
            preserve_created_at=False,
        )
        return edge

    def create_execution(
        self,
        *,
        workflow_id: str,
        current_agent: str,
        workflow_state: dict[str, Any],
        context_state: dict[str, Any] | None = None,
        checkpoint_reference: str = "",
    ) -> AgentExecutionContext:
        execution = AgentExecutionContext(
            execution_id=f"aexec_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            current_agent=current_agent,
            next_agent="",
            agent_execution_path=[current_agent] if current_agent else [],
            collaboration_path=[],
            workflow_state=copy.deepcopy(workflow_state),
            context_state=copy.deepcopy(context_state or {}),
            checkpoint_reference=checkpoint_reference,
            updated_at=datetime.now(),
        )
        self.persist_execution(execution)
        decision_tracer.trace_event(
            event_type=TraceEventType.AGENT_ROUTED,
            workflow_id=workflow_id,
            node="agent_graph",
            reason="agent execution created",
            payload={
                "execution_id": execution.execution_id,
                "current_agent": current_agent,
                "agent_execution_path": execution.agent_execution_path,
            },
        )
        return execution

    def transition(
        self,
        *,
        execution: AgentExecutionContext,
        next_agent: str,
        workflow_state: dict[str, Any] | None = None,
        context_state: dict[str, Any] | None = None,
        reason: str = "",
    ) -> AgentExecutionContext:
        previous = execution.current_agent
        execution.next_agent = next_agent
        execution.current_agent = next_agent
        if next_agent:
            execution.agent_execution_path.append(next_agent)
        execution.collaboration_path.append({
            "from_agent": previous,
            "to_agent": next_agent,
            "reason": reason,
            "transition_time": datetime.now().isoformat(),
        })
        if workflow_state is not None:
            execution.workflow_state = copy.deepcopy(workflow_state)
        if context_state is not None:
            execution.context_state = copy.deepcopy(context_state)
        execution.updated_at = datetime.now()
        self.persist_execution(execution)
        decision_tracer.trace_event(
            event_type=TraceEventType.AGENT_TRANSFER,
            workflow_id=execution.workflow_id,
            node="agent_graph",
            reason=reason or "agent graph transition",
            payload={
                "execution_id": execution.execution_id,
                "from_agent": previous,
                "to_agent": next_agent,
                "agent_execution_path": execution.agent_execution_path,
            },
        )
        return execution

    def persist_execution(self, execution: AgentExecutionContext) -> None:
        workflow_repository.save(
            "agent_execution",
            execution.execution_id,
            execution.workflow_id,
            execution,
            metadata={"current_agent": execution.current_agent},
            preserve_created_at=False,
        )
        workflow_repository.save(
            "agent_state",
            execution.workflow_id,
            execution.workflow_id,
            execution.to_dict(),
            metadata={"execution_id": execution.execution_id},
        )

    def load_execution(self, execution_id: str) -> AgentExecutionContext | None:
        record = workflow_repository.load("agent_execution", execution_id)
        return self._execution_from_payload(record.get("payload", {})) if record else None

    def recover_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        record = workflow_repository.load("agent_state", workflow_id)
        if not record:
            return None
        payload = record.get("payload", {})
        decision_tracer.trace_event(
            event_type=TraceEventType.AGENT_RECOVERY,
            workflow_id=workflow_id,
            node="agent_graph",
            reason="agent workflow recovered",
            payload={
                "current_agent": payload.get("current_agent"),
                "agent_execution_path": payload.get("agent_execution_path", []),
                "collaboration_path": payload.get("collaboration_path", []),
            },
        )
        return payload

    def _execution_from_payload(self, payload: dict[str, Any]) -> AgentExecutionContext | None:
        if not payload:
            return None
        return AgentExecutionContext(
            execution_id=payload["execution_id"],
            workflow_id=payload["workflow_id"],
            current_agent=payload.get("current_agent", ""),
            next_agent=payload.get("next_agent", ""),
            agent_execution_path=payload.get("agent_execution_path", []),
            collaboration_path=payload.get("collaboration_path", []),
            workflow_state=payload.get("workflow_state", {}),
            context_state=payload.get("context_state", {}),
            checkpoint_reference=payload.get("checkpoint_reference", ""),
            status=payload.get("status", "active"),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
            metadata=payload.get("metadata", {}),
        )


agent_graph = AgentGraph()
