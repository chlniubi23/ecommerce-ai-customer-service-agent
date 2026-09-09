"""Product query tool backed by the business database."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, ProductRepository
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _record_audit(tool_name: str, kwargs: dict[str, Any], result: dict[str, Any], success: bool) -> None:
    try:
        AgentAuditRepository().record(
            agent_name=kwargs.get("agent_name", "ProductAgent"),
            tool_name=tool_name,
            user_request=str(kwargs.get("keyword", "")),
            execution_result=result,
            workflow_id=kwargs.get("workflow_id"),
            session_id=kwargs.get("session_id"),
            success=success,
        )
    except Exception as exc:
        logger.warning("[ProductTool] audit log failed: %s", exc)


class ProductTool(BaseTool):
    """Query products from the Product Repository."""

    @property
    def name(self) -> str:
        return "product_query"

    @property
    def description(self) -> str:
        return "Query product catalog data by keyword, including brand, category, price, inventory and images."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "keyword": {
                "type": "string",
                "description": "Product name, SKU, brand, category or keyword.",
                "required": True,
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        keyword = kwargs.get("keyword", "").strip()
        logger.info("[ProductTool] query keyword=%s", keyword)

        if not keyword:
            return ToolResult(success=False, error="Missing product keyword", tool_name=self.name)

        try:
            products = ProductRepository().search_products(keyword)
        except DatabaseAccessError as exc:
            error = str(exc)
            _record_audit(self.name, kwargs, {"error": error}, False)
            return ToolResult(success=False, error=error, tool_name=self.name)

        if not products:
            data = {"keyword": keyword, "products": [], "message": "No matching product found in database"}
            _record_audit(self.name, kwargs, data, False)
            return ToolResult(success=False, data=data, error=data["message"], tool_name=self.name)

        data = {
            "keyword": keyword,
            "count": len(products),
            "products": products,
            "primary_product": products[0],
        }
        _record_audit(self.name, kwargs, data, True)
        return ToolResult(success=True, data=data, tool_name=self.name)
