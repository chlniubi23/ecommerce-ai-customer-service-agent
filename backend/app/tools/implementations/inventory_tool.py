"""Inventory query tool backed by ProductRepository."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, ProductRepository
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class InventoryTool(BaseTool):
    """Query real inventory data by product name or SKU."""

    @property
    def name(self) -> str:
        return "query_inventory"

    @property
    def description(self) -> str:
        return "Query product inventory, including quantity, available inventory, reserved inventory and stock status."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "product_name": {
                "type": "string",
                "description": "Product name, SKU or keyword.",
                "required": True,
            }
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        product_name = kwargs.get("product_name", "").strip()
        logger.info("[InventoryTool] query product_name=%s", product_name)

        if not product_name:
            return ToolResult(success=False, error="Missing product name", tool_name=self.name)

        try:
            product = ProductRepository().get_inventory(product_name)
        except DatabaseAccessError as exc:
            return ToolResult(success=False, error=str(exc), tool_name=self.name)

        if not product:
            return ToolResult(
                success=False,
                error=f"No inventory data found for '{product_name}'",
                tool_name=self.name,
            )

        data = {
            "product_id": product["product_id"],
            "sku_id": product["sku_id"],
            "product_name": product["product_name"],
            "brand_name": product.get("brand_name"),
            "category_name": product.get("category_name"),
            "quantity": product.get("quantity", 0),
            "available_quantity": product.get("available_quantity", 0),
            "reserved_quantity": product.get("reserved_quantity", 0),
            "safety_stock": product.get("safety_stock", 0),
            "inventory_status": product.get("inventory_status"),
            "in_stock": (product.get("available_quantity") or 0) > 0,
        }
        try:
            AgentAuditRepository().record(
                agent_name=kwargs.get("agent_name", "InventoryAgent"),
                tool_name=self.name,
                user_request=product_name,
                execution_result=data,
                workflow_id=kwargs.get("workflow_id"),
                session_id=kwargs.get("session_id"),
                success=True,
            )
        except Exception as exc:
            logger.warning("[InventoryTool] audit log failed: %s", exc)

        return ToolResult(success=True, data=data, tool_name=self.name)
