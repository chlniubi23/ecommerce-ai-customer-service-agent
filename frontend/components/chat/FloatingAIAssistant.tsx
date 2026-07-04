"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import DebugPanel from "@/components/debug/DebugPanel";
import { commerceApi, getStoredUserId, type AgentContext, type AssistantEvent, type AssistantInsight, type AssistantInsights, type Complaint, type DemoUser, type Order, type Refund } from "@/services/commerce";
import { sendChatMessage } from "@/services/chat";
import { createUserMessage, type Message } from "@/types/message";
import type { AgentTraceData } from "@/types/trace";

const SESSION_KEY = "commerce_floating_agent_session";
const OPEN_EVENT = "commerce:open-agent";

type AssistantContextRequest = {
  user_id?: string;
  product_id?: string;
  order_id?: string;
};

type ServiceSnapshot = {
  orders: Order[];
  refunds: Refund[];
  complaints: Complaint[];
};

type AgentCapability =
  | "logistics"
  | "order"
  | "refund"
  | "complaint"
  | "human"
  | "product"
  | "knowledge"
  | "summary";

// 面板激进合并：概览/任务与对话高度重复，合并为"对话"(主页，含待办条) + "Agent 面板"两页。
type AssistantView = "chat" | "trace";

const guestSuggestionBatches = [
  ["618 有哪些优惠活动？", "新用户首单有什么福利？", "退货退款规则是什么？", "商品发货一般多久？"],
  ["帮我推荐一款办公电脑", "怎么判断商品是否有库存？", "优惠券可以叠加使用吗？", "售后服务怎么联系？"],
  ["如何免费试用平台服务？", "会员权益有哪些？", "买贵了可以保价吗？", "配送范围支持哪些城市？"],
];

const signedInSuggestionBatches = [
  ["帮我看看最近的订单", "我的物流到哪里了？", "我要申请退款", "帮我创建投诉工单"],
  ["我最近有哪些售后进度？", "帮我查询可用优惠券", "推荐适合我复购的商品", "订单地址可以修改吗？"],
  ["帮我总结未完成事项", "有没有需要我处理的退款？", "查看我的会员权益", "帮我找人工客服"],
];

// 演示脚本：一键触发的场景，按"能力域"分组，覆盖 9 大能力。
// 面试/演示时照着点即可，每个 prompt 都能真实命中对应 Agent 并执行动作。
type DemoScenario = { icon: string; label: string; desc: string; prompt: string; requiresLogin?: boolean };

const DEMO_SCENARIOS: DemoScenario[] = [
  { icon: "📦", label: "查订单", desc: "看最近订单状态", prompt: "帮我看看我最近的订单现在什么状态", requiresLogin: true },
  { icon: "🚚", label: "追物流", desc: "快递到哪了", prompt: "我最近一个订单的快递到哪了？预计什么时候到", requiresLogin: true },
  { icon: "💰", label: "退款", desc: "直接发起退款", prompt: "我有个订单想申请退款，帮我处理一下", requiresLogin: true },
  { icon: "✨", label: "推荐", desc: "按我的历史推荐", prompt: "根据我买过的东西，帮我推荐几款值得入手的商品", requiresLogin: true },
  { icon: "🎫", label: "投诉", desc: "创建投诉工单", prompt: "我要投诉，商品有质量问题，帮我登记一下", requiresLogin: true },
  { icon: "🎁", label: "优惠券", desc: "查可用券", prompt: "我现在有哪些优惠券可以用？", requiresLogin: true },
  { icon: "📚", label: "问规则", desc: "查平台政策", prompt: "七天无理由退货的规则是什么？" },
  { icon: "👤", label: "转人工", desc: "接入人工客服", prompt: "帮我转人工客服", requiresLogin: true },
];

function createFloatingSessionId() {
  if (typeof window === "undefined") return "floating-agent";
  const created =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 16)
      : `${Date.now()}${Math.random().toString(16).slice(2, 8)}`;
  localStorage.setItem(SESSION_KEY, created);
  return created;
}

function getFloatingSessionId() {
  if (typeof window === "undefined") return "floating-agent";
  const stored = localStorage.getItem(SESSION_KEY);
  return stored || createFloatingSessionId();
}

function routeContextFromPath(pathname: string | null) {
  if (!pathname) return {} as { product_id?: string; order_id?: string };
  const productMatch = pathname.match(/^\/products\/([^/?#]+)/);
  const orderMatch = pathname.match(/^\/orders\/([^/?#]+)/);
  return {
    product_id: productMatch?.[1],
    order_id: orderMatch?.[1],
  };
}

function buildContextPrompt(
  context: AgentContext,
  user: DemoUser | null,
  snapshot: ServiceSnapshot,
  content: string,
  capability: AgentCapability,
  targetOrder?: Order,
) {
  const lines = [
    content,
    "",
    "[系统补充上下文 - 不要把本段当成用户原话]",
    "你是平台正式 AI 客服，必须优先使用下面的真实数据库记录回答。",
    "禁止编造订单号、物流单号、金额、日期、商品和处理结论；如果记录里没有，就明确说当前没有查询到。",
    "如果用户问订单、物流、退款、投诉、人工客服，必须进入对应 Agent/工具流程，不要回答通用政策。",
  ];
  if (targetOrder) {
    lines.push(`本轮优先处理订单号：${targetOrder.order_id}`);
  }
  if (capability === "logistics" && targetOrder) {
    lines.push(`本轮任务：物流查询。请调用 LogisticsAgent / logistics_query 查询订单号 ${targetOrder.order_id} 的真实物流。`);
  }
  if (capability === "order" && targetOrder) {
    lines.push(`本轮任务：订单查询。请调用 OrderAgent / query_order 查询订单号 ${targetOrder.order_id} 的真实订单。`);
  }
  if (capability === "refund" && targetOrder) {
    lines.push(`本轮任务：退款/售后。请调用 RefundAgent / refund_apply 查询或处理订单号 ${targetOrder.order_id} 的退款售后。`);
  }
  if (capability === "complaint" && targetOrder) {
    lines.push(`本轮任务：投诉/升级。请调用 ComplaintAgent，关联订单号 ${targetOrder.order_id}，用户ID ${user?.user_id || ""}，必要时进入 SupervisorAgent 升级。`);
  }
  if (capability === "human") {
    lines.push("本轮任务：转人工。请调用 HumanTransferAgent / transfer_human 查询人工客服状态并给出排队信息。");
  }
  if (user) {
    lines.push(`当前登录用户：${user.user_id} / ${user.full_name} / ${user.phone}`);
  } else {
    lines.push("当前用户未登录：只能回答商品、活动、政策、导购、知识库等通用问题；涉及真实订单、退款、投诉时请引导用户登录。");
  }
  if (context.product) {
    lines.push(`当前商品：${context.product.product_id} / ${context.product.product_name} / 价格 ${context.product.price} / 库存 ${context.product.inventory_status}`);
  }
  if (context.order) {
    lines.push(`当前订单：${context.order.order_id} / 订单 ${context.order.order_status} / 支付 ${context.order.payment_status} / 配送 ${context.order.shipping_status} / 金额 ${context.order.total_amount}`);
    lines.push(`当前订单商品：${(context.order.items || []).map((item) => `${item.product_name} x${item.quantity}`).join("，") || "暂无"}`);
  }
  if (context.logistics) {
    lines.push(`物流：${context.logistics.carrier_name} / ${context.logistics.tracking_no} / ${context.logistics.current_status} / ${context.logistics.current_location}`);
    if (context.logistics.timeline?.length) {
      lines.push(`物流轨迹：${context.logistics.timeline.map((item) => `${item.event_time} ${item.location} ${item.status} ${item.description}`).join("；")}`);
    }
  }
  if (context.refund) {
    lines.push(`退款：${context.refund.refund_id} / ${context.refund.audit_status} / ${context.refund.refund_status}`);
  }
  if (context.complaints && context.complaints.length > 0) {
    lines.push(`当前投诉：${context.complaints.map((item) => `${item.complaint_id} / ${item.complaint_type} / ${item.complaint_status} / ${item.priority}`).join("；")}`);
  }
  if (snapshot.orders.length > 0) {
    lines.push("[该用户订单列表]");
    snapshot.orders.slice(0, 8).forEach((order) => {
      lines.push(
        `- ${order.order_id} / ${order.order_status} / 支付${order.payment_status} / 配送${order.shipping_status} / ${order.total_amount}${order.currency} / ${order.created_at} / 商品:${(order.items || []).map((item) => `${item.product_name}x${item.quantity}`).join("、") || "暂无"} / 物流:${order.logistics?.carrier_name || "暂无"} ${order.logistics?.tracking_no || ""} ${order.logistics?.current_status || ""} ${order.logistics?.current_location || ""}`,
      );
    });
  } else if (user) {
    lines.push("[该用户订单列表] 当前未查询到订单。");
  }
  if (snapshot.refunds.length > 0) {
    lines.push(`[该用户退款记录] ${snapshot.refunds.map((item) => `${item.refund_id} / 订单${item.order_id} / ${item.audit_status} / ${item.refund_status} / ${item.refund_amount}`).join("；")}`);
  } else if (user) {
    lines.push("[该用户退款记录] 当前未查询到退款。");
  }
  if (snapshot.complaints.length > 0) {
    lines.push(`[该用户投诉记录] ${snapshot.complaints.map((item) => `${item.complaint_id} / 订单${item.order_id || "无"} / ${item.complaint_type} / ${item.complaint_status} / ${item.priority}`).join("；")}`);
  } else if (user) {
    lines.push("[该用户投诉记录] 当前未查询到投诉。");
  }
  lines.push("回答要求：直接给结论和下一步操作；涉及售后、投诉、人工客服时说明当前系统记录和可执行动作；不要要求用户重复提供已经存在的信息。");
  return lines.join("\n");
}

function detectCapability(content: string): AgentCapability {
  const text = content.toLowerCase();
  if (/人工|真人|转人工|客服人员|活人/.test(text)) return "human";
  if (/投诉|抱怨|差评|升级|主管|赔付|补偿/.test(text)) return "complaint";
  if (/退款|退货|退钱|售后|退换|换货|审核/.test(text)) return "refund";
  if (/物流|快递|配送|运输|到哪|到哪里|发货|签收|运单|单号/.test(text)) return "logistics";
  if (/订单|下单|买了|最近|未完成|支付|收货/.test(text)) return "order";
  if (/商品|推荐|库存|有货|价格|参数|复购|买/.test(text)) return "product";
  if (/规则|政策|优惠|会员|活动|券|保价|配送范围|多久/.test(text)) return "knowledge";
  return "summary";
}

function parseTime(value?: string) {
  const time = value ? new Date(value).getTime() : 0;
  return Number.isNaN(time) ? 0 : time;
}

function chooseTargetOrder(context: AgentContext, snapshot: ServiceSnapshot, capability: AgentCapability) {
  if (context.order) return context.order;
  const orders = [...snapshot.orders].sort((a, b) => parseTime(b.created_at) - parseTime(a.created_at));
  if (orders.length === 0) return undefined;

  if (capability === "complaint") {
    return orders.find((order) => /异常|exception|破损|配送异常/.test(`${order.order_status}${order.shipping_status}${order.logistics?.current_status}`)) || orders[0];
  }
  if (capability === "refund") {
    const refundOrderIds = new Set(snapshot.refunds.map((refund) => refund.order_id));
    return orders.find((order) => refundOrderIds.has(order.order_id)) || orders.find((order) => /签收|收货|售后/.test(`${order.order_status}${order.shipping_status}${order.receipt_status}`)) || orders[0];
  }
  if (capability === "logistics") {
    return orders.find((order) => !/签收|已收货|completed|delivered/.test(`${order.shipping_status}${order.receipt_status}${order.logistics?.current_status}`)) || orders[0];
  }
  return orders[0];
}

function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

// 工具名 → 用户可读的动作标签（让"Agent 在干活"变得直观可见）。
const TOOL_LABELS: Record<string, string> = {
  query_order: "查询订单",
  logistics_query: "查询物流",
  refund_apply: "提交退款",
  create_ticket: "创建投诉工单",
  complaint_create: "创建投诉",
  transfer_human: "转接人工",
  query_inventory: "查询库存",
  product_query: "查询商品",
  recommend_products: "个性化推荐",
  knowledge_search: "检索知识库",
  query_coupons: "查询优惠券",
  complaint_lookup: "读取投诉记录",
};

const FLOW_LABELS: Record<string, string> = {
  OrderFlow: "订单",
  LogisticsFlow: "物流",
  RefundFlow: "退款售后",
  ProductFlow: "商品",
  KnowledgeFlow: "知识库",
  TicketFlow: "投诉工单",
  HumanTransferFlow: "转人工",
  CouponFlow: "优惠券",
  GeneralFlow: "通用",
  MultiAgentCoordinator: "多智能体协同",
};

function toolLabel(name: string) {
  return TOOL_LABELS[name] || name;
}

function flowLabel(name?: string) {
  if (!name) return "";
  return FLOW_LABELS[name] || name;
}

export default function FloatingAIAssistant() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [user, setUser] = useState<DemoUser | null>(null);
  const [context, setContext] = useState<AgentContext>({});
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [suggestionPage, setSuggestionPage] = useState(0);
  const [sessionId, setSessionId] = useState(getFloatingSessionId);
  const [contextRequest, setContextRequest] = useState<AssistantContextRequest>({});
  const [snapshot, setSnapshot] = useState<ServiceSnapshot>({ orders: [], refunds: [], complaints: [] });
  const [insights, setInsights] = useState<AssistantInsights | null>(null);
  const [events, setEvents] = useState<AssistantEvent[]>([]);
  const [dismissedEvents, setDismissedEvents] = useState<string[]>([]);
  const [trace, setTrace] = useState<AgentTraceData | null>(null);
  const [traceStore, setTraceStore] = useState<{ audits: unknown[]; workflows: unknown[] }>({ audits: [], workflows: [] });
  const [assistantView, setAssistantView] = useState<AssistantView>("chat");
  const [showOrderPicker, setShowOrderPicker] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const routeContext = useMemo(() => routeContextFromPath(pathname), [pathname]);
  const activeContext = useMemo(
    () => ({
      ...routeContext,
      product_id: contextRequest.product_id || routeContext.product_id,
      order_id: contextRequest.order_id || routeContext.order_id,
    }),
    [contextRequest, routeContext],
  );

  useEffect(() => {
    const openAssistant = (event: Event) => {
      const detail = (event as CustomEvent<AssistantContextRequest>).detail || {};
      setContextRequest(detail);
      setOpen(true);
    };
    window.addEventListener(OPEN_EVENT, openAssistant);
    if (sessionStorage.getItem("commerce_open_agent_on_home") === "1") {
      sessionStorage.removeItem("commerce_open_agent_on_home");
      setOpen(true);
    }
    return () => window.removeEventListener(OPEN_EVENT, openAssistant);
  }, []);

  useEffect(() => {
    const userId = contextRequest.user_id || getStoredUserId();
    if (!userId) {
      setUser(null);
      setSnapshot({ orders: [], refunds: [], complaints: [] });
      setInsights(null);
      setEvents([]);
      if (activeContext.product_id || activeContext.order_id) {
        commerceApi.agentContext(activeContext).then(setContext).catch(() => setContext({}));
      } else {
        setContext({});
      }
      return;
    }

    commerceApi.getUser(userId).then(setUser).catch(() => setUser(null));
    commerceApi.agentContext({ user_id: userId, ...activeContext }).then(setContext).catch(() => setContext({}));
    commerceApi.agentInsights(userId).then(setInsights).catch(() => setInsights(null));
    commerceApi.agentEvents(userId).then((data) => setEvents(data.events)).catch(() => setEvents([]));
    Promise.all([
      commerceApi.orders(userId).catch(() => []),
      commerceApi.refunds(userId).catch(() => []),
      commerceApi.complaints(userId).catch(() => []),
    ]).then(([orders, refunds, complaints]) => setSnapshot({ orders, refunds, complaints }));
    commerceApi.agentTrace().then(setTraceStore).catch(() => setTraceStore({ audits: [], workflows: [] }));
  }, [activeContext, contextRequest.user_id]);

  useEffect(() => {
    setSuggestionPage(0);
  }, [user]);

  useEffect(() => {
    if (!open) setAssistantView("chat");
  }, [open]);

  useEffect(() => {
    const userId = contextRequest.user_id || getStoredUserId();
    if (!userId) return;
    const poll = () => {
      // 主动服务轮询：每 30s 拉取"未读"主动事件（事件驱动 + 去重后端已处理）。
      commerceApi.agentEvents(userId)
        .then((data) => setEvents(data.events))
        .catch(() => undefined);
    };
    const timer = window.setInterval(poll, 30000);
    return () => window.clearInterval(timer);
  }, [contextRequest.user_id]);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open]);

  const suggestionBatches = user ? signedInSuggestionBatches : guestSuggestionBatches;
  const suggestions = suggestionBatches[suggestionPage % suggestionBatches.length];
  const visibleInsights = insights?.insights || [];
  const visibleEvents = events.filter((event) => !dismissedEvents.includes(event.event_id));

  const resetConversation = useCallback(() => {
    setMessages([]);
    setInput("");
    setError("");
    setLoading(false);
    setTrace(null);
    setAssistantView("chat");
    setSessionId(createFloatingSessionId());
  }, []);

  const send = useCallback(async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || loading) return;

    setError("");
    setInput("");
    setOpen(true);
    setAssistantView("chat");
    setShowOrderPicker(false);

    const visibleMessage = createUserMessage(trimmed);
    const nextMessages = [...messages, visibleMessage];
    setMessages(nextMessages);
    setLoading(true);

    try {
      const capability = detectCapability(trimmed);
      const targetOrder = selectedOrder || chooseTargetOrder(context, snapshot, capability);
      const history = messages.map((message) => ({
        role: message.role,
        content: message.content,
      }));
      const result = await sendChatMessage({
        message: buildContextPrompt(context, user, snapshot, trimmed, capability, targetOrder),
        history,
        session_id: sessionId,
      });
      // 把本轮 trace 附到该条 AI 消息上，便于在气泡下展示"AI 调了哪个 Agent/工具"，
      // 让用户直观看到助手是"真的执行了动作"而非只是回话。
      const assistantMessage: Message = result.trace
        ? { ...result.message, metadata: { ...result.message.metadata, trace: result.trace } }
        : result.message;
      setMessages((prev) => [...prev, assistantMessage]);
      setTrace(result.trace);
      commerceApi.agentTrace().then(setTraceStore).catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }, [context, loading, messages, selectedOrder, sessionId, snapshot, user]);

  const openInsight = useCallback((insight: AssistantInsight) => {
    setAssistantView("chat");
    setOpen(true);
    void send(insight.action_prompt);
  }, [send]);

  const openEvent = useCallback((event: AssistantEvent) => {
    setOpen(true);
    setAssistantView("chat");
    setDismissedEvents((items) => Array.from(new Set([...items, event.event_id])));
    void send(event.assistant_prompt);
  }, [send]);

  const renderEventBanner = () => visibleEvents.length > 0 && (
    <div className="rounded-2xl border border-orange-100 bg-orange-50/80 p-3 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-orange-100 text-sm font-black text-orange-700">!</div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-black text-slate-950">{visibleEvents[0].title}</div>
          <div className="mt-1 text-xs leading-5 text-slate-600">{visibleEvents[0].description}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" onClick={() => openEvent(visibleEvents[0])} className="rounded-full bg-slate-950 px-3 py-1.5 text-xs font-bold text-white">Handle now</button>
            <button type="button" onClick={() => setDismissedEvents((items) => [...items, visibleEvents[0].event_id])} className="rounded-full bg-white px-3 py-1.5 text-xs font-bold text-slate-500">Later</button>
          </div>
        </div>
      </div>
    </div>
  );

  // AI 气泡下的"Agent 执行芯片"：直观展示本轮命中的能力域 + 真实调用的工具 + 耗时，
  // 让用户一眼看到助手"真的执行了动作"，而不仅是回了一段话。
  const renderAgentChip = (msgTrace: AgentTraceData) => {
    const successTools = (msgTrace.tool_calls || []).filter((tc) => tc.success);
    const domain = flowLabel(msgTrace.selected_flow);
    if (!domain && successTools.length === 0) return null;
    return (
      <div className="ml-9 mt-1.5 flex flex-wrap items-center gap-1">
        {domain && (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold text-blue-700">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />{domain}
          </span>
        )}
        {successTools.map((tc, index) => (
          <span key={`${tc.tool_name}-${index}`} className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
            <span className="text-[9px]">✓</span>{toolLabel(tc.tool_name)}
          </span>
        ))}
        {typeof msgTrace.duration_ms === "number" && msgTrace.duration_ms > 0 && (
          <span className="text-[10px] font-medium text-slate-400">{(msgTrace.duration_ms / 1000).toFixed(1)}s</span>
        )}
      </div>
    );
  };

  const renderChatPage = () => (
    <div className="flex min-h-full flex-col">
      {messages.length === 0 ? (
        <div className="space-y-3">
          {renderEventBanner()}
          {/* 待办摘要条：把原"服务概览"的核心信息（数量 + 最高优先待办）折叠进对话主页，
              不再单独占一个 tab，避免与任务面板重复。 */}
          {user && insights && (
            <section className="rounded-2xl border border-blue-100 bg-gradient-to-br from-white to-blue-50/40 p-3.5 shadow-sm">
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-black text-slate-950">你好，{user.full_name}</div>
                <button type="button" onClick={() => send("帮我总结当前订单、物流、退款和投诉情况。")} className="rounded-full bg-slate-900 px-2.5 py-1 text-[10px] font-bold text-white transition hover:bg-slate-800">一键总结</button>
              </div>
              <div className="mt-2.5 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-xl bg-white p-2 shadow-sm"><div className="text-base font-black text-slate-950">{insights.counts.active_orders}</div><div className="text-[10px] text-slate-400">进行中订单</div></div>
                <div className="rounded-xl bg-white p-2 shadow-sm"><div className="text-base font-black text-slate-950">{insights.counts.open_refunds}</div><div className="text-[10px] text-slate-400">待跟进退款</div></div>
                <div className="rounded-xl bg-white p-2 shadow-sm"><div className="text-base font-black text-slate-950">{insights.counts.open_complaints}</div><div className="text-[10px] text-slate-400">未结投诉</div></div>
              </div>
              {visibleInsights.length > 0 && (
                <div className="mt-2.5 grid gap-1">
                  {visibleInsights.slice(0, 2).map((insight) => (
                    <button key={insight.insight_id} type="button" onClick={() => openInsight(insight)} className="flex items-center justify-between gap-2 rounded-xl bg-white px-2.5 py-2 text-left shadow-sm transition hover:bg-blue-50/70">
                      <span className="min-w-0 flex-1 truncate text-[11px] font-bold text-slate-700">{insight.title}</span>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${insight.severity === "urgent" ? "bg-red-100 text-red-700" : insight.severity === "high" ? "bg-orange-100 text-orange-700" : "bg-slate-100 text-slate-500"}`}>{insight.action_label}</span>
                    </button>
                  ))}
                </div>
              )}
            </section>
          )}
          <section className="rounded-2xl border border-blue-100 bg-white p-4 shadow-sm">
            <div className="text-sm font-black text-slate-950">今天帮你处理什么？</div>
            <p className="mt-1 text-[11px] text-slate-500">点下面任意场景，我会直接帮你把事办了 —— 不是教你怎么做，是替你做。</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {DEMO_SCENARIOS.map((sc) => (
                <button
                  type="button"
                  key={sc.label}
                  onClick={() => send(sc.prompt)}
                  className="group flex items-start gap-2 rounded-xl border border-slate-100 bg-white px-2.5 py-2.5 text-left transition hover:border-blue-200 hover:bg-blue-50/60 hover:shadow-sm"
                >
                  <span className="text-base leading-none">{sc.icon}</span>
                  <span className="min-w-0">
                    <span className="block text-xs font-black text-slate-800 group-hover:text-blue-700">{sc.label}</span>
                    <span className="block text-[10px] leading-4 text-slate-400">{sc.desc}</span>
                  </span>
                </button>
              ))}
            </div>
          </section>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-xl border border-blue-100 bg-white px-3 py-2 text-[11px] text-slate-500 shadow-sm"><div>{user ? "结合服务上下文回复" : "访客模式"}</div><button type="button" onClick={resetConversation} className="rounded-full bg-slate-900 px-2.5 py-1 text-[10px] font-bold text-white">重新开始</button></div>
          {messages.map((message) => { const isUser = message.role === "user"; const msgTrace = message.metadata?.trace as AgentTraceData | undefined; return (<div key={message.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}><div className={`max-w-[85%] ${isUser ? "items-end" : "items-start"}`}><div className={`flex items-end gap-1.5 ${isUser ? "flex-row-reverse" : "flex-row"}`}>{!isUser && (<div className="relative h-7 w-7 shrink-0 overflow-hidden rounded-full bg-[#eef5ff] shadow-sm"><img src="/assistant/ai-assistant-avatar.png" alt="" className="assistant-avatar-3d absolute inset-0 h-full w-full object-cover object-center" /></div>)}<div className={`whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed shadow-sm ${isUser ? "rounded-br-sm bg-gradient-to-r from-[#2563eb] to-[#7c3aed] text-white" : "rounded-bl-sm border border-blue-50 bg-white text-slate-800"}`}>{message.content}</div></div>{!isUser && msgTrace && renderAgentChip(msgTrace)}<div className={`mt-0.5 px-9 text-[10px] text-slate-400 ${isUser ? "text-right" : "text-left"}`}>{formatTime(message.timestamp)}</div></div></div>); })}
          {loading && <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-100 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-500 shadow-sm"><span className="typing-dot h-1 w-1 rounded-full bg-[#2563eb]" /><span className="typing-dot h-1 w-1 rounded-full bg-[#2563eb]" /><span className="typing-dot h-1 w-1 rounded-full bg-[#2563eb]" />思考中</div>}
          {error && <div className="rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600">{error}</div>}
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );

  const renderGuestWelcome = () => (
    <div className="flex flex-col items-center">
      {/* Hero section */}
      <div className="relative mb-4 mt-2 flex flex-col items-center">
        <div className="relative h-28 w-28 overflow-hidden rounded-full">
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-blue-100 via-purple-50 to-pink-100 opacity-80" />
          <img src="/assistant/ai-assistant-avatar.png" alt="ShopEase AI" className="assistant-avatar-3d relative h-full w-full object-cover object-center" />
        </div>
        <h2 className="mt-3 text-lg font-black text-slate-950">ShopEase AI 助手</h2>
        <p className="mt-1 text-xs text-slate-500">购物问题找我就对了！</p>
        <div className="mt-3 flex gap-2">
          <Link href="/register" className="rounded-full border border-slate-200 px-4 py-1.5 text-xs font-bold text-slate-600 transition hover:border-blue-200 hover:text-blue-700">注册</Link>
          <Link href="/login" className="rounded-full bg-slate-900 px-4 py-1.5 text-xs font-bold text-white shadow-sm">登录</Link>
        </div>
      </div>

      {/* Demo hint banner：让第一次用/演示的人立刻知道怎么进入完整能力 */}
      <div className="mb-4 w-full rounded-2xl border border-blue-100 bg-gradient-to-r from-blue-50 via-white to-indigo-50 p-3.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs font-black text-slate-900">🚀 想看完整能力？用演示账号登录</div>
            <p className="mt-1 text-[11px] leading-4 text-slate-500">登录后可查真实订单、物流、退款、投诉，并让我直接替你执行。</p>
            <div className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-white px-2 py-1 text-[10px] font-bold text-blue-700 shadow-sm">
              演示账号 <span className="rounded bg-blue-50 px-1.5 py-0.5">13560569291</span> / <span className="rounded bg-blue-50 px-1.5 py-0.5">123456</span>
            </div>
          </div>
          <span className="text-2xl">🔑</span>
        </div>
      </div>

      {/* Recommendations */}
      <div className="w-full">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[11px] font-bold text-slate-500">为你推荐：</span>
          <button type="button" onClick={() => setSuggestionPage((p) => p + 1)} className="flex items-center gap-1 text-[11px] font-bold text-slate-400 transition hover:text-blue-600">换一换 <span className="text-sm">↻</span></button>
        </div>
        <div className="grid gap-1.5">
          {suggestions.map((item) => (
            <button key={item} type="button" onClick={() => send(item)} className="flex items-center gap-2 rounded-xl border border-slate-100 bg-white px-3 py-2.5 text-left transition hover:border-blue-200 hover:bg-blue-50/60">
              <span className="text-sm text-blue-500">✦</span>
              <span className="text-xs font-bold text-slate-700">{item}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );

  const renderTracePage = () => (
    <div className="space-y-3">
      <section className="overflow-hidden rounded-2xl border border-blue-100 bg-white shadow-sm"><div className="border-b border-blue-50 px-4 py-3"><div className="text-sm font-black text-slate-950">Agent 面板</div><p className="mt-0.5 text-[11px] text-slate-500">意图路由、工具调用、工作流状态</p></div><DebugPanel trace={trace} alwaysVisible /></section>
      <section className="rounded-2xl border border-slate-100 bg-white p-3 shadow-sm"><div className="mb-2 text-xs font-black text-slate-950">最近工具审计</div>{traceStore.audits.slice(0, 3).map((audit, index) => (<pre key={index} className="mb-1.5 max-h-24 overflow-hidden rounded-xl bg-slate-50 p-2 text-[10px] text-slate-600">{JSON.stringify(audit, null, 2).slice(0, 200)}</pre>))}{traceStore.audits.length === 0 && <div className="rounded-xl bg-slate-50 p-3 text-[11px] text-slate-400">暂无记录</div>}</section>
      <section className="rounded-2xl border border-slate-100 bg-white p-3 shadow-sm"><div className="mb-2 text-xs font-black text-slate-950">工作流运行</div>{traceStore.workflows.slice(0, 3).map((workflow, index) => (<pre key={index} className="mb-1.5 max-h-24 overflow-hidden rounded-xl bg-slate-50 p-2 text-[10px] text-slate-600">{JSON.stringify(workflow, null, 2).slice(0, 200)}</pre>))}{traceStore.workflows.length === 0 && <div className="rounded-xl bg-slate-50 p-3 text-[11px] text-slate-400">暂无记录</div>}</section>
    </div>
  );

  return (
    <>
      {!open && (
        <div className="fixed right-3 top-1/2 z-50 flex -translate-y-1/2 flex-col items-end gap-2 sm:right-5">
          {visibleEvents.length > 0 && (
            <button type="button" onClick={() => openEvent(visibleEvents[0])} className="mr-2 max-w-[220px] rounded-2xl border border-orange-100 bg-white px-4 py-3 text-left shadow-[0_18px_48px_rgba(249,115,22,0.18)] transition hover:-translate-x-1"><div className="text-xs font-black text-orange-600">新提醒</div><div className="mt-1 line-clamp-2 text-sm font-bold leading-5 text-slate-900">{visibleEvents[0].title}</div><div className="mt-1 line-clamp-2 text-xs leading-4 text-slate-500">{visibleEvents[0].description}</div></button>
          )}
          <button type="button" onClick={() => setOpen(true)} className="assistant-side-float group relative h-[154px] w-[108px] overflow-visible rounded-l-[32px] rounded-r-2xl border border-blue-100 bg-white/95 shadow-[0_18px_48px_rgba(37,99,235,0.24)] backdrop-blur transition hover:-translate-x-1 hover:shadow-[0_24px_58px_rgba(37,99,235,0.32)]" aria-label="AI assistant"><span className="assistant-aura absolute left-1/2 top-5 h-24 w-24 -translate-x-1/2 rounded-full bg-blue-200/50" /><span className="absolute -left-[92px] top-8 hidden rounded-full border border-blue-100 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition group-hover:-translate-x-1 md:block">问我问题</span><img src="/assistant/ai-assistant-avatar.png" alt="ShopEase AI 助手" className="assistant-avatar-float absolute -top-10 left-1/2 h-36 w-36 -translate-x-1/2 object-contain" /><span className="absolute bottom-8 left-1/2 w-[74px] -translate-x-1/2 rounded-full bg-[#2563eb] px-2 py-1 text-[12px] font-black text-white shadow-sm">AI 助手</span><span className="absolute bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 text-[11px] font-semibold text-emerald-600"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />在线</span></button>
        </div>
      )}

      {open && (
        <section className={`fixed z-50 flex overflow-hidden border border-blue-100 bg-white shadow-[0_28px_90px_rgba(15,23,42,0.28)] transition-all duration-300 ${expanded ? "bottom-3 right-3 left-3 top-3 rounded-[20px] sm:bottom-4 sm:right-4 sm:left-4 sm:top-4" : "bottom-5 right-5 top-[60px] w-[25vw] min-w-[380px] max-w-[560px] max-h-[calc(100vh-80px)] rounded-2xl max-sm:left-3 max-sm:right-3 max-sm:top-3 max-sm:bottom-3 max-sm:w-auto max-sm:min-w-0 max-sm:max-w-none max-sm:max-h-none"}`}>
          {/* Sidebar - only in expanded + logged in */}
          {user && <aside className={`hidden shrink-0 flex-col border-r border-blue-50 bg-[#f7fbff] p-5 ${expanded ? "w-64 lg:flex" : "hidden"}`}>
            <div className="flex items-center gap-3"><div className="relative h-16 w-16 overflow-hidden rounded-2xl bg-white shadow-sm"><img src="/assistant/ai-assistant-avatar.png" alt="" className="assistant-avatar-3d absolute inset-0 h-full w-full object-cover object-center" /></div><div><div className="text-base font-black text-slate-950">ShopEase AI</div><div className="mt-1 text-xs font-semibold text-emerald-600">在线服务中</div></div></div>
            <nav className="mt-8 grid gap-2">{(["chat", "trace"] as AssistantView[]).map((view) => (<button key={view} type="button" onClick={() => setAssistantView(view)} className={`rounded-2xl px-4 py-3 text-left text-sm font-black transition ${assistantView === view ? "bg-slate-950 text-white shadow-lg" : "text-slate-600 hover:bg-white hover:text-slate-950"}`}>{view === "chat" ? "AI 对话" : "Agent 面板"}</button>))}</nav>
            <div className="mt-auto rounded-2xl bg-white p-4 text-xs leading-5 text-slate-500 shadow-sm">AI 回复仅供参考，订单和售后以平台记录为准。</div>
          </aside>}

          <div className="flex min-w-0 flex-1 flex-col">
            {/* Header */}
            <header className="flex items-center justify-between border-b border-blue-50 bg-gradient-to-r from-[#f6fbff] via-white to-[#f8f4ff] px-4 py-3">
              <div className="min-w-0 flex items-center gap-3">{!expanded && <div className="relative h-9 w-9 shrink-0 overflow-hidden rounded-full bg-white shadow-sm"><img src="/assistant/ai-assistant-avatar.png" alt="" className="assistant-avatar-3d absolute inset-0 h-full w-full object-cover object-center" /></div>}<div><div className="truncate text-sm font-black text-slate-950">{user ? (assistantView === "chat" ? "AI 对话" : "Agent 面板") : "ShopEase AI 助手"}</div>{expanded && user && <div className="mt-0.5 truncate text-xs text-slate-500">{user.full_name}，正在结合你的服务上下文回复</div>}</div></div>
              <div className="flex items-center gap-1.5">{user && <button type="button" onClick={resetConversation} className="hidden rounded-full border border-slate-100 px-2.5 py-1.5 text-[11px] font-bold text-slate-500 hover:text-blue-700 sm:inline-flex">清空</button>}<button type="button" onClick={() => setExpanded((value) => !value)} className="h-8 rounded-full border border-slate-100 px-2.5 text-[11px] font-bold text-slate-600 hover:text-blue-700" aria-label={expanded ? "还原窗口" : "最大化"}>{expanded ? "还原" : "展开"}</button><button type="button" onClick={() => setOpen(false)} className="grid h-8 w-8 place-items-center rounded-full text-sm font-black text-slate-500 hover:bg-slate-100 hover:text-slate-950" aria-label="关闭助手">✕</button></div>
            </header>

            {/* Tab bar - only when logged in */}
            {user && <div className="flex gap-1.5 overflow-x-auto border-b border-blue-50 bg-white px-3 py-2">{(["chat", "trace"] as AssistantView[]).map((view) => (<button key={view} type="button" onClick={() => setAssistantView(view)} className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-bold transition ${assistantView === view ? "bg-slate-950 text-white" : "bg-slate-50 text-slate-500 hover:bg-slate-100"}`}>{view === "chat" ? "对话" : "Agent 面板"}</button>))}</div>}

            {/* Main content */}
            <main className="chat-scrollbar flex-1 overflow-y-auto bg-gradient-to-b from-[#f7fbff] to-white p-3 sm:p-4">
              {user ? (
                <>{assistantView === "chat" && renderChatPage()}{assistantView === "trace" && renderTracePage()}</>
              ) : (
                messages.length > 0 ? renderChatPage() : renderGuestWelcome()
              )}
            </main>

            {/* Footer with input - always show for guest chat or logged-in chat view */}
            {(user ? assistantView === "chat" : true) && <footer className="border-t border-blue-50 bg-white p-3">{selectedOrder && (<div className="mb-2 flex items-center gap-1.5 rounded-lg border border-blue-100 bg-blue-50/60 px-2.5 py-1.5"><span className="text-[10px] font-bold text-blue-700">订单：</span><span className="min-w-0 flex-1 truncate text-[10px] text-slate-700">{selectedOrder.order_id.slice(-8)} / {(selectedOrder.items || []).map((i) => i.product_name).join(", ") || "暂无"}</span><button type="button" onClick={() => setSelectedOrder(null)} className="shrink-0 text-[10px] font-bold text-slate-400 hover:text-red-500">✕</button></div>)}{showOrderPicker && snapshot.orders.length > 0 && (<div className="mb-2 max-h-36 overflow-y-auto rounded-lg border border-blue-100 bg-white shadow-sm"><div className="sticky top-0 border-b border-blue-50 bg-white/95 px-2.5 py-1.5 text-[10px] font-bold text-slate-500 backdrop-blur">选择订单</div>{snapshot.orders.map((order) => (<button key={order.order_id} type="button" onClick={() => { setSelectedOrder(order); setShowOrderPicker(false); }} className={`flex w-full items-center gap-1.5 border-b border-slate-50 px-2.5 py-2 text-left transition hover:bg-blue-50/60 ${selectedOrder?.order_id === order.order_id ? "bg-blue-50" : ""}`}><span className="text-sm">📦</span><span className="min-w-0 flex-1"><span className="block truncate text-[11px] font-bold text-slate-800">{(order.items || []).map((i) => i.product_name).join(", ") || order.order_id}</span><span className="block text-[10px] text-slate-400">{order.order_status} / {order.currency || "CNY"} {order.total_amount}</span></span></button>))}</div>)}<div className="flex items-end gap-2 rounded-xl border border-blue-100 bg-[#f8fbff] p-1.5">{user && snapshot.orders.length > 0 && (<button type="button" onClick={() => setShowOrderPicker((v) => !v)} className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg text-sm transition hover:bg-blue-100 ${showOrderPicker ? "bg-blue-100 text-blue-700" : "text-slate-400"}`} aria-label="选择订单" title="选择订单">📋</button>)}<textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(input); } }} rows={1} placeholder={user ? (selectedOrder ? `针对 ${selectedOrder.order_id.slice(-6)} 提问...` : "问订单、物流、退款都可以") : "请描述你遇到的问题"} className="max-h-24 min-h-[36px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-xs outline-none placeholder:text-slate-400" /><button type="button" onClick={() => send(input)} disabled={!input.trim() || loading} className="h-9 shrink-0 rounded-lg bg-gradient-to-r from-[#2563eb] to-[#7c3aed] px-3 text-xs font-bold text-white shadow-sm transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0" aria-label="发送">发送</button></div></footer>}
          </div>
        </section>
      )}
    </>
  );
}
