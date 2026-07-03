"""Personalized product recommendation tool backed by real purchase history."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, ProductRecommendationRepository
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class RecommendTool(BaseTool):
    """Recommend products for a user based on their real purchase history."""

    @property
    def name(self) -> str:
        return "recommend_products"

    @property
    def description(self) -> str:
        return "Recommend in-stock products personalized to the user's purchase history (preferred categories/brands), excluding already-purchased items."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "user_id": {"type": "string", "description": "Current user id.", "required": True},
            "limit": {"type": "integer", "description": "Max recommendations.", "required": False},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = str(kwargs.get("user_id", "")).strip()
        if not user_id:
            return ToolResult(success=False, error="Missing user id", tool_name=self.name)
        limit = kwargs.get("limit") or 5
        try:
            data = ProductRecommendationRepository().recommend_for_user(user_id, limit=int(limit))
        except DatabaseAccessError as exc:
            return ToolResult(success=False, error=str(exc), tool_name=self.name)

        try:
            AgentAuditRepository().record(
                agent_name=kwargs.get("agent_name", "ProductAgent"),
                tool_name=self.name,
                user_request=f"recommend products for {user_id}",
                execution_result=data,
                workflow_id=kwargs.get("workflow_id"),
                session_id=kwargs.get("session_id"),
                success=True,
            )
        except Exception as exc:
            logger.warning("[RecommendTool] audit log failed: %s", exc)
        return ToolResult(success=True, data=data, tool_name=self.name)
