"""Refund application tool backed by the business database."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, RefundRepository
from app.services.proactive import emit_proactive_event
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _record_audit(tool_name: str, kwargs: dict[str, Any], result: dict[str, Any], success: bool) -> None:
    try:
        AgentAuditRepository().record(
            agent_name=kwargs.get("agent_name", "RefundAgent"),
            tool_name=tool_name,
            user_request=f"{kwargs.get('order_id', '')} {kwargs.get('reason', '')}".strip(),
            execution_result=result,
            workflow_id=kwargs.get("workflow_id"),
            session_id=kwargs.get("session_id"),
            success=success,
        )
    except Exception as exc:
        logger.warning("[RefundTool] audit log failed: %s", exc)


class RefundTool(BaseTool):
    """Create or query refund requests through RefundRepository."""

    @property
    def name(self) -> str:
        return "refund_apply"

    @property
    def description(self) -> str:
        return "Create a refund request or return the existing refund state for an order."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "order_id": {
                "type": "string",
                "description": "Order id.",
                "required": True,
            },
            "reason": {
                "type": "string",
                "description": "Refund reason.",
                "required": False,
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        order_id = kwargs.get("order_id", "").strip()
        reason = kwargs.get("reason", "Customer requested refund")
        logger.info("[RefundTool] apply/query order_id=%s", order_id)

        if not order_id:
            return ToolResult(success=False, error="Missing order id", tool_name=self.name)

        repository = RefundRepository()
        try:
            data = repository.get_by_order_id(order_id)
            if not data:
                data = repository.create_refund(order_id, reason)
        except (DatabaseAccessError, ValueError, RuntimeError) as exc:
            error = str(exc)
            _record_audit(self.name, kwargs, {"error": error}, False)
            return ToolResult(success=False, error=error, tool_name=self.name)

        _record_audit(self.name, kwargs, data, True)

        # 动作即事件：退款进入审核后落一条主动事件，用户可在服务面板持续跟进进度。
        emit_proactive_event(
            user_id=data.get("user_id") or kwargs.get("user_id"),
            event_type="refund_pending_detected",
            severity="high",
            title="退款申请已提交",
            description=f"订单 {order_id} 的退款已进入 {data.get('refund_status') or '待处理'}，我会帮你盯着进度。",
            action_prompt=f"帮我跟进订单 {order_id} 的退款进度，有更新第一时间告诉我",
            dedup_key=f"refund-pending-{data.get('refund_id') or order_id}",
            order_id=order_id,
            related_id=data.get("refund_id"),
        )

        return ToolResult(success=True, data=data, tool_name=self.name)
