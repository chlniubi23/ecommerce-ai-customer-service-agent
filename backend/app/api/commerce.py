"""Commerce demo APIs backed by the real MySQL business database."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.database.connection import DatabaseAccessError
from app.database.repositories import (
    AgentAuditRepository,
    ComplaintRepository,
    LogisticsRepository,
    OrderRepository,
    ProactiveEventRepository,
    ProductRepository,
    RefundRepository,
    UserRepository,
    WorkflowRuntimeRepository,
)
from app.models.base_response import error_response, success_response


router = APIRouter(prefix="/commerce", tags=["commerce"])


class LoginRequest(BaseModel):
    login: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2)
    email: str = Field(..., min_length=3)
    phone: str = Field(..., min_length=5)
    password: str = Field(..., min_length=3)
    full_name: str = Field(..., min_length=1)


class AddressRequest(BaseModel):
    receiver_name: str
    phone: str
    province: str
    city: str
    district: str
    address_line: str
    postal_code: str = ""
    is_default: bool = False


class CreateOrderRequest(BaseModel):
    user_id: str
    product_id: str
    quantity: int = Field(default=1, ge=1, le=20)


class RefundRequest(BaseModel):
    order_id: str
    reason: str = "用户申请退款"


class ComplaintRequest(BaseModel):
    user_id: str | None = None
    order_id: str | None = None
    complaint_type: str = "general"
    content: str


class TaskActionRequest(BaseModel):
    user_id: str
    task_id: str
    action: str = Field(..., min_length=1)


SEVERITY_RANK = {
    "urgent": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def _password_hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_password(stored_hash: str, password: str) -> bool:
    return (
        stored_hash == _password_hash(password)
        or stored_hash == password
        or (stored_hash.startswith("demo_hash_") and password == "demo123")
    )


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    user = dict(user)
    user.pop("password_hash", None)
    return user


def _contains_any(value: str, keywords: tuple[str, ...]) -> bool:
    text = value.lower()
    return any(keyword.lower() in text for keyword in keywords)


def _first_order_item_name(order: dict[str, Any]) -> str:
    items = order.get("items") or []
    if not items:
        return "相关商品"
    return str(items[0].get("product_name") or "相关商品")


def _make_insight(
    insight_id: str,
    insight_type: str,
    severity: str,
    title: str,
    description: str,
    action_label: str,
    action_prompt: str,
    order_id: str | None = None,
    related_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "insight_id": insight_id,
        "type": insight_type,
        "severity": severity,
        "title": title,
        "description": description,
        "action_label": action_label,
        "action_prompt": action_prompt,
        "order_id": order_id,
        "related_id": related_id,
        "created_at": created_at,
    }


def _build_agent_insights(
    user_id: str,
    orders: list[dict[str, Any]],
    refunds: list[dict[str, Any]],
    complaints: list[dict[str, Any]],
) -> dict[str, Any]:
    insights: list[dict[str, Any]] = []

    for order in orders[:12]:
        order_id = str(order.get("order_id") or "")
        status_text = " ".join(
            str(order.get(field) or "")
            for field in ("order_status", "payment_status", "shipping_status", "receipt_status", "logistics_status")
        )
        product_name = _first_order_item_name(order)

        if _contains_any(status_text, ("exception", "异常", "problem", "failed")):
            insights.append(
                _make_insight(
                    insight_id=f"logistics-exception-{order_id}",
                    insight_type="logistics_exception",
                    severity="urgent",
                    title="物流可能异常",
                    description=f"{product_name} 的配送状态需要优先核对。",
                    action_label="查看物流",
                    action_prompt=f"帮我核查订单 {order_id} 的物流异常，并告诉我下一步怎么处理",
                    order_id=order_id,
                    created_at=order.get("created_at"),
                )
            )
            continue

        if _contains_any(status_text, ("shipped", "in_transit", "out_for_delivery", "待收货", "运输", "派送", "已发货")):
            insights.append(
                _make_insight(
                    insight_id=f"logistics-follow-{order_id}",
                    insight_type="logistics_follow",
                    severity="medium",
                    title="订单正在配送",
                    description=f"{product_name} 仍在配送链路中，可直接追踪当前位置。",
                    action_label="追踪订单",
                    action_prompt=f"帮我追踪订单 {order_id} 的当前位置和预计送达时间",
                    order_id=order_id,
                    created_at=order.get("created_at"),
                )
            )

        if _contains_any(status_text, ("unpaid", "待支付", "未支付", "created")):
            insights.append(
                _make_insight(
                    insight_id=f"order-unpaid-{order_id}",
                    insight_type="order_attention",
                    severity="low",
                    title="订单待确认",
                    description=f"{product_name} 的订单状态还未完全闭环。",
                    action_label="查看订单",
                    action_prompt=f"帮我检查订单 {order_id} 当前卡在哪一步，还需要我做什么",
                    order_id=order_id,
                    created_at=order.get("created_at"),
                )
            )

    for refund in refunds[:8]:
        refund_id = str(refund.get("refund_id") or "")
        order_id = str(refund.get("order_id") or "")
        status_text = f"{refund.get('audit_status') or ''} {refund.get('refund_status') or ''}"
        if _contains_any(status_text, ("pending", "review", "processing", "待", "审核", "处理中")):
            insights.append(
                _make_insight(
                    insight_id=f"refund-pending-{refund_id}",
                    insight_type="refund_progress",
                    severity="high",
                    title="退款进度待跟进",
                    description=f"订单 {order_id} 的退款仍在 {refund.get('refund_status') or refund.get('audit_status')}。",
                    action_label="跟进退款",
                    action_prompt=f"帮我跟进订单 {order_id} 的退款进度，说明当前状态和下一步",
                    order_id=order_id,
                    related_id=refund_id,
                    created_at=refund.get("created_at"),
                )
            )
        elif _contains_any(status_text, ("rejected", "拒绝", "驳回")):
            insights.append(
                _make_insight(
                    insight_id=f"refund-rejected-{refund_id}",
                    insight_type="refund_rejected",
                    severity="urgent",
                    title="退款结果需确认",
                    description=f"订单 {order_id} 的退款申请未通过，需要确认原因。",
                    action_label="查看原因",
                    action_prompt=f"帮我查看订单 {order_id} 退款未通过的原因，并给出可申诉或补充材料建议",
                    order_id=order_id,
                    related_id=refund_id,
                    created_at=refund.get("created_at"),
                )
            )

    for complaint in complaints[:8]:
        complaint_id = str(complaint.get("complaint_id") or "")
        order_id = complaint.get("order_id")
        status_text = f"{complaint.get('complaint_status') or ''} {complaint.get('priority') or ''}"
        severity = "urgent" if _contains_any(status_text, ("urgent", "high", "escalated", "紧急", "高", "升级")) else "high"
        if not _contains_any(status_text, ("closed", "resolved", "已关闭", "已解决")):
            insights.append(
                _make_insight(
                    insight_id=f"complaint-open-{complaint_id}",
                    insight_type="complaint_follow",
                    severity=severity,
                    title="投诉工单待处理",
                    description=f"工单 {complaint.get('ticket_id') or complaint_id} 当前为 {complaint.get('complaint_status')}。",
                    action_label="跟进工单",
                    action_prompt=f"帮我跟进投诉工单 {complaint_id}，说明当前处理进度和是否需要升级",
                    order_id=order_id,
                    related_id=complaint_id,
                    created_at=complaint.get("created_at"),
                )
            )

    if not insights and orders:
        latest_order = orders[0]
        order_id = str(latest_order.get("order_id") or "")
        insights.append(
            _make_insight(
                insight_id=f"order-summary-{order_id}",
                insight_type="service_summary",
                severity="low",
                title="近期订单可复盘",
                description="当前没有高风险售后事项，可以快速汇总近期订单和权益。",
                action_label="生成总结",
                action_prompt="帮我总结最近订单、物流、退款、投诉和可用权益",
                order_id=order_id,
                created_at=latest_order.get("created_at"),
            )
        )

    if not insights:
        insights.append(
            _make_insight(
                insight_id=f"guest-guide-{user_id}",
                insight_type="shopping_guide",
                severity="low",
                title="可以开始购物助手服务",
                description="登录后可自动汇总订单、物流、售后和投诉待办。",
                action_label="了解能力",
                action_prompt="你可以作为 AI 电商助手帮我做哪些事？",
            )
        )

    insights = sorted(
        insights,
        key=lambda item: (SEVERITY_RANK.get(item["severity"], 0), str(item.get("created_at") or "")),
        reverse=True,
    )[:8]

    counts = {
        "orders": len(orders),
        "active_orders": sum(
            1
            for order in orders
            if not _contains_any(
                " ".join(str(order.get(field) or "") for field in ("order_status", "shipping_status", "receipt_status")),
                ("completed", "delivered", "已完成", "已签收", "已收货"),
            )
        ),
        "refunds": len(refunds),
        "open_refunds": sum(
            1
            for refund in refunds
            if _contains_any(f"{refund.get('audit_status') or ''} {refund.get('refund_status') or ''}", ("pending", "review", "processing", "待", "审核", "处理中"))
        ),
        "complaints": len(complaints),
        "open_complaints": sum(
            1
            for complaint in complaints
            if not _contains_any(str(complaint.get("complaint_status") or ""), ("closed", "resolved", "已关闭", "已解决"))
        ),
    }

    urgent_count = sum(1 for item in insights if item["severity"] in {"urgent", "high"})
    summary = (
        f"发现 {urgent_count} 个需要优先关注的服务事项"
        if urgent_count
        else "当前没有高风险售后事项"
    )

    quick_actions = [
        {"label": "整理待办", "prompt": "帮我整理当前需要处理的订单、物流、退款和投诉事项"},
        {"label": "查物流", "prompt": "帮我查看最近一个未签收订单的物流进度"},
        {"label": "售后进度", "prompt": "帮我查看有没有需要我处理的退款或售后进度"},
        {"label": "找人工", "prompt": "帮我查询人工客服排队情况并说明是否需要转人工"},
    ]

    return {
        "user_id": user_id,
        "summary": summary,
        "counts": counts,
        "insights": insights,
        "quick_actions": quick_actions,
        "pain_point_coverage": [
            "减少重复描述：自动携带用户、订单、物流、售后上下文",
            "主动提醒：识别异常物流、待处理退款、未关闭投诉",
            "流程指引：每条洞察都带下一步行动",
            "跨系统协同：订单、物流、退款、投诉和人工客服统一汇总",
        ],
    }


def _event_from_insight(insight: dict[str, Any]) -> dict[str, Any]:
    event_type_map = {
        "logistics_exception": "logistics_exception_detected",
        "refund_progress": "refund_pending_detected",
        "refund_rejected": "refund_rejected_detected",
        "complaint_follow": "complaint_followup_detected",
        "order_attention": "order_attention_detected",
        "logistics_follow": "delivery_followup_detected",
    }
    return {
        "event_id": f"evt-{insight['insight_id']}",
        "event_type": event_type_map.get(insight["type"], "assistant_insight_detected"),
        "severity": insight["severity"],
        "title": insight["title"],
        "description": insight["description"],
        "order_id": insight.get("order_id"),
        "related_id": insight.get("related_id"),
        "created_at": insight.get("created_at"),
        "assistant_prompt": insight["action_prompt"],
        "requires_user_attention": insight["severity"] in {"urgent", "high"},
    }


def _task_steps_for_insight(insight: dict[str, Any]) -> list[dict[str, Any]]:
    insight_type = insight["type"]
    if insight_type in {"logistics_exception", "logistics_follow"}:
        return [
            {
                "step_id": "check_logistics",
                "title": "核查物流记录",
                "description": "读取订单物流状态、当前位置、轨迹和预计送达时间。",
                "status": "ready",
                "action": "ask_agent",
                "action_label": "核查物流",
                "prompt": insight["action_prompt"],
            },
            {
                "step_id": "decide_next_action",
                "title": "判断下一步",
                "description": "根据物流状态判断继续等待、催促配送、申请售后或转人工。",
                "status": "pending",
                "action": "ask_agent",
                "action_label": "给出方案",
                "prompt": f"{insight['action_prompt']}，并把下一步方案按优先级列出来",
            },
            {
                "step_id": "human_if_needed",
                "title": "必要时转人工",
                "description": "如果存在异常或长时间未更新，查询人工客服排队并准备转接。",
                "status": "pending",
                "action": "ask_agent",
                "action_label": "转人工评估",
                "prompt": f"订单 {insight.get('order_id') or ''} 是否需要转人工处理？请查询人工客服状态并说明原因",
            },
        ]
    if insight_type in {"refund_progress", "refund_rejected"}:
        return [
            {
                "step_id": "check_refund",
                "title": "核查退款状态",
                "description": "读取退款审核状态、处理状态、金额和关联订单。",
                "status": "ready",
                "action": "ask_agent",
                "action_label": "查看退款",
                "prompt": insight["action_prompt"],
            },
            {
                "step_id": "prepare_materials",
                "title": "准备补充材料",
                "description": "如果退款被拒或卡住，整理用户需要补充的凭证和说明。",
                "status": "pending",
                "action": "ask_agent",
                "action_label": "整理材料",
                "prompt": f"针对订单 {insight.get('order_id') or ''} 的退款问题，帮我整理需要补充的材料和申诉话术",
            },
            {
                "step_id": "escalate_if_needed",
                "title": "升级处理",
                "description": "仍无法解决时，创建投诉或转人工，减少用户反复沟通。",
                "status": "pending",
                "action": "ask_agent",
                "action_label": "升级售后",
                "prompt": f"如果订单 {insight.get('order_id') or ''} 退款继续卡住，帮我判断应该投诉、转人工还是继续等待",
            },
        ]
    if insight_type == "complaint_follow":
        return [
            {
                "step_id": "check_ticket",
                "title": "核查工单进度",
                "description": "读取投诉状态、优先级、处理记录和升级记录。",
                "status": "ready",
                "action": "ask_agent",
                "action_label": "查看工单",
                "prompt": insight["action_prompt"],
            },
            {
                "step_id": "escalation_decision",
                "title": "判断是否升级",
                "description": "根据投诉优先级和处理时间判断是否需要 SupervisorAgent 介入。",
                "status": "pending",
                "action": "ask_agent",
                "action_label": "升级判断",
                "prompt": f"帮我判断投诉 {insight.get('related_id') or ''} 是否需要升级主管，并说明理由",
            },
            {
                "step_id": "human_transfer",
                "title": "人工协同",
                "description": "需要真人处理时，查询人工客服队列并准备沟通摘要。",
                "status": "pending",
                "action": "ask_agent",
                "action_label": "准备转接",
                "prompt": f"帮我把投诉 {insight.get('related_id') or ''} 整理成人工客服接手摘要，并查询排队情况",
            },
        ]
    return [
        {
            "step_id": "summarize_context",
            "title": "汇总上下文",
            "description": "整理订单、物流、退款、投诉和权益信息。",
            "status": "ready",
            "action": "ask_agent",
            "action_label": "生成总结",
            "prompt": insight["action_prompt"],
        },
        {
            "step_id": "recommend_next",
            "title": "推荐下一步",
            "description": "给出用户现在最值得做的动作。",
            "status": "pending",
            "action": "ask_agent",
            "action_label": "推荐动作",
            "prompt": "基于我的当前购物和售后上下文，推荐我下一步最应该处理什么",
        },
    ]


def _build_task_board(insights_payload: dict[str, Any]) -> dict[str, Any]:
    tasks = []
    for insight in insights_payload.get("insights", []):
        task_id = f"task-{insight['insight_id']}"
        steps = _task_steps_for_insight(insight)
        tasks.append(
            {
                "task_id": task_id,
                "source_insight_id": insight["insight_id"],
                "type": insight["type"],
                "severity": insight["severity"],
                "title": insight["title"],
                "description": insight["description"],
                "order_id": insight.get("order_id"),
                "related_id": insight.get("related_id"),
                "status": "active" if insight["severity"] in {"urgent", "high", "medium"} else "suggested",
                "progress": 0,
                "steps": steps,
                "next_prompt": steps[0]["prompt"] if steps else insight["action_prompt"],
            }
        )
    return {
        "user_id": insights_payload["user_id"],
        "summary": insights_payload["summary"],
        "tasks": tasks,
        "completion_policy": "每个任务先核查真实业务记录，再给下一步动作；用户确认后继续推进，必要时转人工或升级投诉。",
    }


@router.get("/dashboard")
async def dashboard():
    try:
        repo = ProductRepository()
        data = {
            "products": repo.fetch_one("SELECT COUNT(*) AS count FROM products"),
            "orders": repo.fetch_one("SELECT COUNT(*) AS count FROM orders"),
            "refunds": repo.fetch_one("SELECT COUNT(*) AS count FROM refunds"),
            "complaints": repo.fetch_one("SELECT COUNT(*) AS count FROM complaints"),
            "recent_audits": AgentAuditRepository().list_recent(8),
            "recent_workflows": WorkflowRuntimeRepository().list_recent(8),
        }
        return success_response(data=data)
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "Business database is unavailable", str(exc))


@router.post("/auth/login")
async def login(request: LoginRequest):
    try:
        user = UserRepository().find_by_login(request.login)
        if not user or not _verify_password(user["password_hash"], request.password):
            return error_response("AUTH_FAILED", "用户名或密码不正确")
        return success_response(
            data={
                "token": user["user_id"],
                "user": _public_user(UserRepository().get_by_id(user["user_id"]) or user),
            }
        )
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.post("/auth/register")
async def register(request: RegisterRequest):
    try:
        user = UserRepository().create_user(
            username=request.username,
            email=request.email,
            phone=request.phone,
            password_hash=_password_hash(request.password),
            full_name=request.full_name,
        )
        return success_response(data={"token": user["user_id"], "user": user})
    except Exception as exc:
        return error_response("REGISTER_FAILED", "注册失败", str(exc))


@router.get("/users/{user_id}")
async def get_user(user_id: str):
    try:
        user = UserRepository().get_by_id(user_id)
        if not user:
            return error_response("USER_NOT_FOUND", "用户不存在")
        return success_response(data=user)
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.post("/users/{user_id}/addresses")
async def add_address(user_id: str, request: AddressRequest):
    try:
        address = UserRepository().add_address(user_id=user_id, **request.model_dump())
        return success_response(data=address)
    except Exception as exc:
        return error_response("ADDRESS_FAILED", "地址保存失败", str(exc))


@router.get("/categories")
async def categories():
    try:
        return success_response(data=ProductRepository().list_categories())
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.get("/products")
async def products(keyword: str = "", category_id: str | None = None, limit: int = 50):
    try:
        return success_response(
            data=ProductRepository().list_products(keyword=keyword, category_id=category_id, limit=limit)
        )
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.get("/products/{product_id}")
async def product_detail(product_id: str):
    try:
        product = ProductRepository().get_product(product_id)
        if not product:
            return error_response("PRODUCT_NOT_FOUND", "商品不存在")
        return success_response(data=product)
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.post("/orders")
async def create_order(request: CreateOrderRequest):
    try:
        order = OrderRepository().create_order(
            user_id=request.user_id,
            product_id=request.product_id,
            quantity=request.quantity,
        )
        return success_response(data=order)
    except Exception as exc:
        return error_response("ORDER_CREATE_FAILED", "创建订单失败", str(exc))


@router.get("/users/{user_id}/orders")
async def user_orders(user_id: str):
    try:
        return success_response(data=OrderRepository().list_user_orders(user_id))
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.get("/orders/{order_id}")
async def order_detail(order_id: str):
    try:
        order = OrderRepository().get_order(order_id)
        if not order:
            return error_response("ORDER_NOT_FOUND", "订单不存在")
        order["logistics"] = LogisticsRepository().get_by_order_id(order_id)
        order["refund"] = RefundRepository().get_by_order_id(order_id)
        return success_response(data=order)
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.get("/orders/{order_id}/logistics")
async def order_logistics(order_id: str):
    try:
        logistics = LogisticsRepository().get_by_order_id(order_id)
        if not logistics:
            return error_response("LOGISTICS_NOT_FOUND", "物流记录不存在")
        return success_response(data=logistics)
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.get("/users/{user_id}/refunds")
async def refunds(user_id: str):
    try:
        return success_response(data=RefundRepository().list_by_user(user_id))
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.post("/refunds")
async def apply_refund(request: RefundRequest):
    try:
        repository = RefundRepository()
        refund = repository.get_by_order_id(request.order_id) or repository.create_refund(
            request.order_id,
            request.reason,
        )
        return success_response(data=refund)
    except Exception as exc:
        return error_response("REFUND_FAILED", "退款申请失败", str(exc))


@router.get("/users/{user_id}/complaints")
async def complaints(user_id: str):
    try:
        return success_response(data=ComplaintRepository().list_by_user(user_id))
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.post("/complaints")
async def create_complaint(request: ComplaintRequest):
    try:
        complaint = ComplaintRepository().create_complaint(
            content=request.content,
            complaint_type=request.complaint_type,
            order_id=request.order_id,
            user_id=request.user_id,
        )
        return success_response(data=complaint)
    except Exception as exc:
        return error_response("COMPLAINT_FAILED", "投诉提交失败", str(exc))


@router.get("/agent/context")
async def agent_context(
    user_id: str | None = None,
    order_id: str | None = None,
    product_id: str | None = None,
):
    try:
        data: dict[str, Any] = {}
        if user_id:
            data["user"] = UserRepository().get_by_id(user_id)
        if product_id:
            data["product"] = ProductRepository().get_product(product_id)
        if order_id:
            order = OrderRepository().get_order(order_id)
            data["order"] = order
            data["logistics"] = LogisticsRepository().get_by_order_id(order_id)
            data["refund"] = RefundRepository().get_by_order_id(order_id)
            if order:
                data["complaints"] = [
                    complaint
                    for complaint in ComplaintRepository().list_by_user(order["user_id"])
                    if complaint.get("order_id") == order_id
                ]
        return success_response(data=data)
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.get("/agent/insights")
async def agent_insights(user_id: str):
    try:
        user = UserRepository().get_by_id(user_id)
        if not user:
            return error_response("USER_NOT_FOUND", "用户不存在")
        orders = OrderRepository().list_user_orders(user_id)
        refunds = RefundRepository().list_by_user(user_id)
        complaints = ComplaintRepository().list_by_user(user_id)
        return success_response(data=_build_agent_insights(user_id, orders, refunds, complaints))
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


def _scan_and_emit_events(
    user_id: str,
    orders: list[dict[str, Any]],
    refunds: list[dict[str, Any]],
    complaints: list[dict[str, Any]],
    min_rank: int,
) -> None:
    """扫描当前业务状态，把达到阈值的洞察"落"成去重的持久化主动事件。

    这是"事件驱动"的扫描侧：同一情形（同 insight_id → dedup_key）只落一次，
    用户看过标记已读后不再刷屏。真正的状态变化（新退款/新投诉）会生成新的
    insight_id，从而作为新事件出现在未读列表里。
    """
    repo = ProactiveEventRepository()
    insights_payload = _build_agent_insights(user_id, orders, refunds, complaints)
    for insight in insights_payload["insights"]:
        if SEVERITY_RANK.get(insight["severity"], 0) < min_rank:
            continue
        event = _event_from_insight(insight)
        repo.emit(
            user_id=user_id,
            event_type=event["event_type"],
            severity=insight["severity"],
            title=insight["title"],
            description=insight["description"],
            action_prompt=insight["action_prompt"],
            dedup_key=insight["insight_id"],
            order_id=insight.get("order_id"),
            related_id=insight.get("related_id"),
        )


@router.get("/agent/events")
async def agent_events(user_id: str, min_severity: str = "medium"):
    try:
        user = UserRepository().get_by_id(user_id)
        if not user:
            return error_response("USER_NOT_FOUND", "用户不存在")
        orders = OrderRepository().list_user_orders(user_id)
        refunds = RefundRepository().list_by_user(user_id)
        complaints = ComplaintRepository().list_by_user(user_id)
        min_rank = SEVERITY_RANK.get(min_severity, 2)

        # 事件驱动：先扫描当前业务状态落成去重事件，再只返回"未读"事件。
        _scan_and_emit_events(user_id, orders, refunds, complaints, min_rank)
        unread = ProactiveEventRepository().list_for_user(user_id, statuses=("unread",))
        events = [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "severity": row["severity"],
                "title": row["title"],
                "description": row["description"],
                "assistant_prompt": row["action_prompt"],
                "order_id": row.get("order_id"),
                "related_id": row.get("related_id"),
                "created_at": row.get("created_at"),
                "requires_user_attention": row["severity"] in {"urgent", "high"},
            }
            for row in unread
        ]
        return success_response(
            data={
                "user_id": user_id,
                "events": events,
                "unread_count": len(events),
                "poll_after_seconds": 30,
                "source": "proactive_events",
            }
        )
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.post("/agent/events/{event_id}/read")
async def agent_event_mark_read(event_id: str):
    """标记主动事件已读：用户看过/处理后不再重复推送（配合去重防刷屏）。"""
    try:
        event = ProactiveEventRepository().get_by_id(event_id)
        if not event:
            return error_response("EVENT_NOT_FOUND", "事件不存在")
        ProactiveEventRepository().mark_read(event_id)
        return success_response(data={"event_id": event_id, "event_status": "read"})
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.get("/agent/tasks")
async def agent_tasks(user_id: str):
    try:
        user = UserRepository().get_by_id(user_id)
        if not user:
            return error_response("USER_NOT_FOUND", "用户不存在")
        orders = OrderRepository().list_user_orders(user_id)
        refunds = RefundRepository().list_by_user(user_id)
        complaints = ComplaintRepository().list_by_user(user_id)
        insights_payload = _build_agent_insights(user_id, orders, refunds, complaints)
        return success_response(data=_build_task_board(insights_payload))
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.post("/agent/tasks/action")
async def agent_task_action(request: TaskActionRequest):
    try:
        user = UserRepository().get_by_id(request.user_id)
        if not user:
            return error_response("USER_NOT_FOUND", "用户不存在")
        tasks_payload = _build_task_board(
            _build_agent_insights(
                request.user_id,
                OrderRepository().list_user_orders(request.user_id),
                RefundRepository().list_by_user(request.user_id),
                ComplaintRepository().list_by_user(request.user_id),
            )
        )
        task = next((item for item in tasks_payload["tasks"] if item["task_id"] == request.task_id), None)
        if not task:
            return error_response("TASK_NOT_FOUND", "任务不存在或已完成")
        task["last_action"] = request.action
        task["progress"] = 50 if request.action == "start" else 100 if request.action == "complete" else task["progress"]
        task["status"] = "completed" if request.action == "complete" else "active"
        return success_response(data=task)
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))


@router.get("/agent/trace")
async def agent_trace():
    try:
        return success_response(
            data={
                "audits": AgentAuditRepository().list_recent(20),
                "workflows": WorkflowRuntimeRepository().list_recent(20),
            }
        )
    except DatabaseAccessError as exc:
        return error_response("DATABASE_ERROR", "业务数据库暂不可用", str(exc))
