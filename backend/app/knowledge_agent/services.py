"""Knowledge Agent services built on the existing RAG stack."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.knowledge_agent.context import knowledge_context_builder
from app.knowledge_agent.models import KnowledgeSearchRequest, KnowledgeWorkflowResult
from app.models.message import Message, MessageRole
from app.services.llm import call_llm
from app.tools.executors.tool_executor import tool_executor
from app.tools.tool_registry import tool_registry
from app.workflow.decision_tracer import decision_tracer
from app.workflow.models import TraceEventType

logger = logging.getLogger(__name__)


class KnowledgeAgent:
    """Independent Knowledge Agent. It never accesses business databases."""

    agent_name = "KnowledgeAgent"

    async def answer(self, request: KnowledgeSearchRequest) -> KnowledgeWorkflowResult:
        started_at = time.perf_counter()
        tool = tool_registry.get("knowledge_search")
        if tool is None:
            raise RuntimeError("knowledge_search tool is not registered")

        tool_result = await tool_executor.execute(
            tool,
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score,
            category=request.category.value if request.category else "",
            workflow_id=request.workflow_id,
            session_id=request.session_id,
            history=request.history,
        )
        tool_call = tool_result.to_trace_dict()
        if not tool_result.success or not tool_result.tool_result:
            search_payload = {}
            answer = "抱歉，当前知识库中没有检索到足够的信息，暂时无法基于知识库回答这个问题。"
        else:
            search_payload = tool_result.tool_result.data
            answer = await self._generate_answer(request, search_payload)

        execution_time_ms = (time.perf_counter() - started_at) * 1000
        trace_metadata = self.trace(
            workflow_id=request.workflow_id,
            query=request.query,
            tool_call=tool_call,
            search_payload=search_payload,
            answer=answer,
            execution_time_ms=execution_time_ms,
        )

        from app.knowledge_agent.models import KnowledgeSearchResult
        from app.knowledge_agent.models import KnowledgeSourceCitation

        citations = [
            KnowledgeSourceCitation(
                document_name=item.get("document_name", ""),
                document_id=item.get("document_id", ""),
                chunk_id=item.get("chunk_id", ""),
                similarity_score=float(item.get("similarity_score", 0.0) or 0.0),
                category=item.get("category", ""),
                source=item.get("source", ""),
                metadata=item.get("metadata", {}),
            )
            for item in search_payload.get("citations", [])
            if isinstance(item, dict)
        ]

        search_result = KnowledgeSearchResult(
            query=search_payload.get("query", request.query),
            retrieval_query=search_payload.get("retrieval_query", request.query),
            documents=search_payload.get("documents", []),
            chunks=search_payload.get("chunks", []),
            citations=citations,
            context=search_payload.get("final_context", ""),
            answer_constraints=search_payload.get("answer_constraints", []),
            has_relevant=bool(search_payload.get("chunks", [])),
            debug_info=search_payload.get("debug_info", {}),
        )
        return KnowledgeWorkflowResult(
            answer=answer,
            search_result=search_result,
            tool_call=tool_call,
            trace_metadata=trace_metadata,
        )

    async def _generate_answer(self, request: KnowledgeSearchRequest, search_payload: dict[str, Any]) -> str:
        chunks = search_payload.get("chunks", [])
        if not chunks:
            return "根据当前知识库信息，暂时没有找到足够相关的内容。"
        from app.knowledge_agent.models import KnowledgeSearchResult

        search_result = KnowledgeSearchResult(
            query=request.query,
            retrieval_query=search_payload.get("retrieval_query", request.query),
            documents=search_payload.get("documents", []),
            chunks=chunks,
            context=search_payload.get("final_context", ""),
            answer_constraints=search_payload.get("answer_constraints", []),
            has_relevant=True,
            debug_info=search_payload.get("debug_info", {}),
        )
        system_prompt = knowledge_context_builder.build_system_prompt(search_result)
        user_message = (
            f"用户问题：{request.query}\n\n"
            "请基于上方知识库上下文回答，并保持客服口吻。"
        )
        return await call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            history=request.history,
            temperature=0.2,
            max_tokens=1200,
        )

    def trace(self, *, workflow_id: str, query: str, tool_call: dict[str, Any], search_payload: dict[str, Any], answer: str, execution_time_ms: float) -> dict[str, Any]:
        event = decision_tracer.trace_event(
            event_type=TraceEventType.DECISION,
            workflow_id=workflow_id,
            node="knowledge_agent",
            reason="Knowledge Agent answered with knowledge_search",
            payload={
                "query": query,
                "tool_call": tool_call,
                "retrieved_documents": search_payload.get("documents", []),
                "retrieved_chunks": search_payload.get("chunks", []),
                "citations": search_payload.get("citations", []),
                "final_context": search_payload.get("final_context", ""),
                "answer_preview": answer[:300],
                "agent_name": self.agent_name,
                "selected_tool": "knowledge_search",
                "retrieved_documents_count": len(search_payload.get("documents", [])),
                "retrieved_chunks_count": len(search_payload.get("chunks", [])),
                "execution_time_ms": round(execution_time_ms, 2),
            },
            actor=self.agent_name,
            source="knowledge_agent",
            metadata={
                "agent": self.agent_name,
                "workflow": "KnowledgeWorkflow",
                "tool": "knowledge_search",
                "trace_node": "Knowledge Agent",
                "chunks_count": len(search_payload.get("chunks", [])),
                "documents_count": len(search_payload.get("documents", [])),
                "execution_time_ms": round(execution_time_ms, 2),
            },
        )
        return {
            "trace_event_id": event.event_id,
            "trace_id": event.event_id,
            "knowledge_agent_trace": event.to_dict(),
            "agent_name": self.agent_name,
            "selected_tool": "knowledge_search",
            "retrieved_documents_count": len(search_payload.get("documents", [])),
            "retrieved_chunks_count": len(search_payload.get("chunks", [])),
            "execution_time_ms": round(execution_time_ms, 2),
        }


class KnowledgeWorkflow:
    """Workflow entrypoint: intent -> Knowledge Agent -> knowledge_search -> answer."""

    workflow_name = "KnowledgeWorkflow"

    def __init__(self, agent: KnowledgeAgent):
        self.agent = agent

    async def run(self, query: str, *, history: list[dict] | None = None, workflow_id: str = "knowledge_workflow", session_id: str = "", category: str = "", top_k: int = 5, min_score: float | None = None) -> KnowledgeWorkflowResult:
        from app.knowledge_agent.models import KnowledgeCategory

        intent_event = decision_tracer.trace_event(
            event_type=TraceEventType.DECISION,
            workflow_id=workflow_id,
            node="knowledge_intent",
            reason="Knowledge intent accepted before KnowledgeWorkflow",
            payload={
                "user_query": query,
                "intent_result": "knowledge_query",
                "confidence": 0.92,
                "timestamp": time.time(),
                "trace_node": "Intent",
            },
            session_id=session_id or None,
            actor="KnowledgeIntent",
            source="knowledge_intent",
            metadata={
                "intent": "knowledge_query",
                "confidence": 0.92,
                "trace_node": "Intent",
            },
        )
        router_event = decision_tracer.trace_event(
            event_type=TraceEventType.DECISION,
            workflow_id=workflow_id,
            node="knowledge_router",
            reason="Knowledge intent routed to KnowledgeAgent",
            payload={
                "user_query": query,
                "selected_agent": "KnowledgeAgent",
                "selected_workflow": self.workflow_name,
                "trace_node": "Router",
            },
            session_id=session_id or None,
            actor="KnowledgeRouter",
            source="knowledge_router",
            metadata={
                "agent": "KnowledgeAgent",
                "workflow": self.workflow_name,
                "trace_node": "Router",
            },
        )
        workflow_event = decision_tracer.trace_event(
            event_type=TraceEventType.DECISION,
            workflow_id=workflow_id,
            node="knowledge_workflow",
            reason="KnowledgeWorkflow started",
            payload={
                "user_query": query,
                "workflow_name": self.workflow_name,
                "trace_node": "Knowledge Workflow",
            },
            session_id=session_id or None,
            actor=self.workflow_name,
            source="knowledge_workflow",
            metadata={
                "workflow": self.workflow_name,
                "trace_node": "Knowledge Workflow",
            },
        )

        request = KnowledgeSearchRequest(
            query=query,
            workflow_id=workflow_id,
            session_id=session_id,
            category=KnowledgeCategory(category) if category else None,
            top_k=top_k,
            min_score=min_score,
            history=history or [],
        )
        result = await self.agent.answer(request)
        result.trace_metadata.update({
            "intent_trace": intent_event.to_dict(),
            "router_trace": router_event.to_dict(),
            "workflow_trace": workflow_event.to_dict(),
            "trace_chain": [
                {
                    "node": "Intent",
                    "trace_id": intent_event.event_id,
                    "event": intent_event.to_dict(),
                },
                {
                    "node": "Router",
                    "trace_id": router_event.event_id,
                    "event": router_event.to_dict(),
                },
                {
                    "node": "Knowledge Agent",
                    "trace_id": result.trace_metadata.get("trace_event_id"),
                    "event": result.trace_metadata.get("knowledge_agent_trace", {}),
                },
                {
                    "node": "Knowledge Workflow",
                    "trace_id": workflow_event.event_id,
                    "event": workflow_event.to_dict(),
                },
                {
                    "node": "Knowledge Tool",
                    "trace_id": result.tool_call.get("tool_name", "knowledge_search"),
                    "event": result.tool_call,
                },
                {
                    "node": "Retriever",
                    "trace_id": "retriever",
                    "event": result.search_result.debug_info,
                },
                {
                    "node": "Citation",
                    "trace_id": "citation",
                    "event": result.search_result.to_dict().get("citations", []),
                },
                {
                    "node": "Final Answer",
                    "trace_id": "final_answer",
                    "event": {"answer_preview": result.answer[:300]},
                },
            ],
        })
        return result

    async def as_message(self, query: str, *, history: list[dict] | None = None, workflow_id: str = "knowledge_workflow", session_id: str = "") -> tuple[Message, list[dict[str, Any]]]:
        result = await self.run(query, history=history, workflow_id=workflow_id, session_id=session_id)
        message = Message(role=MessageRole.ASSISTANT, content=result.answer)
        message.metadata = {
            "selected_agent": "KnowledgeAgent",
            "selected_flow": self.workflow_name,
            "selected_tool": "knowledge_search",
            "knowledge_documents": result.search_result.documents,
            "knowledge_chunks": result.search_result.chunks,
            "knowledge_citations": result.search_result.to_dict().get("citations", []),
            "answer_source": result.search_result.documents,
            "trace": result.trace_metadata,
        }
        return message, [result.tool_call]

    def architecture_summary(self) -> dict[str, Any]:
        return {
            "stage": "Phase 8 Stage 3",
            "architecture": "Independent Knowledge Agent",
            "agent": "KnowledgeAgent",
            "workflow": self.workflow_name,
            "tool": "knowledge_search",
            "retrieval_stack": ["Existing RetrievalService", "Existing VectorStore", "Existing RAG Pipeline"],
            "guardrails": [
                "Knowledge Agent does not access business databases",
                "All knowledge retrieval goes through knowledge_search tool",
                "Answers are constrained to retrieved knowledge context",
                "Source citations are returned for frontend trace display",
            ],
            "categories": ["policy", "product", "faq", "sop", "logistics", "refund", "complaint", "membership", "other"],
        }


knowledge_agent = KnowledgeAgent()
knowledge_workflow = KnowledgeWorkflow(knowledge_agent)
