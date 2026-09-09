"""Order query tool backed by OrderRepository."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, OrderRepository
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class OrderQueryTool(BaseTool):
    """Query real order data by order id."""

    @property
    def name(self) -> str:
        return "query_order"

    @property
    def description(self) -> str:
        return "Query order details, user, status, payment, shipping, address and order items."

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
        logger.info("[OrderQueryTool] query order_id=%s", order_id)

        if not order_id:
            return ToolResult(success=False, error="Missing order id", tool_name=self.name)

        try:
            data = OrderRepository().get_order(order_id)
        except DatabaseAccessError as exc:
            return ToolResult(success=False, error=str(exc), tool_name=self.name)

        if not data:
            return ToolResult(
                success=False,
                error=f"Order {order_id} was not found in database",
                tool_name=self.name,
            )

        try:
            AgentAuditRepository().record(
                agent_name=kwargs.get("agent_name", "OrderAgent"),
                tool_name=self.name,
                user_request=order_id,
                execution_result=data,
                workflow_id=kwargs.get("workflow_id"),
                session_id=kwargs.get("session_id"),
                success=True,
            )
        except Exception as exc:
            logger.warning("[OrderQueryTool] audit log failed: %s", exc)

        return ToolResult(success=True, data=data, tool_name=self.name)
