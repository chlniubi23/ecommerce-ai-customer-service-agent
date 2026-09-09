"""
Metrics API — 100% real-time aggregation from the live MySQL database.

Every number on the dashboard is computed from actual rows:
- Counts (orders/refunds/complaints/products/users) via COUNT.
- Flow distribution via agent_audit_logs GROUP BY agent_name.
- Tool success rate via agent_audit_logs success flag.
- Order/refund/complaint status breakdowns via GROUP BY on the real
  Chinese status columns.

No hardcoded sample numbers. The only non-DB field is the prompt-iteration
changelog, which documents real prompt-engineering commits (kept as a record,
clearly labelled as a changelog, not a live metric).
"""

from __future__ import annotations

from fastapi import APIRouter
from app.core.config import get_settings
from app.database.connection import mysql_connection, DatabaseAccessError
from app.models.base_response import success_response, error_response

router = APIRouter(prefix="/metrics", tags=["metrics"])

settings = get_settings()

# agent_name (from agent_audit_logs) -> user-facing flow label + accent color
AGENT_FLOW_MAP: dict[str, dict[str, str]] = {
    "OrderAgent":     {"flow": "OrderFlow",         "label": "订单查询",  "color": "#60a5fa"},
    "LogisticsAgent": {"flow": "LogisticsFlow",     "label": "物流追踪",  "color": "#a78bfa"},
    "RefundAgent":    {"flow": "RefundFlow",        "label": "退款售后",  "color": "#34d399"},
    "KnowledgeAgent": {"flow": "KnowledgeFlow",     "label": "知识问答",  "color": "#67e8f9"},
    "ProductAgent":   {"flow": "ProductFlow",       "label": "商品推荐",  "color": "#fbbf24"},
    "ComplaintAgent": {"flow": "TicketFlow",        "label": "投诉工单",  "color": "#fb7185"},
    "HumanAgent":     {"flow": "HumanTransferFlow", "label": "转人工",    "color": "#94a3b8"},
    "CouponAgent":    {"flow": "CouponFlow",        "label": "优惠券",    "color": "#f472b6"},
}
_DEFAULT_FLOW = {"flow": "GeneralFlow", "label": "其他", "color": "#cbd5e1"}


@router.get("", summary="Product analytics dashboard data")
def get_metrics():
    """Return fully DB-derived metrics for the dashboard."""
    try:
        with mysql_connection() as conn:
            cur = conn.cursor()

            # ── Live counts ──────────────────────────────────────────────────
            cur.execute("SELECT COUNT(*) AS cnt FROM orders")
            total_orders = (cur.fetchone() or {}).get("cnt", 0)

            cur.execute("SELECT COUNT(*) AS cnt FROM refunds")
            total_refunds = (cur.fetchone() or {}).get("cnt", 0)

            cur.execute("SELECT COUNT(*) AS cnt FROM complaints")
            total_complaints = (cur.fetchone() or {}).get("cnt", 0)

            cur.execute("SELECT COUNT(*) AS cnt FROM products")
            product_count = (cur.fetchone() or {}).get("cnt", 0)

            cur.execute("SELECT COUNT(*) AS cnt FROM users")
            total_users = (cur.fetchone() or {}).get("cnt", 0)

            # ── Order status breakdown (real Chinese statuses) ───────────────
            cur.execute(
                "SELECT order_status, COUNT(*) AS cnt FROM orders GROUP BY order_status"
            )
            order_status: dict[str, int] = {
                row["order_status"]: row["cnt"] for row in cur.fetchall()
            }

            # ── Refund audit status breakdown (real Chinese statuses) ─────────
            cur.execute(
                "SELECT audit_status, COUNT(*) AS cnt FROM refunds GROUP BY audit_status"
            )
            refund_rows = cur.fetchall()
            # Map real Chinese statuses to the three UI buckets
            approved_set = {"已通过", "通过", "审核通过"}
            rejected_set = {"已拒绝", "拒绝", "驳回", "审核不通过"}
            refund_approved = sum(r["cnt"] for r in refund_rows if r["audit_status"] in approved_set)
            refund_rejected = sum(r["cnt"] for r in refund_rows if r["audit_status"] in rejected_set)
            refund_pending  = sum(r["cnt"] for r in refund_rows
                                  if r["audit_status"] not in approved_set
                                  and r["audit_status"] not in rejected_set)
            # Full raw breakdown for display
            refund_status_raw: dict[str, int] = {
                row["audit_status"]: row["cnt"] for row in refund_rows
            }

            # ── Complaint priority breakdown (real) ──────────────────────────
            cur.execute(
                "SELECT priority, COUNT(*) AS cnt FROM complaints GROUP BY priority"
            )
            complaint_priority: dict[str, int] = {
                row["priority"]: row["cnt"] for row in cur.fetchall()
            }

            # ── Tool call stats from agent_audit_logs (real) ─────────────────
            cur.execute(
                """
                SELECT tool_name,
                       COUNT(*)                                     AS total,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS succeeded
                FROM agent_audit_logs
                GROUP BY tool_name
                ORDER BY total DESC
                """
            )
            tool_by_tool:    dict[str, int] = {}
            success_by_tool: dict[str, int] = {}
            for row in cur.fetchall():
                tool_by_tool[row["tool_name"]]    = int(row["total"])
                success_by_tool[row["tool_name"]] = int(row["succeeded"] or 0)

            total_calls   = sum(tool_by_tool.values())
            total_success = sum(success_by_tool.values())
            overall_rate  = round(total_success / total_calls * 100, 1) if total_calls > 0 else None

            # ── Flow distribution from agent_audit_logs GROUP BY agent (real) ─
            cur.execute(
                """
                SELECT agent_name, COUNT(*) AS cnt
                FROM agent_audit_logs
                GROUP BY agent_name
                ORDER BY cnt DESC
                """
            )
            flow_distribution: list[dict] = []
            for row in cur.fetchall():
                meta = AGENT_FLOW_MAP.get(row["agent_name"], _DEFAULT_FLOW)
                flow_distribution.append({
                    "flow":  meta["flow"],
                    "label": meta["label"],
                    "count": int(row["cnt"]),
                    "color": meta["color"],
                })

            # ── Distinct sessions handled (real) ─────────────────────────────
            cur.execute(
                "SELECT COUNT(DISTINCT session_id) AS cnt FROM agent_audit_logs WHERE session_id IS NOT NULL AND session_id <> ''"
            )
            distinct_sessions = (cur.fetchone() or {}).get("cnt", 0)

            # ── Total audit records ──────────────────────────────────────────
            cur.execute("SELECT COUNT(*) AS cnt FROM agent_audit_logs")
            total_audit = (cur.fetchone() or {}).get("cnt", 0)

        # Prompt-engineering changelog — documents real commits (not a live metric)
        prompt_iterations = [
            {
                "version": "v3", "date": "2024-12-20",
                "change": "为「退款 vs 政策咨询」添加 few-shot 示例，降低意图误判",
                "metric": "意图路由", "before": "易混淆", "after": "已区分", "improvement": "few-shot",
            },
            {
                "version": "v2", "date": "2024-12-10",
                "change": "response_style 增加「口语化 + 简洁」指令",
                "metric": "回复风格", "before": "机械", "after": "自然", "improvement": "prompt",
            },
            {
                "version": "v1", "date": "2024-11-28",
                "change": "初始版本：单轮问答，无 Slot Filling",
                "metric": "首次建立", "before": "—", "after": "—", "improvement": "—",
            },
        ]

        return success_response(data={
            "live": {
                "total_orders":       total_orders,
                "total_refunds":      total_refunds,
                "total_complaints":   total_complaints,
                "product_count":      product_count,
                "total_users":        total_users,
                "order_status":       order_status,
                "refund_breakdown":   {
                    "approved": refund_approved,
                    "pending":  refund_pending,
                    "rejected": refund_rejected,
                },
                "refund_status_raw":  refund_status_raw,
                "complaint_priority": complaint_priority,
            },
            "tool_calls": {
                "total":                total_calls,
                "total_audit_records":  total_audit,
                "distinct_sessions":    distinct_sessions,
                "overall_success_rate": overall_rate,
                "by_tool":              tool_by_tool,
                "success_by_tool":      success_by_tool,
            },
            # Real flow distribution (derived from agent_audit_logs)
            "flow_distribution": flow_distribution,
            "prompt_iterations": prompt_iterations,
        })

    except DatabaseAccessError as exc:
        return error_response(code="DB_ERROR", message="业务数据库暂不可用", detail=str(exc) if settings.app_debug else None)
    except Exception as exc:
        return error_response(code="METRICS_ERROR", message="指标聚合失败", detail=str(exc) if settings.app_debug else None)
