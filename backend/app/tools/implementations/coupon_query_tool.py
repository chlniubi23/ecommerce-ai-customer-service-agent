"""Coupon query tool backed by CouponRepository (demo data source)."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, CouponRepository
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class CouponQueryTool(BaseTool):
    @property
    def name(self) -> str:
        return "query_coupons"

    @property
    def description(self) -> str:
        return "Query the current user's usable coupons (name, type, threshold, discount, status, validity)."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "user_id": {"type": "string", "description": "Current user id.", "required": True},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = str(kwargs.get("user_id", "")).strip()
        if not user_id:
            return ToolResult(success=False, error="Missing user id", tool_name=self.name)
        try:
            coupons = CouponRepository().list_by_user(user_id)
        except DatabaseAccessError as exc:
            return ToolResult(success=False, error=str(exc), tool_name=self.name)
        usable = [c for c in coupons if c.get("coupon_status") == "可用"]
        data = {
            "user_id": user_id,
            "usable_count": len(usable),
            "total_count": len(coupons),
            "coupons": coupons,
        }
        try:
            AgentAuditRepository().record(
                agent_name=kwargs.get("agent_name", "CouponAgent"),
                tool_name=self.name,
                user_request=f"query coupons for {user_id}",
                execution_result=data,
                workflow_id=kwargs.get("workflow_id"),
                session_id=kwargs.get("session_id"),
                success=True,
            )
        except Exception as exc:
            logger.warning("[CouponQueryTool] audit log failed: %s", exc)
        return ToolResult(success=True, data=data, tool_name=self.name)
