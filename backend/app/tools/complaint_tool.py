"""Complaint creation tool backed by ComplaintRepository."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, ComplaintRepository
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ComplaintCreateTool(BaseTool):
    """Create a real complaint record for ComplaintAgent workflows."""

    @property
    def name(self) -> str:
        return "complaint_create"

    @property
    def description(self) -> str:
        return "Create a complaint using the database-backed complaint repository."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "content": {
                "type": "string",
                "description": "Complaint content.",
                "required": True,
            },
            "complaint_type": {
                "type": "string",
                "description": "Complaint type.",
                "required": False,
            },
            "order_id": {
                "type": "string",
                "description": "Related order id.",
                "required": False,
            },
            "user_id": {
                "type": "string",
                "description": "Related user id.",
                "required": False,
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        content = kwargs.get("content", "").strip()
        complaint_type = kwargs.get("complaint_type", "general")

        if not content:
            return ToolResult(success=False, error="Missing complaint content", tool_name=self.name)

        try:
            complaint = ComplaintRepository().create_complaint(
                content=content,
                complaint_type=complaint_type,
                order_id=kwargs.get("order_id"),
                user_id=kwargs.get("user_id"),
            )
        except (DatabaseAccessError, ValueError, RuntimeError) as exc:
            return ToolResult(success=False, error=str(exc), tool_name=self.name)

        try:
            AgentAuditRepository().record(
                agent_name=kwargs.get("agent_name", "ComplaintAgent"),
                tool_name=self.name,
                user_request=content,
                execution_result=complaint,
                workflow_id=kwargs.get("workflow_id"),
                session_id=kwargs.get("session_id"),
                success=True,
            )
        except Exception as exc:
            logger.warning("[ComplaintCreateTool] audit log failed: %s", exc)

        return ToolResult(success=True, data=complaint, tool_name=self.name)
