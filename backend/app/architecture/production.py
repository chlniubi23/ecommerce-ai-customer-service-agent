"""Canonical production architecture map.

This module does not execute business logic. It documents the single production
entry and registry alignment created in Phase 8.5 Stage 2 so runtime, frontend,
admin and validation code can refer to the same source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProductionArchitectureRegistry:
    """Read-only map of the unified production runtime."""

    production_chat_entry: str = "/api/v1/chat"
    streaming_chat_entry: str = "/api/v1/chat/stream"
    frontend_chat_service: str = "frontend/services/chat.ts"
    agent_entry: str = "app.agents.agent.run"
    intent_router: str = "app.agents.classifier.classify_intent"
    flow_router: str = "app.router.agent_router.route"
    workflow_router: str = "app.router.registry.flow_registry"
    tool_runtime: str = "app.tools.tool_registry + app.tools.executors.tool_executor"
    database_boundary: str = "app.database.repositories"
    knowledge_entry: str = "KnowledgeFlow -> KnowledgeWorkflow -> KnowledgeAgent"
    knowledge_tool: str = "knowledge_search"
    retriever: str = "app.rag.services.retrieval_service"
    vector_store: str = "backend/vector_store/vectors.json"
    evaluation_suite: str = "backend/evaluation (routing eval, offline/live)"
    production_agents: tuple[str, ...] = (
        "ProductAgent",
        "LogisticsAgent",
        "RefundAgent",
        "ComplaintAgent",
        "SupervisorAgent",
        "KnowledgeAgent",
    )
    removed_runtime_entries: tuple[str, ...] = (
        "app.graph (LangGraph V1/V2 experiment layer)",
        "app.state (graph-only state layer)",
        "app.workflows (legacy orchestration engine)",
        "app.tools.mock_backend (in-memory mock data)",
        "agent task board API (/api/commerce/agent/tasks)",
    )
    intent_to_flow: dict[str, str] = field(default_factory=lambda: {
        "refund": "RefundFlow",
        "logistics_query": "LogisticsFlow",
        "order_query": "OrderFlow",
        "product_query": "ProductFlow",
        "knowledge_query": "KnowledgeFlow",
        "coupon_query": "CouponFlow",
        "ticket": "TicketFlow",
        "human_transfer": "HumanTransferFlow",
        "general": "GeneralFlow",
    })
    intent_to_agent: dict[str, str] = field(default_factory=lambda: {
        "refund": "RefundAgent",
        "logistics_query": "LogisticsAgent",
        "order_query": "ProductAgent",
        "product_query": "ProductAgent",
        "knowledge_query": "KnowledgeAgent",
        "coupon_query": "KnowledgeAgent",
        "ticket": "ComplaintAgent",
        "human_transfer": "SupervisorAgent",
        "general": "SupervisorAgent",
    })
    intent_to_tool: dict[str, list[str]] = field(default_factory=lambda: {
        "refund": ["refund_apply", "query_order"],
        "logistics_query": ["logistics_query"],
        "order_query": ["query_order"],
        "product_query": ["product_query", "query_inventory"],
        "knowledge_query": ["knowledge_search"],
        "ticket": ["create_ticket"],
        "complaint": ["complaint_create", "create_ticket"],
        "human_transfer": ["transfer_human"],
        "general": ["transfer_human", "create_ticket"],
    })

    def as_dict(self) -> dict[str, Any]:
        return {
            "production_chat_entry": self.production_chat_entry,
            "streaming_chat_entry": self.streaming_chat_entry,
            "frontend_chat_service": self.frontend_chat_service,
            "agent_entry": self.agent_entry,
            "intent_router": self.intent_router,
            "flow_router": self.flow_router,
            "workflow_router": self.workflow_router,
            "tool_runtime": self.tool_runtime,
            "database_boundary": self.database_boundary,
            "knowledge_entry": self.knowledge_entry,
            "knowledge_tool": self.knowledge_tool,
            "retriever": self.retriever,
            "vector_store": self.vector_store,
            "evaluation_suite": self.evaluation_suite,
            "production_agents": list(self.production_agents),
            "removed_runtime_entries": list(self.removed_runtime_entries),
            "intent_to_flow": self.intent_to_flow,
            "intent_to_agent": self.intent_to_agent,
            "intent_to_tool": self.intent_to_tool,
        }


production_architecture_registry = ProductionArchitectureRegistry()
PRODUCTION_ARCHITECTURE = production_architecture_registry.as_dict()
