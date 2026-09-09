"""Agent Registry and Capability Framework - Phase 6 Stage 6."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.workflow.models import (
    AgentCapability,
    AgentDefinition,
    AgentStatus,
    AgentType,
    WorkflowType,
)
from app.workflow.repository import workflow_repository

logger = logging.getLogger(__name__)


class AgentRegistry:
    """System-level registry for agent identity, metadata and capabilities."""

    def __init__(self):
        self._agents: dict[str, AgentDefinition] = {}
        self._capabilities: dict[str, AgentCapability] = {}
        self._initialized = False

    def register_capability(self, capability: AgentCapability) -> AgentCapability:
        self._capabilities[capability.capability_id] = capability
        workflow_repository.save(
            "agent_capability",
            capability.capability_id,
            "system",
            capability,
            metadata={"name": capability.name},
            preserve_created_at=False,
        )
        return capability

    def register_agent(self, agent: AgentDefinition) -> AgentDefinition:
        agent.updated_at = datetime.now()
        self._agents[agent.agent_id] = agent
        workflow_repository.save(
            "agent",
            agent.agent_id,
            "system",
            agent,
            metadata={
                "agent_type": agent.agent_type.value,
                "status": agent.status.value,
            },
            preserve_created_at=False,
        )
        logger.info("[AgentRegistry] registered agent=%s type=%s", agent.agent_id, agent.agent_type.value)
        return agent

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id) or self._load_agent(agent_id)

    def list_agents(self, *, status: AgentStatus | None = None) -> list[AgentDefinition]:
        agents = list(self._agents.values())
        if status:
            agents = [agent for agent in agents if agent.status == status]
        return agents

    def discover_agents(self, capability_id: str | None = None) -> list[AgentDefinition]:
        agents = [
            agent for agent in self._agents.values()
            if agent.status in (AgentStatus.ACTIVE, AgentStatus.REGISTERED)
        ]
        if capability_id:
            agents = [agent for agent in agents if capability_id in agent.capabilities]
        return agents

    def update_status(self, agent_id: str, status: AgentStatus) -> AgentDefinition:
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        agent.status = status
        agent.updated_at = datetime.now()
        return self.register_agent(agent)

    def get_capability(self, capability_id: str) -> AgentCapability | None:
        return self._capabilities.get(capability_id) or self._load_capability(capability_id)

    def query_capabilities(
        self,
        *,
        intent: str = "",
        workflow_type: WorkflowType | str | None = None,
    ) -> list[AgentCapability]:
        workflow_value = workflow_type.value if hasattr(workflow_type, "value") else workflow_type
        matches: list[AgentCapability] = []
        for capability in self._capabilities.values():
            intent_match = bool(intent and intent in capability.intent_patterns)
            workflow_match = bool(workflow_value and workflow_value in capability.workflow_types)
            if intent_match or workflow_match or (not intent and not workflow_value):
                matches.append(capability)
        return matches

    def match_agents(
        self,
        *,
        intent: str = "",
        workflow_type: WorkflowType | str | None = None,
        required_capabilities: list[str] | None = None,
    ) -> list[AgentDefinition]:
        required = required_capabilities or [
            capability.capability_id
            for capability in self.query_capabilities(intent=intent, workflow_type=workflow_type)
        ]
        agents = self.discover_agents()
        if required:
            agents = [
                agent for agent in agents
                if any(capability_id in agent.capabilities for capability_id in required)
            ]
        return agents

    def validate_capability(self, capability_id: str) -> bool:
        capability = self.get_capability(capability_id)
        return bool(capability and capability.name)

    def initialize_defaults(self) -> None:
        if self._initialized:
            return
        defaults = [
            AgentCapability("cap_routing", "routing", "Analyze request and select agent", ["general"], [WorkflowType.GENERAL.value]),
            AgentCapability("cap_refund", "refund_processing", "Handle refund workflows", ["refund"], [WorkflowType.REFUND.value], ["order_id"]),
            AgentCapability("cap_refund_refund", "refund", "Handle refund requests", ["refund", "refund_request"], [WorkflowType.REFUND.value], ["order_id"]),
            AgentCapability("cap_refund_return", "return", "Handle return requests", ["return", "return_request"], [WorkflowType.REFUND.value], ["order_id"]),
            AgentCapability("cap_refund_exchange", "exchange", "Handle exchange requests", ["exchange", "exchange_request"], [WorkflowType.REFUND.value], ["order_id"]),
            AgentCapability("cap_refund_cancel_order", "cancel_order", "Handle order cancellation requests", ["cancel_order", "cancellation"], [WorkflowType.REFUND.value], ["order_id"]),
            AgentCapability("cap_refund_eligibility", "eligibility_evaluation", "Evaluate after-sales eligibility", ["eligibility_evaluation"], [WorkflowType.REFUND.value], ["order_id"]),
            AgentCapability("cap_refund_consultation", "after_sales_consultation", "Answer after-sales consultation questions", ["after_sales_consultation"], [WorkflowType.REFUND.value], ["order_id"]),
            AgentCapability("cap_refund_decision", "refund_decision_support", "Generate after-sales decisions", ["refund_decision_support"], [WorkflowType.REFUND.value], ["order_id"]),
            AgentCapability("cap_logistics", "logistics_query", "Handle logistics workflows", ["logistics_query"], [WorkflowType.LOGISTICS.value], ["order_id"]),
            AgentCapability("cap_logistics_tracking", "tracking", "Track shipment and tracking lifecycle", ["logistics_query", "tracking"], [WorkflowType.LOGISTICS.value], ["order_id"]),
            AgentCapability("cap_logistics_status", "shipment_status", "Analyze logistics status and next stage", ["shipment_status"], [WorkflowType.LOGISTICS.value], ["order_id"]),
            AgentCapability("cap_logistics_eta", "eta_prediction", "Predict ETA and delay risk", ["eta_prediction"], [WorkflowType.LOGISTICS.value], ["order_id"]),
            AgentCapability("cap_logistics_exception", "exception_analysis", "Analyze logistics exceptions and delivery risks", ["exception_analysis"], [WorkflowType.LOGISTICS.value], ["order_id"]),
            AgentCapability("cap_logistics_consultation", "delivery_consultation", "Answer delivery consultation questions", ["delivery_consultation"], [WorkflowType.LOGISTICS.value], ["order_id"]),
            AgentCapability("cap_logistics_decision", "delivery_decision_support", "Generate logistics decisions", ["delivery_decision_support"], [WorkflowType.LOGISTICS.value], ["order_id"]),
            AgentCapability("cap_product", "product_query", "Handle product workflows", ["product_query"], [WorkflowType.PRODUCT.value], ["product_id"]),
            AgentCapability("cap_complaint", "complaint_handling", "Handle complaint workflows", ["complaint"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_intake", "complaint_intake", "Create and register complaints", ["complaint_intake", "complaint"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_classification", "complaint_classification", "Classify complaint domains", ["complaint_classification"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_severity", "severity_assessment", "Assess complaint severity", ["severity_assessment"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_investigation", "complaint_investigation", "Investigate complaint facts", ["complaint_investigation"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_root_cause", "root_cause_analysis", "Analyze complaint root cause", ["root_cause_analysis"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_resolution", "complaint_resolution", "Generate complaint resolution", ["complaint_resolution"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_compensation", "compensation_recommendation", "Recommend complaint compensation", ["compensation_recommendation"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_recovery", "customer_recovery", "Create customer recovery plan", ["customer_recovery"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_consultation", "complaint_consultation", "Answer complaint consultation", ["complaint_consultation"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_complaint_decision", "complaint_decision_support", "Generate complaint decisions", ["complaint_decision_support"], [WorkflowType.COMPLAINT.value], ["complaint_reason"]),
            AgentCapability("cap_supervisor", "supervision", "Monitor and recover multi-agent execution", [], []),
        ]
        for capability in defaults:
            self.register_capability(capability)
        agents = [
            AgentDefinition("agent_routing", "Routing Agent", AgentType.ROUTING, "Entry routing agent", ["cap_routing"], AgentStatus.ACTIVE),
            AgentDefinition(
                "agent_refund",
                "Refund Agent",
                AgentType.REFUND,
                "Refund specialist agent",
                [
                    "cap_refund",
                    "cap_refund_refund",
                    "cap_refund_return",
                    "cap_refund_exchange",
                    "cap_refund_cancel_order",
                    "cap_refund_eligibility",
                    "cap_refund_consultation",
                    "cap_refund_decision",
                ],
                AgentStatus.ACTIVE,
            ),
            AgentDefinition(
                "agent_logistics",
                "Logistics Agent",
                AgentType.LOGISTICS,
                "Logistics specialist agent",
                [
                    "cap_logistics",
                    "cap_logistics_tracking",
                    "cap_logistics_status",
                    "cap_logistics_eta",
                    "cap_logistics_exception",
                    "cap_logistics_consultation",
                    "cap_logistics_decision",
                ],
                AgentStatus.ACTIVE,
            ),
            AgentDefinition("agent_product", "Product Agent", AgentType.PRODUCT, "Product specialist agent", ["cap_product"], AgentStatus.ACTIVE),
            AgentDefinition(
                "agent_complaint",
                "Complaint Agent",
                AgentType.COMPLAINT,
                "Complaint specialist agent",
                [
                    "cap_complaint",
                    "cap_complaint_intake",
                    "cap_complaint_classification",
                    "cap_complaint_severity",
                    "cap_complaint_investigation",
                    "cap_complaint_root_cause",
                    "cap_complaint_resolution",
                    "cap_complaint_compensation",
                    "cap_complaint_recovery",
                    "cap_complaint_consultation",
                    "cap_complaint_decision",
                ],
                AgentStatus.ACTIVE,
            ),
            AgentDefinition("agent_supervisor", "Supervisor Agent", AgentType.SUPERVISOR, "Cross-agent supervisor", ["cap_supervisor"], AgentStatus.ACTIVE),
            AgentDefinition("agent_general", "General Agent", AgentType.GENERAL, "Fallback general agent", ["cap_routing"], AgentStatus.ACTIVE),
        ]
        for agent in agents:
            self.register_agent(agent)
        self._initialized = True

    def restore(self) -> None:
        self._agents.clear()
        self._capabilities.clear()
        for record in workflow_repository.query(record_type="agent_capability"):
            capability = self._capability_from_payload(record.get("payload", {}))
            if capability:
                self._capabilities[capability.capability_id] = capability
        for record in workflow_repository.query(record_type="agent"):
            agent = self._agent_from_payload(record.get("payload", {}))
            if agent:
                self._agents[agent.agent_id] = agent

    def _load_agent(self, agent_id: str) -> AgentDefinition | None:
        record = workflow_repository.load("agent", agent_id)
        agent = self._agent_from_payload(record.get("payload", {})) if record else None
        if agent:
            self._agents[agent.agent_id] = agent
        return agent

    def _load_capability(self, capability_id: str) -> AgentCapability | None:
        record = workflow_repository.load("agent_capability", capability_id)
        capability = self._capability_from_payload(record.get("payload", {})) if record else None
        if capability:
            self._capabilities[capability.capability_id] = capability
        return capability

    def _agent_from_payload(self, payload: dict[str, Any]) -> AgentDefinition | None:
        if not payload:
            return None
        return AgentDefinition(
            agent_id=payload["agent_id"],
            agent_name=payload["agent_name"],
            agent_type=AgentType(payload["agent_type"]),
            description=payload.get("description", ""),
            capabilities=payload.get("capabilities", []),
            status=AgentStatus(payload.get("status", AgentStatus.REGISTERED.value)),
            metadata=payload.get("metadata", {}),
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
        )

    def _capability_from_payload(self, payload: dict[str, Any]) -> AgentCapability | None:
        if not payload:
            return None
        return AgentCapability(
            capability_id=payload["capability_id"],
            name=payload.get("name", ""),
            description=payload.get("description", ""),
            intent_patterns=payload.get("intent_patterns", []),
            workflow_types=payload.get("workflow_types", []),
            required_slots=payload.get("required_slots", []),
            metadata=payload.get("metadata", {}),
        )


agent_registry = AgentRegistry()
