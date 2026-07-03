"""Human transfer tool backed by database queue status."""

import logging
from typing import Any

from app.database.connection import DatabaseAccessError
from app.database.repositories import AgentAuditRepository, HumanTransferRepository
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class HumanTransferTool(BaseTool):
    """Enqueue a real human-transfer request and return the queue position."""

    @property
    def name(self) -> str:
        return "transfer_human"

    @property
    def description(self) -> str:
        return "Transfer to human service by enqueuing a real request and return queue position and estimated wait time."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "reason": {
                "type": "string",
                "description": "Reason for human transfer.",
                "required": False,
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        reason = kwargs.get("reason", "Customer requested human service")
        team_name = kwargs.get("team_name", "general_service")
        logger.info("[HumanTransferTool] transfer reason=%s team=%s", reason, team_name)

        # 真正把用户加入人工队列：写一条转接请求并让队列人数 +1，
        # 而非只读取排队数后返回"成功"。这是 Agent（执行）与 Chatbot（告知）的区别。
        try:
            transfer = HumanTransferRepository().create_transfer_request(
                team_name=team_name,
                reason=reason,
                user_id=kwargs.get("user_id"),
                session_id=kwargs.get("session_id"),
            )
        except DatabaseAccessError as exc:
            return ToolResult(success=False, error=str(exc), tool_name=self.name)
        except (ValueError, RuntimeError) as exc:
            return ToolResult(success=False, error=str(exc), tool_name=self.name)

        result_data = {
            "transfer_success": True,
            "transfer_id": transfer["transfer_id"],
            "transfer_status": transfer["transfer_status"],
            "queue_position": transfer["queue_position"],
            "estimated_wait": f"{transfer['estimated_wait_minutes']} minutes",
            "online_agents": transfer["online_agents"],
            "working_hours": transfer["working_hours"],
            "team_name": team_name,
            "reason": reason,
        }
        try:
            AgentAuditRepository().record(
                agent_name=kwargs.get("agent_name", "HumanAgent"),
                tool_name=self.name,
                user_request=reason,
                execution_result=result_data,
                workflow_id=kwargs.get("workflow_id"),
                session_id=kwargs.get("session_id"),
                success=True,
            )
        except Exception as exc:
            logger.warning("[HumanTransferTool] audit log failed: %s", exc)

        return ToolResult(success=True, data=result_data, tool_name=self.name)
