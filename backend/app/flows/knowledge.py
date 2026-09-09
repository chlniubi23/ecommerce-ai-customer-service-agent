"""Knowledge Flow for enterprise knowledge questions."""

import logging
import re

from app.flows.base import BaseFlow, FlowResult
from app.knowledge_agent import knowledge_workflow
from app.models.message import Message, MessageRole
from app.schemas.intent import IntentResult

logger = logging.getLogger(__name__)


class KnowledgeFlow(BaseFlow):
    """Route knowledge questions to the independent Knowledge Agent."""

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        query = _extract_user_request(intent_result.raw_input)
        logger.info("KnowledgeFlow handling: %s", query[:80])
        try:
            message, tool_calls = await knowledge_workflow.as_message(
                query,
                history=history,
                workflow_id=(slots or {}).get("workflow_id", "knowledge_workflow"),
                session_id=(slots or {}).get("session_id", ""),
            )
        except Exception as exc:
            logger.error("KnowledgeFlow failed: %s", exc, exc_info=True)
            return FlowResult(
                message=Message(
                    role=MessageRole.ASSISTANT,
                    content="抱歉，知识库检索暂时不可用，请稍后再试。",
                ),
                tool_calls=[{
                    "tool_name": "knowledge_search",
                    "tool_input": {"query": query},
                    "tool_output": {"error": str(exc)},
                    "success": False,
                    "latency_ms": 0.0,
                }],
            )
        return FlowResult(message=message, tool_calls=tool_calls)


def _extract_user_request(raw_input: str) -> str:
    """Extract the real user question when frontend prepends business context.

    The frontend wraps knowledge queries as:
        [用户请求]七天无理由退货的规则是什么？
        [系统补充上下文...] ...

    We want only the first line after the marker — not the system context.
    """
    for marker in ("[用户请求]", "[鐢ㄦ埛璇锋眰]"):
        if marker in raw_input:
            after_marker = raw_input.split(marker, 1)[1]
            # Take only the first non-empty line to exclude system context blocks
            first_line = after_marker.split("\n")[0].strip()
            if first_line:
                return first_line
    # Fallback: if no marker, return only the first line of the raw input
    # (user message is always first, system context follows after a blank line)
    first_line = raw_input.split("\n")[0].strip()
    return first_line if first_line else raw_input.strip()
