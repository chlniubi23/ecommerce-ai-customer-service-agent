"""Customer service ticket tool backed by ComplaintRepository."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, ComplaintRepository
from app.services.proactive import emit_proactive_event
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class TicketTool(BaseTool):
    """Create a complaint-backed service ticket."""

    @property
    def name(self) -> str:
        return "create_ticket"

    @property
    def description(self) -> str:
        return "Create a customer service ticket backed by the complaints table."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "description": {
                "type": "string",
                "description": "Issue description.",
                "required": True,
            },
            "category": {
                "type": "string",
                "description": "Ticket category.",
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
        description = kwargs.get("description", "").strip()
        category = kwargs.get("category", "general")

        if not description:
            return ToolResult(success=False, error="Missing issue description", tool_name=self.name)

        try:
            ticket = ComplaintRepository().create_complaint(
                content=description,
                complaint_type=category,
                order_id=kwargs.get("order_id"),
                user_id=kwargs.get("user_id"),
            )
        except (DatabaseAccessError, ValueError, RuntimeError) as exc:
            return ToolResult(success=False, error=str(exc), tool_name=self.name)

        data = {
            "ticket_id": ticket["ticket_id"],
            "complaint_id": ticket["complaint_id"],
            "status": ticket["complaint_status"],
            "category": ticket["complaint_type"],
            "created_at": ticket["created_at"],
            "complaint": ticket,
        }
        try:
            AgentAuditRepository().record(
                agent_name=kwargs.get("agent_name", "TicketAgent"),
                tool_name=self.name,
                user_request=description,
                execution_result=data,
                workflow_id=kwargs.get("workflow_id"),
                session_id=kwargs.get("session_id"),
                success=True,
            )
        except Exception as exc:
            logger.warning("[TicketTool] audit log failed: %s", exc)

        # 动作即事件：投诉工单创建后落一条主动事件，用户可在服务面板跟进处理进度。
        emit_proactive_event(
            user_id=ticket.get("user_id") or kwargs.get("user_id"),
            event_type="complaint_followup_detected",
            severity="high",
            title="投诉工单已创建",
            description=f"工单 {ticket['ticket_id']} 已受理（{ticket['complaint_status']}），我会帮你跟进处理进度。",
            action_prompt=f"帮我跟进投诉工单 {ticket['complaint_id']}，说明当前进度和是否需要升级",
            dedup_key=f"complaint-open-{ticket['complaint_id']}",
            order_id=kwargs.get("order_id"),
            related_id=ticket["complaint_id"],
        )

        return ToolResult(success=True, data=data, tool_name=self.name)
