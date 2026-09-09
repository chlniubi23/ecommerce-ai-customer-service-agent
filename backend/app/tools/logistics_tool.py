"""Logistics query tool backed by the business database."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, LogisticsRepository
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _record_audit(tool_name: str, kwargs: dict[str, Any], result: dict[str, Any], success: bool) -> None:
    try:
        AgentAuditRepository().record(
            agent_name=kwargs.get("agent_name", "LogisticsAgent"),
            tool_name=tool_name,
            user_request=str(kwargs.get("order_id", "")),
            execution_result=result,
            workflow_id=kwargs.get("workflow_id"),
            session_id=kwargs.get("session_id"),
            success=success,
        )
    except Exception as exc:
        logger.warning("[LogisticsTool] audit log failed: %s", exc)


class LogisticsTool(BaseTool):
    """Query real logistics data by order id."""

    @property
    def name(self) -> str:
        return "logistics_query"

    @property
    def description(self) -> str:
        return "Query shipment status, carrier, tracking number and tracking timeline for an order."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "order_id": {
                "type": "string",
                "description": "Order id.",
                "required": True,
            }
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        order_id = kwargs.get("order_id", "").strip()
        logger.info("[LogisticsTool] query order_id=%s", order_id)

        if not order_id:
            return ToolResult(success=False, error="Missing order id", tool_name=self.name)

        try:
            shipment = LogisticsRepository().get_by_order_id(order_id)
        except DatabaseAccessError as exc:
            error = str(exc)
            _record_audit(self.name, kwargs, {"error": error}, False)
            return ToolResult(success=False, error=error, tool_name=self.name)

        if not shipment:
            data = {"order_id": order_id, "message": "No logistics record found in database"}
            _record_audit(self.name, kwargs, data, False)
            return ToolResult(success=False, data=data, error=data["message"], tool_name=self.name)

        _record_audit(self.name, kwargs, shipment, True)
        return ToolResult(success=True, data=shipment, tool_name=self.name)
