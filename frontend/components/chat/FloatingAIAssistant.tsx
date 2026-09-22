"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import DebugPanel from "@/components/debug/DebugPanel";
import { commerceApi, getStoredUserId, type AgentContext, type AssistantEvent, type AssistantInsight, type AssistantInsights, type Complaint, type DemoUser, type Order, type Refund } from "@/services/commerce";
import { sendChatMessage, sendChatMessageStream, type ChatResult } from "@/services/chat";
import { createUserMessage, generateMessageId, type Message } from "@/types/message";
import type { AgentTraceData } from "@/types/trace";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  BookOpenText,
  Brain,
  ClipboardList,
  Headset,
  KeyRound,
  MapPin,
  Megaphone,
  Package,
  PackageSearch,
  ReceiptText,
  RefreshCcw,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  TicketPercent,
  Truck,
  Wrench,
  type LucideIcon,
} from "lucide-react";

const SESSION_KEY = "commerce_floating_agent_session";
const OPEN_EVENT = "commerce:open-agent";

// 助手人格设定：给数字人一个名字和身份，让用户感觉在和"人"对话而不是冷冰冰的系统。
// "小易" 取自"小易电商助手"，也贴合国内数字助手命名习惯（小度/小爱/小冰）。
const ASSISTANT_NAME = "小易";
const ASSISTANT_TITLE = "小易电商助手";
const ASSISTANT_TAGLINE = "你的专属购物管家，能查能办不只是聊";

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
// requiresOrder: 该场景必须先绑定一个订单。用户未选单时点击 → 先弹订单选择窗口，
// 选完再带着订单执行；已选单则直接针对该订单执行。
type DemoScenario = { icon: LucideIcon; label: string; desc: string; prompt: string; requiresLogin?: boolean; requiresOrder?: boolean };

const DEMO_SCENARIOS: DemoScenario[] = [
  { icon: PackageSearch, label: "查订单", desc: "看最近订单状态", prompt: "帮我看看这个订单现在什么状态", requiresLogin: true, requiresOrder: true },
  { icon: Truck, label: "追物流", desc: "快递到哪了", prompt: "这个订单的快递到哪了？预计什么时候到", requiresLogin: true, requiresOrder: true },
  { icon: ReceiptText, label: "退款", desc: "直接发起退款", prompt: "我想申请退款，帮我处理一下这个订单", requiresLogin: true, requiresOrder: true },
  { icon: Sparkles, label: "推荐", desc: "按我的历史推荐", prompt: "根据我买过的东西，帮我推荐几款值得入手的商品", requiresLogin: true },
  { icon: Megaphone, label: "投诉", desc: "创建投诉工单", prompt: "我要投诉，帮我登记一下这个订单", requiresLogin: true, requiresOrder: true },
  { icon: TicketPercent, label: "优惠券", desc: "查可用券", prompt: "我现在有哪些优惠券可以用？", requiresLogin: true },
  { icon: BookOpenText, label: "问规则", desc: "查平台政策", prompt: "七天无理由退货的规则是什么？" },
  { icon: Headset, label: "转人工", desc: "接入人工客服", prompt: "帮我转人工客服", requiresLogin: true },
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
  // 知识查询时在用户原始问题前加标记，让后端 KnowledgeFlow 能精确提取查询词做向量检索
  const userContent = capability === "knowledge" ? `[用户请求]${content}` : content;
  const lines = [
    userContent,
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
    lines.push(`本轮任务：退款/售后。必须且只能处理订单号 ${targetOrder.order_id}（当前状态：订单${targetOrder.order_status} / 配送${targetOrder.shipping_status}）。禁止自行选择其他订单。请调用 RefundAgent / refund_apply 查询或处理该订单的退款售后。`);
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
  // 知识查询和通用总结不注入用户个人订单快照，避免AI被个人数据劫持而无法回答通用政策
  if (capability !== "knowledge" && capability !== "summary") {
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
  }
  lines.push("回答要求：直接给结论和下一步操作；涉及售后、投诉、人工客服时说明当前系统记录和可执行动作；不要要求用户重复提供已经存在的信息。");
  return lines.join("\n");
}

function detectCapability(content: string): AgentCapability {
  const text = content.toLowerCase();
  // 政策咨询优先级最高：含"规则/政策/怎么/多久"等问询词时走知识库，
  // 即使同时含有"退货/退款"等词（如"七天无理由退货的规则是什么"）也不走退款流程。
  if (/规则|政策|怎么申请|如何申请|是什么|多久|几天|条件|范围|标准|流程/.test(text) &&
      !/我要退|帮我退|申请退款|申请退货|发起退/.test(text)) return "knowledge";
  if (/人工|真人|转人工|客服人员|活人/.test(text)) return "human";
  if (/投诉|抱怨|差评|升级|主管|赔付|补偿/.test(text)) return "complaint";
  if (/退款|退货|退钱|售后|退换|换货|审核/.test(text)) return "refund";
  if (/物流|快递|配送|运输|到哪|到哪里|发货|签收|运单|单号/.test(text)) return "logistics";
  if (/订单|下单|买了|最近|未完成|支付|收货/.test(text)) return "order";
  if (/商品|推荐|库存|有货|价格|参数|复购|买/.test(text)) return "product";
  if (/优惠|会员|活动|券|保价|配送范围/.test(text)) return "knowledge";
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

// ─── Round 1 helpers ────────────────────────────────────────────────────────

/** AI 气泡左侧强调色：Dark Premium 全站唯一主色 accent（不再按 Flow 分色）。 */
function getFlowAccentColor(_flowName?: string): string {
  return "var(--accent)";
}

// ─── 数字人 Hero 头部：直接充当面板头部，承载名字/状态 + 清空/展开/关闭控制 ──────────
function AssistantHeroBanner({
  userName,
  viewLabel,
  onReset,
  onToggleExpand,
  onClose,
  expanded,
  showReset,
}: {
  userName?: string;
  viewLabel?: string;
  onReset?: () => void;
  onToggleExpand: () => void;
  onClose: () => void;
  expanded: boolean;
  showReset: boolean;
}) {
  return (
    <section className="relative shrink-0 overflow-hidden bg-elevated/90 backdrop-blur-xl border-b border-line px-4 py-3.5">
      {/* 背景装饰光斑 */}
      <span className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-accent/20 blur-2xl" />
      <span className="pointer-events-none absolute -bottom-12 -left-8 h-36 w-36 rounded-full bg-accent/15 blur-2xl" />
      {/* 网格纹理 */}
      <span
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
          backgroundSize: "18px 18px",
        }}
      />
      {/* 控制按钮：清空 / 展开 / 关闭 */}
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1.5">
        {showReset && onReset && (
          <button type="button" onClick={onReset} className="hidden rounded-full border border-white/30 bg-white/15 px-2.5 py-1 text-[11px] font-bold text-white backdrop-blur transition hover:bg-white/25 sm:inline-flex" aria-label="清空对话">清空</button>
        )}
        <button type="button" onClick={onToggleExpand} className="rounded-full border border-white/30 bg-white/15 px-2.5 py-1 text-[11px] font-bold text-white backdrop-blur transition hover:bg-white/25" aria-label={expanded ? "还原窗口" : "最大化"}>{expanded ? "还原" : "展开"}</button>
        <button type="button" onClick={onClose} className="grid h-7 w-7 place-items-center rounded-full bg-white/15 text-sm font-black text-white backdrop-blur transition hover:bg-white/25" aria-label="关闭助手">✕</button>
      </div>

      <div className="relative flex items-center gap-4">
        {/* 大尺寸数字人形象 */}
        <div className="relative shrink-0">
          <span className="assistant-aura absolute inset-0 rounded-full bg-accent/35" />
          <div className="relative h-[72px] w-[72px] overflow-hidden rounded-full bg-elevated shadow-xl ring-4 ring-line">
            <img
              src="/assistant/ai-assistant-avatar.png"
              alt={ASSISTANT_NAME}
              className="assistant-avatar-3d absolute inset-0 h-full w-full object-cover object-center"
            />
          </div>
          <span className="absolute bottom-0.5 right-0.5 flex h-4 w-4 items-center justify-center rounded-full border-2 border-elevated bg-success">
            <span className="absolute inset-0 animate-ping rounded-full bg-success opacity-75" />
            <span className="relative h-1 w-1 rounded-full bg-white" />
          </span>
        </div>
        {/* 文案区 */}
        <div className="min-w-0 flex-1 pr-24">
          <div className="flex items-center gap-1.5">
            <h2 className="truncate text-lg font-black text-white">{ASSISTANT_NAME}</h2>
            <span className="shrink-0 rounded-full bg-white/25 px-2 py-0.5 text-[10px] font-bold text-white backdrop-blur">AI 数字人</span>
            {viewLabel && <span className="shrink-0 rounded-full bg-black/25 px-2 py-0.5 text-[10px] font-bold text-white backdrop-blur">{viewLabel}</span>}
          </div>
          <p className="mt-0.5 truncate text-xs font-medium text-white/85">
            {userName ? `${userName}，我在呢` : "你好，我在呢"}
          </p>
          <p className="mt-1 line-clamp-1 text-[11px] leading-4 text-white/70">{ASSISTANT_TAGLINE}</p>
        </div>
      </div>
    </section>
  );
}

// ─── Capability-aware loading phase messages ─────────────────────────────────
const CAPABILITY_LOADING_PHASES: Record<AgentCapability, string[]> = {
  logistics: ["连接物流系统...", "追踪快递轨迹...", "定位当前位置..."],
  order:     ["读取订单数据...", "分析订单状态...", "整理订单详情..."],
  refund:    ["查询退款记录...", "核对退款资格...", "处理退款申请..."],
  complaint: ["核查投诉记录...", "创建工单...",    "通知处理团队..."],
  human:     ["查询客服排队...", "连接人工坐席...", "正在分配客服..."],
  product:   ["检索商品信息...", "匹配推荐算法...", "个性化分析..."],
  knowledge: ["检索知识库...",   "匹配相关规则...", "整理答案内容..."],
  summary:   ["分析服务状态...", "调用 AI Agent...", "生成回复中..."],
};

/** Cycles through capability-specific status phrases while the backend processes the request. */
function SmartLoadingIndicator({ capability }: { capability: AgentCapability }) {
  const phases = CAPABILITY_LOADING_PHASES[capability];
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setPhase((p) => (p + 1) % phases.length), 1400);
    return () => clearInterval(timer);
  }, [phases.length]);
  return (
    <div className="flex items-center gap-2.5 rounded-2xl border border-accent/30 bg-accent/[0.07] px-4 py-2.5 shadow-card-inset">
      <div className="flex items-center gap-1">
        <span className="agent-loading-dot h-1.5 w-1.5 rounded-full bg-accent" />
        <span className="agent-loading-dot h-1.5 w-1.5 rounded-full bg-accent" />
        <span className="agent-loading-dot h-1.5 w-1.5 rounded-full bg-accent" />
      </div>
      <span className="text-[11px] font-semibold text-secondary">{phases[phase]}</span>
    </div>
  );
}

/** Placeholder shown while user insights are loading — mirrors the real stats layout. */
function SkeletonInsights() {
  return (
    <section className="rounded-2xl border border-accent/30 bg-surface p-3.5 shadow-card-inset">
      <div className="flex items-center justify-between gap-2">
        <div className="skeleton h-3.5 w-28" />
        <div className="skeleton h-6 w-16 rounded-full" />
      </div>
      <div className="mt-2.5 grid grid-cols-3 gap-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-xl bg-elevated p-2">
            <div className="skeleton mx-auto mb-1 h-7 w-8" />
            <div className="skeleton mx-auto h-2.5 w-14" />
          </div>
        ))}
      </div>
      <div className="mt-2.5 grid gap-1">
        <div className="skeleton h-9 w-full rounded-xl" />
        <div className="skeleton h-9 w-full rounded-xl" />
      </div>
    </section>
  );
}

/** Thumbs-up / thumbs-down feedback row shown under each AI reply. State is local-only (demo). */
function MessageFeedback({ msgId: _msgId }: { msgId: string }) {
  const [vote, setVote] = useState<"up" | "down" | null>(null);
  return (
    <div className="ml-9 mt-1 flex items-center gap-1.5">
      <button
        type="button"
        onClick={() => setVote((v) => (v === "up" ? null : "up"))}
        title="有帮助"
        className={`grid h-6 w-6 place-items-center rounded-full text-sm transition hover:scale-110 ${
          vote === "up"
            ? "bg-success/15 text-success"
            : "text-tertiary hover:bg-elevated hover:text-secondary"
        }`}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={() => setVote((v) => (v === "down" ? null : "down"))}
        title="没帮助"
        className={`grid h-6 w-6 place-items-center rounded-full text-sm transition hover:scale-110 ${
          vote === "down"
            ? "bg-danger/15 text-danger"
            : "text-tertiary hover:bg-elevated hover:text-secondary"
        }`}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>
      {vote && (
        <span className="text-[10px] font-medium text-tertiary">
          {vote === "up" ? "感谢反馈" : "已记录，我们会改进"}
        </span>
      )}
    </div>
  );
}

/** Renders AI reply text with full Markdown support.
 *  When  is true plays a typewriter reveal character-by-character;
 *  ReactMarkdown renders partial markdown gracefully throughout. */
function AiMessageContent({ content, streaming }: { content: string; streaming: boolean }) {
  // streaming 时 content 来自后端 SSE 的真实增量，直接渲染即可；
  // typewriter-cursor 仅作为"正在输出"的光标提示。
  return (
    <div className={streaming ? "typewriter-cursor" : ""}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p:          ({ children }) => <p className="mb-1.5 last:mb-0 leading-relaxed">{children}</p>,
          ul:         ({ children }) => <ul className="mb-1.5 ml-4 list-disc space-y-0.5">{children}</ul>,
          ol:         ({ children }) => <ol className="mb-1.5 ml-4 list-decimal space-y-0.5">{children}</ol>,
          li:         ({ children }) => <li className="leading-relaxed">{children}</li>,
          strong:     ({ children }) => <strong className="font-bold text-primary">{children}</strong>,
          em:         ({ children }) => <em className="italic text-secondary">{children}</em>,
          h1:         ({ children }) => <p className="mb-1.5 font-black text-primary">{children}</p>,
          h2:         ({ children }) => <p className="mb-1.5 font-bold text-primary">{children}</p>,
          h3:         ({ children }) => <p className="mb-1 font-bold text-primary">{children}</p>,
          hr:         () => <hr className="my-2 border-line" />,
          blockquote: ({ children }) => <blockquote className="border-l-2 border-accent/40 pl-2.5 italic text-secondary">{children}</blockquote>,
          pre:        ({ children }) => <pre className="my-1.5 overflow-x-auto rounded-lg bg-elevated p-2.5 text-[10px] text-secondary">{children}</pre>,
          code:       ({ children }) => <code className="rounded bg-elevated px-1 py-0.5 font-mono text-[10px] text-secondary">{children}</code>,
          a:          ({ href, children }) => <a href={href} className="text-accent underline hover:text-accent-hover" target="_blank" rel="noopener noreferrer">{children}</a>,
          table:      ({ children }) => <div className="mb-1.5 overflow-x-auto"><table className="w-full border-collapse text-[10px]">{children}</table></div>,
          th:         ({ children }) => <th className="border border-line bg-elevated px-2 py-1 text-left font-bold text-secondary">{children}</th>,
          td:         ({ children }) => <td className="border border-line px-2 py-1 text-secondary">{children}</td>,
        }}
      >
        {content || " "}
      </ReactMarkdown>
    </div>
  );
}

/** Visual execution timeline for the Agent panel — shows intent routing + tool call chain. */
function AgentTimeline({ trace }: { trace: AgentTraceData | null }) {
  if (!trace) {
    return (
      <div className="rounded-2xl bg-elevated p-6 text-center text-xs text-tertiary">
        发送一条消息后，这里会显示 Agent 的执行路径
      </div>
    );
  }

  const tools = trace.tool_calls || [];
  const flowColor = getFlowAccentColor(trace.selected_flow);
  const confPct = Math.round((trace.confidence || 0) * 100);

  return (
    <div className="space-y-3">
      {/* ── Intent row ── */}
      <div className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2.5">
        <Brain className="h-4 w-4 shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-black text-primary">
              {trace.intent_desc || trace.intent || "意图识别"}
            </span>
            <span
              className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                confPct >= 80 ? "bg-success/15 text-success" : confPct >= 50 ? "bg-warning/15 text-warning" : "bg-danger/15 text-danger"
              }`}
            >
              {confPct}%
            </span>
          </div>
          {trace.reasoning && (
            <p className="mt-0.5 line-clamp-2 text-[10px] leading-4 text-secondary">{trace.reasoning}</p>
          )}
        </div>
        {trace.duration_ms > 0 && (
          <span className="shrink-0 text-[10px] font-medium text-tertiary">
            {(trace.duration_ms / 1000).toFixed(1)}s
          </span>
        )}
      </div>

      {/* ── Flow badge ── */}
      <div className="flex items-center gap-2 px-1">
        <div className="h-px flex-1 bg-elevated" />
        <span
          className="rounded-full px-3 py-1 text-[10px] font-black text-white shadow-sm"
          style={{ background: flowColor }}
        >
          {flowLabel(trace.selected_flow) || trace.selected_flow || "Flow"}
        </span>
        <div className="h-px flex-1 bg-elevated" />
      </div>

      {/* ── Tool call chain ── */}
      {tools.length > 0 ? (
        <div className="relative pl-6">
          {/* vertical spine */}
          <div className="absolute left-[11px] top-2 bottom-2 w-px bg-line" />
          <div className="space-y-2">
            {tools.map((tc, idx) => (
              <div key={idx} className="relative flex items-start gap-2.5">
                {/* node dot */}
                <div
                  className={`absolute -left-[13px] mt-1 h-3 w-3 rounded-full border-2 border-surface shadow-sm ${
                    tc.success ? "bg-success" : "bg-danger"
                  }`}
                />
                <div className="flex-1 rounded-xl border border-line bg-surface px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-bold text-secondary">
                      {tc.success ? "✓ " : "✗ "}{toolLabel(tc.tool_name)}
                    </span>
                    {tc.latency_ms != null && (
                      <span className="text-[10px] text-tertiary">{tc.latency_ms}ms</span>
                    )}
                  </div>
                  {!tc.success && (
                    <p className="mt-0.5 text-[10px] text-danger">执行失败</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="px-1 text-[11px] text-tertiary">本轮未调用外部工具（直接 LLM 回答）</p>
      )}

      {/* ── RAG indicator ── */}
      {trace.rag_used && (
        <div className="flex items-center gap-1.5 rounded-xl border border-accent/30 bg-accent/10 px-3 py-2">
          <BookOpenText className="h-3.5 w-3.5 shrink-0 text-accent" />
          <span className="text-[11px] font-semibold text-accent">
            RAG 检索命中 {trace.rag_chunks ?? "?"} 段，来源：{(trace.rag_sources || []).join("、") || "知识库"}
          </span>
        </div>
      )}
    </div>
  );
}

/** Mini data card injected below AI bubbles when the trace shows a structured data flow. */
function InlineDataCard({ trace, context }: { trace: AgentTraceData; context: AgentContext }) {
  const flow = trace.selected_flow || "";

  if (/Order/i.test(flow) && context.order) {
    const o = context.order;
    return (
      <div className="message-enter ml-9 mt-1.5 overflow-hidden rounded-xl border border-accent/30 bg-surface shadow-card-inset">
        <div className="flex items-center gap-2 border-b border-accent/30 px-3 py-1.5">
          <Package className="h-3.5 w-3.5 shrink-0 text-accent" />
          <span className="text-[10px] font-black text-accent">订单快照</span>
          <span className="ml-auto font-mono text-[10px] text-tertiary">{o.order_id}</span>
        </div>
        <div className="grid grid-cols-3 divide-x divide-line text-center text-[10px]">
          <div className="px-2 py-1.5"><div className="font-bold text-secondary">{o.order_status}</div><div className="text-tertiary">订单</div></div>
          <div className="px-2 py-1.5"><div className="font-bold text-secondary">{o.shipping_status || "—"}</div><div className="text-tertiary">配送</div></div>
          <div className="px-2 py-1.5"><div className="font-bold text-accent">{o.total_amount}{o.currency}</div><div className="text-tertiary">金额</div></div>
        </div>
      </div>
    );
  }

  if (/Logistics/i.test(flow) && context.logistics) {
    const l = context.logistics;
    return (
      <div className="message-enter ml-9 mt-1.5 overflow-hidden rounded-xl border border-line bg-surface shadow-card-inset">
        <div className="flex items-center gap-2 border-b border-line bg-elevated px-3 py-1.5">
          <Truck className="h-3.5 w-3.5 shrink-0 text-accent" />
          <span className="text-[10px] font-black text-accent">物流快照</span>
          <span className="ml-auto font-mono text-[10px] text-tertiary">{l.tracking_no}</span>
        </div>
        <div className="px-3 py-2 text-[10px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded-full bg-accent/15 px-2 py-0.5 font-bold text-accent">{l.current_status}</span>
            <span className="text-secondary">{l.carrier_name}</span>
          </div>
          {l.current_location && (
            <p className="mt-1 flex items-center gap-1 text-secondary">
              <MapPin className="h-3 w-3 shrink-0" />
              {l.current_location}
            </p>
          )}
        </div>
      </div>
    );
  }

  if (/Refund/i.test(flow) && context.refund) {
    const r = context.refund;
    return (
      <div className="message-enter ml-9 mt-1.5 overflow-hidden rounded-xl border border-line bg-surface shadow-card-inset">
        <div className="flex items-center gap-2 border-b border-line bg-elevated px-3 py-1.5">
          <ReceiptText className="h-3.5 w-3.5 shrink-0 text-success" />
          <span className="text-[10px] font-black text-success">退款快照</span>
          <span className="ml-auto font-mono text-[10px] text-tertiary">{r.refund_id}</span>
        </div>
        <div className="grid grid-cols-2 divide-x divide-line text-center text-[10px]">
          <div className="px-2 py-1.5"><div className="font-bold text-secondary">{r.audit_status}</div><div className="text-tertiary">审核状态</div></div>
          <div className="px-2 py-1.5"><div className="font-bold text-success">{r.refund_status}</div><div className="text-tertiary">退款状态</div></div>
        </div>
      </div>
    );
  }

  return null;
}

// ── 订单状态样式映射 ────────────────────────────────────────────────────────────
function getOrderStatusStyle(status: string): { bg: string; text: string; dot: string } {
  if (/待支付/.test(status))                        return { bg: "bg-warning/10", text: "text-warning", dot: "bg-warning" };
  if (/已发货|运输中|待发货|已支付/.test(status))    return { bg: "bg-accent/10",    text: "text-accent",    dot: "bg-accent" };
  if (/售后|异常|破损|待售后/.test(status))          return { bg: "bg-danger/10", text: "text-danger", dot: "bg-danger" };
  if (/已完成/.test(status))                         return { bg: "bg-success/10", text: "text-success", dot: "bg-success" };
  return                                              { bg: "bg-elevated",    text: "text-secondary",   dot: "bg-tertiary" };
}

// ── 全宽订单选择面板（取代原来的小下拉框）─────────────────────────────────────
const FILTER_TABS = [
  { key: "all",     label: "全部" },
  { key: "active",  label: "进行中" },
  { key: "done",    label: "已完成" },
  { key: "problem", label: "有问题" },
] as const;
type FilterKey = (typeof FILTER_TABS)[number]["key"];

function OrderPickerSheet({
  orders,
  selectedOrder,
  pendingHint,
  onSelect,
  onClear,
  onClose,
}: {
  orders: Order[];
  selectedOrder: Order | null;
  pendingHint?: boolean;
  onSelect: (order: Order) => void;
  onClear: () => void;
  onClose: () => void;
}) {
  const [filter, setFilter] = useState<FilterKey>("all");

  const filtered = orders.filter((o) => {
    if (filter === "all")     return true;
    if (filter === "active")  return /已发货|运输中|待发货|已支付/.test(o.order_status);
    if (filter === "done")    return /已完成/.test(o.order_status);
    if (filter === "problem") return /售后|异常|破损|待支付|待售后/.test(o.order_status);
    return true;
  });

  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-base">
      {/* 顶部标题栏 */}
      <div className="flex shrink-0 items-center justify-between border-b border-line px-4 py-3">
        <div>
          <div className="text-sm font-black text-primary">选择订单</div>
          <div className="mt-0.5 text-[11px] text-tertiary">
            {pendingHint ? "选中订单后，我会立即针对它执行你刚点的操作" : "选中后，提问会自动聚焦到该订单"}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="grid h-8 w-8 place-items-center rounded-full text-tertiary hover:bg-elevated hover:text-secondary"
          aria-label="关闭"
        >✕</button>
      </div>

      {/* 状态筛选 chips */}
      <div className="flex shrink-0 gap-2 overflow-x-auto border-b border-line px-3 py-2">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setFilter(tab.key)}
            className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-bold transition ${
              filter === tab.key
                ? "bg-accent text-white shadow-card-inset"
                : "bg-elevated text-secondary hover:border hover:border-accent/40 hover:text-accent"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 订单卡片列表 */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {filtered.length === 0 && (
          <div className="mt-8 text-center text-sm text-tertiary">该分类暂无订单</div>
        )}
        {filtered.map((order) => {
          const isSelected = selectedOrder?.order_id === order.order_id;
          const style = getOrderStatusStyle(order.order_status);
          const productNames = (order.items || [])
            .map((i) => `${i.product_name}${i.quantity > 1 ? ` ×${i.quantity}` : ""}`)
            .join("、") || "暂无商品信息";

          return (
            <button
              key={order.order_id}
              type="button"
              onClick={() => { onSelect(order); onClose(); }}
              className={`group relative w-full rounded-2xl border-2 p-3.5 text-left transition active:scale-[0.98] ${
                isSelected
                  ? "border-accent bg-accent/10 shadow-[0_0_0_3px_rgba(99,102,241,0.15)]"
                  : "border-line bg-surface hover:border-accent/40 hover:bg-accent/5"
              }`}
            >
              {/* 已选中勾 */}
              {isSelected && (
                <span className="absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[10px] text-white">✓</span>
              )}

              {/* 第一行：订单号 + 状态 */}
              <div className="flex items-center gap-2">
                <span className="rounded bg-elevated px-1.5 py-0.5 font-mono text-[10px] font-bold text-secondary">
                  {order.order_id}
                </span>
                <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${style.bg} ${style.text}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                  {order.order_status}
                </span>
              </div>

              {/* 第二行：商品名（大字，最重要） */}
              <div className="mt-2 line-clamp-2 text-sm font-bold text-primary leading-snug">
                {productNames}
              </div>

              {/* 第三行：金额 + 配送状态 */}
              <div className="mt-1.5 flex items-center justify-between">
                <span className="text-[11px] text-tertiary">
                  {order.shipping_status && (
                    <span className="mr-2 inline-flex items-center gap-1">
                      <Package className="h-3 w-3" />
                      {order.shipping_status}
                    </span>
                  )}
                  {order.created_at && new Date(order.created_at).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })}
                </span>
                <span className="text-sm font-black text-accent">
                  ¥{order.total_amount}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* 底部：清除选择 */}
      {selectedOrder && (
        <div className="shrink-0 border-t border-line px-4 py-2.5">
          <button
            type="button"
            onClick={() => { onClear(); onClose(); }}
            className="w-full rounded-xl border border-line py-2 text-xs font-bold text-secondary transition hover:border-danger/40 hover:text-danger"
          >
            取消订单关联
          </button>
        </div>
      )}
    </div>
  );
}

// ── 投诉确认卡片：后端识别到投诉意图时，前端渲染此卡片替代纯文字确认 ────────
const COMPLAINT_TYPE_ICON: Record<string, LucideIcon> = {
  "物流问题": Truck,
  "质量问题": Wrench,
  "服务态度": Headset,
  "售后问题": RefreshCcw,
};

type PendingComplaint = {
  content: string;
  complaint_type: string;
  order_id: string;
};

function ComplaintConfirmCard({
  complaint,
  onConfirm,
  onCancel,
  disabled = false,
}: {
  complaint: PendingComplaint;
  onConfirm: () => void;
  onCancel: () => void;
  /** 上一轮回复还在生成时禁用按钮：否则点击显示"已提交"却实际没发出去 */
  disabled?: boolean;
}) {
  const [resolved, setResolved] = useState<"confirmed" | "cancelled" | null>(null);
  const TypeIcon = COMPLAINT_TYPE_ICON[complaint.complaint_type] ?? AlertTriangle;

  if (resolved === "confirmed") {
    return (
      <div className="ml-9 mt-2 flex items-center gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-xs font-semibold text-success">
        <span>✓</span><span>已提交投诉，正在处理中</span>
      </div>
    );
  }
  if (resolved === "cancelled") {
    return (
      <div className="ml-9 mt-2 flex items-center gap-2 rounded-xl bg-elevated px-3 py-2 text-xs text-tertiary">
        <span>✕</span><span>已取消，不会提交这条投诉</span>
      </div>
    );
  }

  return (
    <div className="message-enter ml-9 mt-2 overflow-hidden rounded-xl border border-line bg-surface shadow-card-inset">
      {/* 卡片头部 */}
      <div className="flex items-center gap-2 bg-accent-gradient px-4 py-2.5">
        <TypeIcon className="h-4 w-4 shrink-0 text-white" />
        <span className="text-xs font-black text-white">投诉确认</span>
        <span className="ml-auto rounded-full bg-white/25 px-2 py-0.5 text-[10px] font-bold text-white">
          {complaint.complaint_type}
        </span>
      </div>
      {/* 关联订单 */}
      {complaint.order_id && (
        <div className="flex items-center gap-2 border-b border-line bg-elevated px-4 py-2">
          <Package className="h-3.5 w-3.5 shrink-0 text-accent" />
          <span className="font-mono text-[11px] font-bold text-accent">{complaint.order_id}</span>
          <span className="text-[10px] text-tertiary">关联订单</span>
        </div>
      )}
      {/* 投诉内容 */}
      <div className="px-4 py-3">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-tertiary">投诉描述</div>
        <p className="text-xs leading-relaxed text-primary">{complaint.content}</p>
      </div>
      {/* 操作按钮 */}
      <div className="flex gap-2 border-t border-line px-4 py-3">
        <button
          type="button"
          disabled={disabled}
          onClick={() => { setResolved("confirmed"); onConfirm(); }}
          className="flex-1 rounded-xl bg-accent-gradient py-2 text-xs font-black text-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
        >
          ✓ 确认提交投诉
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => { setResolved("cancelled"); onCancel(); }}
          className="rounded-xl border border-line px-4 py-2 text-xs font-bold text-secondary transition hover:border-danger/40 hover:text-danger disabled:cursor-not-allowed disabled:opacity-50"
        >
          取消
        </button>
      </div>
    </div>
  );
}

// ── 退款确认卡片：后端收集退款原因后，前端渲染此卡片替代纯文字确认 ──────────
type PendingRefund = {
  order_id: string;
  reason: string;
  amount?: string;
};

function RefundConfirmCard({
  refund,
  snapshot,
  onConfirm,
  onCancel,
  disabled = false,
}: {
  refund: PendingRefund;
  snapshot: ServiceSnapshot;
  onConfirm: () => void;
  onCancel: () => void;
  /** 上一轮回复还在生成时禁用按钮：否则点击显示"已提交"却实际没发出去 */
  disabled?: boolean;
}) {
  const [resolved, setResolved] = useState<"confirmed" | "cancelled" | null>(null);

  // 从 snapshot 里找到对应订单的金额和商品名
  const order = refund.order_id
    ? snapshot.orders.find((o) => o.order_id === refund.order_id)
    : null;
  const productNames = (order?.items || [])
    .map((i) => `${i.product_name}${i.quantity > 1 ? ` ×${i.quantity}` : ""}`)
    .join("、") || "—";
  const amount = order?.total_amount ?? refund.amount ?? "";

  if (resolved === "confirmed") {
    return (
      <div className="ml-9 mt-2 flex items-center gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-xs font-semibold text-success">
        <span>✓</span><span>退款申请已提交，审核结果将在 1-3 个工作日内通知</span>
      </div>
    );
  }
  if (resolved === "cancelled") {
    return (
      <div className="ml-9 mt-2 flex items-center gap-2 rounded-xl bg-elevated px-3 py-2 text-xs text-tertiary">
        <span>✕</span><span>已取消，退款申请未提交</span>
      </div>
    );
  }

  return (
    <div className="message-enter ml-9 mt-2 overflow-hidden rounded-xl border border-line bg-surface shadow-card-inset">
      {/* 卡片头部 */}
      <div className="flex items-center gap-2 bg-accent-gradient px-4 py-2.5">
        <ReceiptText className="h-4 w-4 shrink-0 text-white" />
        <span className="text-xs font-black text-white">退款确认</span>
        {amount && (
          <span className="ml-auto rounded-full bg-white/25 px-2 py-0.5 text-[11px] font-black text-white">
            ¥{amount}
          </span>
        )}
      </div>

      {/* 订单信息 */}
      {order && (
        <div className="border-b border-line bg-elevated px-4 py-2">
          <div className="flex items-center gap-2">
            <Package className="h-3.5 w-3.5 shrink-0 text-success" />
            <div className="min-w-0">
              <div className="font-mono text-[10px] font-bold text-success">{order.order_id}</div>
              <div className="truncate text-[11px] font-semibold text-secondary">{productNames}</div>
            </div>
          </div>
        </div>
      )}

      {/* 退款原因 */}
      <div className="px-4 py-3">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-tertiary">退款原因</div>
        <p className="text-xs leading-relaxed text-primary">{refund.reason}</p>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-2 border-t border-line px-4 py-3">
        <button
          type="button"
          disabled={disabled}
          onClick={() => { setResolved("confirmed"); onConfirm(); }}
          className="flex-1 rounded-xl bg-accent-gradient py-2 text-xs font-black text-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
        >
          ✓ 确认申请退款
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => { setResolved("cancelled"); onCancel(); }}
          className="rounded-xl border border-line px-4 py-2 text-xs font-bold text-secondary transition hover:border-danger/40 hover:text-danger disabled:cursor-not-allowed disabled:opacity-50"
        >
          取消
        </button>
      </div>
    </div>
  );
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
  // 用户点了"需要订单"的卡片但还没选单 → 暂存该卡片 prompt，选完单后自动执行
  const [pendingScenarioPrompt, setPendingScenarioPrompt] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null);
  const [loadingCapability, setLoadingCapability] = useState<AgentCapability>("summary");

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

  // Ctrl/Cmd+K opens the assistant; Esc closes it — standard AI-product keyboard pattern.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
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

  // orderOverride: 显式传入订单，绕过 selectedOrder 的异步 setState 竞态
  // （用户在选单窗口点选订单后立即执行时需要）
  const send = useCallback(async (content: string, orderOverride?: Order) => {
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

    // 先插入空的 AI 占位气泡，随 SSE delta 逐段增长（真流式）
    const assistantId = generateMessageId();
    const placeholder: Message = {
      id: assistantId,
      role: "assistant",
      type: "text",
      content: "",
      timestamp: new Date().toISOString(),
      status: "completed",
    };

    try {
      const capability = detectCapability(trimmed);
      setLoadingCapability(capability);
      const targetOrder = orderOverride || selectedOrder || chooseTargetOrder(context, snapshot, capability);
      const history = messages.map((message) => ({
        role: message.role,
        content: message.content,
      }));
      const request = {
        message: buildContextPrompt(context, user, snapshot, trimmed, capability, targetOrder),
        history,
        session_id: sessionId,
      };

      setMessages((prev) => [...prev, placeholder]);
      setStreamingMsgId(assistantId);
      let acc = "";
      let result: ChatResult;
      try {
        result = await sendChatMessageStream(request, {
          onDelta: (text) => {
            acc += text;
            setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, content: acc } : m)));
          },
        });
      } catch {
        // 流式失败（旧后端/网络中断）→ 回退整包接口，占位气泡被最终消息替换
        result = await sendChatMessage(request);
      }

      // 把本轮 trace 附到该条 AI 消息上，便于在气泡下展示"AI 调了哪个 Agent/工具"，
      // 让用户直观看到助手是"真的执行了动作"而非只是回话。
      // done 事件携带的是清洗后的完整文本，可能与增量累积略有差异，以它为准。
      const assistantMessage: Message = {
        ...result.message,
        content: result.message.content || acc,
        ...(result.trace ? { metadata: { ...result.message.metadata, trace: result.trace } } : {}),
      };
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? assistantMessage : m)));
      setTrace(result.trace);
      commerceApi.agentTrace().then(setTraceStore).catch(() => undefined);
    } catch (err) {
      // 彻底失败：移除占位气泡并提示
      setMessages((prev) => prev.filter((m) => m.id !== assistantId));
      setError(err instanceof Error ? err.message : "发送失败，请稍后重试");
    } finally {
      setStreamingMsgId(null);
      setLoading(false);
    }
  }, [context, loading, messages, selectedOrder, sessionId, snapshot, user]);

  // Demo 场景卡片点击：
  // - 需要订单 + 未选单 + 有订单可选 → 暂存 prompt，弹订单选择窗口
  // - 其余情况 → 直接执行（已选单会自动带上）
  const handleScenarioClick = useCallback((sc: DemoScenario) => {
    if (sc.requiresOrder && !selectedOrder && snapshot.orders.length > 0) {
      setPendingScenarioPrompt(sc.prompt);
      setShowOrderPicker(true);
      return;
    }
    void send(sc.prompt);
  }, [selectedOrder, snapshot.orders.length, send]);

  // 在订单选择窗口里选中订单：绑定订单 + 若有待执行卡片则立即执行
  const handlePickOrder = useCallback((order: Order) => {
    setSelectedOrder(order);
    setShowOrderPicker(false);
    if (pendingScenarioPrompt) {
      const prompt = pendingScenarioPrompt;
      setPendingScenarioPrompt(null);
      void send(prompt, order);   // 显式传订单，绕过 setState 竞态
    }
  }, [pendingScenarioPrompt, send]);

  const openInsight = useCallback((insight: AssistantInsight) => {
    setAssistantView("chat");
    setOpen(true);
    void send(insight.action_prompt);
  }, [send]);

  const dismissEvent = useCallback((event: AssistantEvent) => {
    // 乐观隐藏 + 落库标记已读：后端按 (user_id, dedup_key) 去重，已读后同一情形
    // 不会再生成新事件，刷新/重开面板也不会重现旧的演示提醒。
    setDismissedEvents((items) => Array.from(new Set([...items, event.event_id])));
    commerceApi.markAgentEventRead(event.event_id).catch(() => undefined);
  }, []);

  const openEvent = useCallback((event: AssistantEvent) => {
    setOpen(true);
    setAssistantView("chat");
    dismissEvent(event);
    void send(event.assistant_prompt);
  }, [dismissEvent, send]);

  const renderEventBanner = () => visibleEvents.length > 0 && (
    <div className="rounded-2xl border border-warning/30 bg-warning/10 p-3 shadow-card-inset">
      <div className="flex items-start gap-3">
        <div className="event-icon-pulse grid h-9 w-9 shrink-0 place-items-center rounded-full bg-warning text-sm font-black text-base">!</div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-black text-primary">{visibleEvents[0].title}</div>
          <div className="mt-1 text-xs leading-5 text-secondary">{visibleEvents[0].description}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" onClick={() => openEvent(visibleEvents[0])} className="rounded-full bg-accent-gradient px-3 py-1.5 text-xs font-bold text-white shadow-accent-glow transition hover:-translate-y-0.5">立即处理</button>
            <button type="button" onClick={() => dismissEvent(visibleEvents[0])} className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-bold text-secondary transition hover:border-accent/40 hover:text-accent">稍后再说</button>
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
          <span className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-bold text-accent shadow-card-inset">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />{domain}
          </span>
        )}
        {successTools.map((tc, index) => (
          <span key={`${tc.tool_name}-${index}`} className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-bold text-accent shadow-card-inset">
            <span className="text-[10px]">✓</span>{toolLabel(tc.tool_name)}
          </span>
        ))}
        {typeof msgTrace.duration_ms === "number" && msgTrace.duration_ms > 0 && (
          <span className="text-[10px] font-medium text-tertiary">{(msgTrace.duration_ms / 1000).toFixed(1)}s</span>
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
          {user && !insights && <SkeletonInsights />}
          {user && insights && (
            <section className="rounded-2xl border border-accent/30 bg-surface p-3.5 shadow-card-inset">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-black text-primary"><ClipboardList className="h-3.5 w-3.5 text-accent" />你的服务概览</div>
                <button type="button" onClick={() => send("帮我总结当前订单、物流、退款和投诉情况。")} className="rounded-full bg-accent/15 px-2.5 py-1 text-[10px] font-bold text-accent transition hover:bg-accent/25">一键总结</button>
              </div>
              <div className="mt-2.5 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-xl bg-accent/10 p-2 shadow-card-inset"><div className="text-xl font-black tabular-nums text-accent">{insights.counts.active_orders}</div><div className="text-[10px] text-secondary">进行中订单</div></div>
                <div className="rounded-xl bg-warning/10 p-2 shadow-card-inset"><div className="text-xl font-black tabular-nums text-warning">{insights.counts.open_refunds}</div><div className="text-[10px] text-secondary">待跟进退款</div></div>
                <div className="rounded-xl bg-danger/10 p-2 shadow-card-inset"><div className="text-xl font-black tabular-nums text-danger">{insights.counts.open_complaints}</div><div className="text-[10px] text-secondary">未结投诉</div></div>
              </div>
              {visibleInsights.length > 0 && (
                <div className="mt-2.5 grid gap-1">
                  {visibleInsights.slice(0, 2).map((insight) => (
                    <button key={insight.insight_id} type="button" onClick={() => openInsight(insight)} className="flex items-center justify-between gap-2 rounded-xl bg-elevated px-2.5 py-2 text-left shadow-card-inset transition hover:bg-accent/10">
                      <span className="min-w-0 flex-1 truncate text-[11px] font-bold text-secondary">{insight.title}</span>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${insight.severity === "urgent" ? "bg-danger/15 text-danger" : insight.severity === "high" ? "bg-warning/15 text-warning" : "bg-surface text-secondary"}`}>{insight.action_label}</span>
                    </button>
                  ))}
                </div>
              )}
            </section>
          )}
          <section className="rounded-2xl border border-accent/30 bg-surface p-4 shadow-card-inset">
            <div className="text-sm font-black text-primary">今天帮你处理什么？</div>
            <p className="mt-1 text-[11px] text-secondary">
              {selectedOrder
                ? `已锁定订单 ${selectedOrder.order_id}，点查订单/物流/退款/投诉将直接针对它处理。`
                : "点查订单、追物流、退款、投诉会先让你选订单，其余场景直接执行。"}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {DEMO_SCENARIOS.map((sc) => (
                <button
                  type="button"
                  key={sc.label}
                  onClick={() => handleScenarioClick(sc)}
                  className="group flex items-start gap-2 rounded-xl border border-line bg-elevated px-2.5 py-2.5 text-left transition hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-accent-glow"
                >
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent transition group-hover:bg-accent/20">
                    <sc.icon className="h-3.5 w-3.5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-xs font-black text-primary">{sc.label}</span>
                    <span className="block text-[10px] leading-4 text-secondary">{sc.desc}</span>
                  </span>
                </button>
              ))}
            </div>
          </section>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-xl border border-line bg-surface px-3 py-2 text-[11px] text-secondary shadow-card-inset"><div className="flex items-center gap-1.5"><span className="inline-flex h-1.5 w-1.5 rounded-full bg-success" />{user ? `${ASSISTANT_NAME}正在结合你的服务上下文回复` : `${ASSISTANT_NAME}访客模式`}</div><button type="button" onClick={resetConversation} className="rounded-full bg-accent/15 px-2.5 py-1 text-[10px] font-bold text-accent transition hover:bg-accent/25">重新开始</button></div>
          {messages.map((message) => { const isUser = message.role === "user"; const msgTrace = message.metadata?.trace as AgentTraceData | undefined; return (<div key={message.id} className={`message-enter flex ${isUser ? "justify-end" : "justify-start"}`}><div className={`max-w-[85%] ${isUser ? "items-end" : "items-start"}`}><div className={`flex items-end gap-1.5 ${isUser ? "flex-row-reverse" : "flex-row"}`}>{!isUser && (<div className="relative h-7 w-7 shrink-0 overflow-hidden rounded-full bg-accent/15 shadow-sm"><img src="/assistant/ai-assistant-avatar.png" alt="" className="assistant-avatar-3d absolute inset-0 h-full w-full object-cover object-center" /></div>)}<div className={`break-words rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed shadow-sm ${isUser ? "whitespace-pre-wrap rounded-br-sm bg-accent text-white" : "rounded-bl-sm border-t border-r border-b border-line border-l-4 bg-surface text-primary"}`} style={!isUser && msgTrace ? { borderLeftColor: getFlowAccentColor(msgTrace.selected_flow) } : undefined}>{isUser ? message.content : <AiMessageContent content={message.content} streaming={streamingMsgId === message.id} />}</div></div>{!isUser && msgTrace && renderAgentChip(msgTrace)}{!isUser && msgTrace && <InlineDataCard trace={msgTrace} context={context} />}{!isUser && (() => { const pc = message.metadata?.pending_complaint as PendingComplaint | undefined; return pc ? <ComplaintConfirmCard complaint={pc} onConfirm={() => send("确认提交投诉")} onCancel={() => send("取消，不提交")} disabled={loading} /> : null; })()}{!isUser && (() => { const pr = message.metadata?.pending_refund as PendingRefund | undefined; return pr ? <RefundConfirmCard refund={pr} snapshot={snapshot} onConfirm={() => send("确认申请退款")} onCancel={() => send("取消，不申请")} disabled={loading} /> : null; })()}{!isUser && <MessageFeedback msgId={message.id} />}<div className={`mt-0.5 px-9 text-[10px] text-tertiary ${isUser ? "text-right" : "text-left"}`}>{formatTime(message.timestamp)}</div></div></div>); })}
          {loading && <SmartLoadingIndicator capability={loadingCapability} />}
          {error && <div className="rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">{error}</div>}
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );

  const renderGuestWelcome = () => (
    <div className="flex flex-col items-center">
      {/* Hero section — 数字人自我介绍 */}
      <div className="relative mb-4 mt-2 flex flex-col items-center">
        <div className="relative h-28 w-28">
          <span className="assistant-aura absolute inset-0 rounded-full bg-accent/40" />
          <div className="relative h-28 w-28 overflow-hidden rounded-full ring-4 ring-elevated">
            <div className="absolute inset-0 rounded-full bg-elevated opacity-80" />
            <img src="/assistant/ai-assistant-avatar.png" alt={ASSISTANT_NAME} className="assistant-avatar-3d relative h-full w-full object-cover object-center" />
          </div>
          <span className="absolute bottom-1.5 right-1.5 h-4 w-4 rounded-full border-2 border-base bg-success">
            <span className="absolute inset-0 animate-ping rounded-full bg-success opacity-75" />
          </span>
        </div>
        <div className="mt-3 flex items-center gap-1.5">
          <h2 className="text-lg font-black text-primary">嗨，我是{ASSISTANT_NAME}</h2>
          <span className="rounded-full bg-accent px-2 py-0.5 text-[10px] font-bold text-white">AI</span>
        </div>
        <p className="mt-1 text-center text-xs text-secondary">{ASSISTANT_TAGLINE}</p>
        <div className="mt-3 flex gap-2">
          <Link href="/register" className="rounded-full border border-line px-4 py-1.5 text-xs font-bold text-secondary transition hover:border-accent/60 hover:text-accent">注册</Link>
          <Link href="/login" className="rounded-full bg-accent-gradient px-4 py-1.5 text-xs font-bold text-white shadow-accent-glow">登录</Link>
        </div>
      </div>

      {/* Demo hint banner：让第一次用/演示的人立刻知道怎么进入完整能力 */}
      <div className="mb-4 w-full rounded-2xl border border-accent/30 bg-elevated p-3.5 shadow-card-inset">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-xs font-black text-primary">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-accent" />
              想看完整能力？用演示账号登录
            </div>
            <p className="mt-1 text-[11px] leading-4 text-secondary">登录后可查真实订单、物流、退款、投诉，并让我直接替你执行。</p>
            <p className="mt-1.5 text-[10px] text-tertiary">演示账号见项目 README</p>
          </div>
          <KeyRound className="h-6 w-6 shrink-0 text-accent" />
        </div>
      </div>

      {/* Recommendations */}
      <div className="w-full">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[11px] font-bold text-secondary">为你推荐：</span>
          <button type="button" onClick={() => setSuggestionPage((p) => p + 1)} className="flex items-center gap-1 text-[11px] font-bold text-tertiary transition hover:text-accent">换一换<RefreshCcw className="h-3 w-3" /></button>
        </div>
        <div className="grid gap-1.5">
          {suggestions.map((item) => (
            <button key={item} type="button" onClick={() => send(item)} className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2.5 text-left transition hover:border-accent/60 hover:bg-accent/10">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-accent" />
              <span className="text-xs font-bold text-secondary">{item}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );

  const renderTracePage = () => (
    <div className="space-y-3">
      {/* ── 执行时间轴（主体） ── */}
      <section className="overflow-hidden rounded-2xl border border-accent/30 bg-surface shadow-card-inset">
        <div className="border-b border-line px-4 py-3">
          <div className="text-sm font-black text-primary">Agent 执行链</div>
          <p className="mt-0.5 text-[11px] text-secondary">意图识别 → Flow 路由 → 工具调用 → 耗时</p>
        </div>
        <div className="p-3">
          <AgentTimeline trace={trace} />
        </div>
      </section>
      {/* ── DebugPanel 作为折叠详情 ── */}
      <details className="group overflow-hidden rounded-2xl border border-line bg-surface shadow-card-inset">
        <summary className="flex cursor-pointer select-none items-center justify-between px-4 py-3 text-xs font-black text-secondary hover:bg-elevated">
          <span>详细调试数据</span>
          <span className="text-tertiary transition group-open:rotate-180">▾</span>
        </summary>
        <div className="border-t border-line px-3 pb-3 pt-2">
          <DebugPanel trace={trace} alwaysVisible />
        </div>
      </details>
      <section className="rounded-2xl border border-line bg-surface p-3 shadow-card-inset"><div className="mb-2 text-xs font-black text-primary">最近工具审计</div>{traceStore.audits.slice(0, 3).map((audit, index) => (<pre key={index} className="mb-1.5 max-h-24 overflow-hidden rounded-xl bg-elevated p-2 text-[10px] text-secondary">{JSON.stringify(audit, null, 2).slice(0, 200)}</pre>))}{traceStore.audits.length === 0 && <div className="rounded-xl bg-elevated p-3 text-[11px] text-tertiary">暂无记录</div>}</section>
      <section className="rounded-2xl border border-line bg-surface p-3 shadow-card-inset"><div className="mb-2 text-xs font-black text-primary">工作流运行</div>{traceStore.workflows.slice(0, 3).map((workflow, index) => (<pre key={index} className="mb-1.5 max-h-24 overflow-hidden rounded-xl bg-elevated p-2 text-[10px] text-secondary">{JSON.stringify(workflow, null, 2).slice(0, 200)}</pre>))}{traceStore.workflows.length === 0 && <div className="rounded-xl bg-elevated p-3 text-[11px] text-tertiary">暂无记录</div>}</section>
    </div>
  );

  return (
    <>
      {!open && (
        <div className="fixed right-3 top-1/2 z-50 flex -translate-y-1/2 flex-col items-end gap-2 sm:right-5">
          {visibleEvents.length > 0 && (
            <button type="button" onClick={() => openEvent(visibleEvents[0])} className="mr-2 max-w-[220px] rounded-2xl border border-warning/30 bg-elevated px-4 py-3 text-left shadow-[0_18px_48px_rgba(0,0,0,0.45)] backdrop-blur transition hover:-translate-x-1"><div className="text-xs font-black text-warning">新提醒</div><div className="mt-1 line-clamp-2 text-sm font-bold leading-5 text-primary">{visibleEvents[0].title}</div><div className="mt-1 line-clamp-2 text-xs leading-4 text-secondary">{visibleEvents[0].description}</div></button>
          )}
          <button type="button" onClick={() => setOpen(true)} className="assistant-side-float group relative h-[188px] w-[132px] overflow-visible rounded-l-[36px] rounded-r-2xl border border-accent/30 bg-elevated/95 shadow-[0_18px_48px_rgba(0,0,0,0.5)] backdrop-blur transition hover:-translate-x-1 hover:shadow-accent-glow" aria-label="AI assistant"><span className="assistant-aura absolute left-1/2 top-6 h-28 w-28 -translate-x-1/2 rounded-full bg-accent/30" />{visibleEvents.length > 0 && <span className="badge-pop absolute right-2 top-2 grid min-w-[20px] place-items-center rounded-full bg-danger px-1.5 py-0.5 text-[10px] font-bold text-white shadow-md">{visibleEvents.length}</span>}<span className="absolute -left-[112px] top-10 hidden rounded-full border border-line bg-elevated px-3 py-1.5 text-xs font-semibold text-secondary shadow-card-inset transition group-hover:-translate-x-1 md:block">{ASSISTANT_NAME}，有事找我</span><img src="/assistant/ai-assistant-avatar.png" alt={ASSISTANT_NAME} className="assistant-avatar-float absolute -top-12 left-1/2 h-44 w-44 -translate-x-1/2 object-contain" /><span className="absolute bottom-9 left-1/2 w-[88px] -translate-x-1/2 rounded-full bg-accent px-2 py-1 text-[13px] font-black text-white shadow-sm">{ASSISTANT_NAME}</span><span className="absolute bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 text-[11px] font-semibold text-success"><span className="h-1.5 w-1.5 rounded-full bg-success" />在线</span></button>
        </div>
      )}

      {open && (
        <section className={`fixed z-50 flex overflow-hidden border border-line bg-base shadow-[0_28px_90px_rgba(0,0,0,0.6)] transition-all duration-300 ${expanded ? "bottom-3 right-3 left-3 top-3 rounded-[20px] sm:bottom-4 sm:right-4 sm:left-4 sm:top-4" : "bottom-5 right-5 top-[60px] w-[25vw] min-w-[380px] max-w-[560px] max-h-[calc(100vh-80px)] rounded-2xl max-sm:left-3 max-sm:right-3 max-sm:top-3 max-sm:bottom-3 max-sm:w-auto max-sm:min-w-0 max-sm:max-w-none max-sm:max-h-none assistant-panel-mobile"}`}>
          {/* Sidebar - only in expanded + logged in */}
          {user && <aside className={`hidden shrink-0 flex-col border-r border-line bg-surface p-5 ${expanded ? "w-64 lg:flex" : "hidden"}`}>
            <div className="flex items-center gap-3"><div className="relative h-16 w-16 shrink-0"><span className="assistant-aura absolute inset-0 rounded-2xl bg-accent/40" /><div className="relative h-16 w-16 overflow-hidden rounded-2xl bg-elevated shadow-card-inset ring-2 ring-line"><img src="/assistant/ai-assistant-avatar.png" alt={ASSISTANT_NAME} className="assistant-avatar-3d absolute inset-0 h-full w-full object-cover object-center" /></div><span className="absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full border-2 border-surface bg-success"><span className="absolute inset-0 animate-ping rounded-full bg-success opacity-75" /></span></div><div><div className="flex items-center gap-1.5"><div className="text-base font-black text-primary">{ASSISTANT_NAME}</div><span className="rounded-full bg-accent px-1.5 py-0.5 text-[9px] font-bold text-white">AI</span></div><div className="mt-1 text-xs font-semibold text-success">● 在线服务中</div><div className="mt-0.5 text-[10px] text-tertiary">{ASSISTANT_TITLE}</div></div></div>
            <nav className="mt-8 grid gap-2">{(["chat", "trace"] as AssistantView[]).map((view) => (<button key={view} type="button" onClick={() => setAssistantView(view)} className={`rounded-2xl px-4 py-3 text-left text-sm font-black transition ${assistantView === view ? "bg-accent-gradient text-white shadow-accent-glow" : "text-secondary hover:bg-elevated hover:text-primary"}`}>{view === "chat" ? "AI 对话" : "Agent 面板"}</button>))}</nav>
            <div className="mt-auto rounded-2xl bg-elevated p-4 text-xs leading-5 text-secondary shadow-card-inset">AI 回复仅供参考，订单和售后以平台记录为准。</div>
          </aside>}

          <div className="relative flex min-w-0 flex-1 flex-col">
            {/* Hero 大横幅直接充当面板头部，承载数字人形象 + 控制按钮 */}
            <AssistantHeroBanner
              userName={user?.full_name}
              viewLabel={user && assistantView === "trace" ? "Agent 面板" : undefined}
              onReset={resetConversation}
              onToggleExpand={() => setExpanded((v) => !v)}
              onClose={() => setOpen(false)}
              expanded={expanded}
              showReset={!!user}
            />

            {/* Tab bar - only when logged in */}
            {user && <div className="flex gap-1.5 overflow-x-auto border-b border-line bg-surface px-3 py-2">{(["chat", "trace"] as AssistantView[]).map((view) => (<button key={view} type="button" onClick={() => setAssistantView(view)} className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-bold transition ${assistantView === view ? "bg-accent text-white shadow-card-inset" : "bg-elevated text-secondary hover:text-accent"}`}>{view === "chat" ? "对话" : "Agent 面板"}</button>))}</div>}

            {/* 订单选择面板：全宽滑出，绝对覆盖在聊天区上方 */}
            {showOrderPicker && snapshot.orders.length > 0 && (
              <OrderPickerSheet
                orders={snapshot.orders}
                selectedOrder={selectedOrder}
                pendingHint={pendingScenarioPrompt !== null}
                onSelect={handlePickOrder}
                onClear={() => { setSelectedOrder(null); setShowOrderPicker(false); setPendingScenarioPrompt(null); }}
                onClose={() => { setShowOrderPicker(false); setPendingScenarioPrompt(null); }}
              />
            )}

            {/* Main content */}
            <main className="chat-scrollbar flex-1 overflow-y-auto bg-base p-3 sm:p-4">
              {user ? (
                <>{assistantView === "chat" && renderChatPage()}{assistantView === "trace" && renderTracePage()}</>
              ) : (
                messages.length > 0 ? renderChatPage() : renderGuestWelcome()
              )}
            </main>

            {/* Footer with input - always show for guest chat or logged-in chat view */}
            {(user ? assistantView === "chat" : true) && <footer className="chat-footer border-t border-line bg-surface p-3">{selectedOrder && (<div className="mb-2 flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/10 px-3 py-2"><Package className="h-3.5 w-3.5 shrink-0 text-accent" /><span className="min-w-0 flex-1"><div className="font-mono text-[10px] font-bold text-accent">{selectedOrder.order_id}</div><div className="truncate text-[11px] font-semibold text-secondary">{(selectedOrder.items || []).map((i) => `${i.product_name}${i.quantity > 1 ? ` ×${i.quantity}` : ""}`).join("、") || "暂无商品"}</div></span><button type="button" onClick={() => setSelectedOrder(null)} className="shrink-0 rounded-full p-1 text-tertiary hover:bg-danger/10 hover:text-danger" aria-label="取消关联">✕</button></div>)}<div className="flex items-end gap-2 rounded-xl border border-line bg-elevated p-1.5 transition focus-within:border-accent/60 focus-within:shadow-[0_0_0_3px_rgba(99,102,241,0.15)]">{user && snapshot.orders.length > 0 && (<button type="button" onClick={() => setShowOrderPicker((v) => !v)} className={`inline-flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-2 text-[11px] font-bold transition ${showOrderPicker ? "bg-accent/15 text-accent" : "text-tertiary hover:bg-surface hover:text-secondary"}`} aria-label="选择订单"><ClipboardList className="h-3.5 w-3.5" /><span>选单</span></button>)}<textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(input); } }} rows={1} placeholder={user ? (selectedOrder ? `针对 ${selectedOrder.order_id.slice(-6)} 提问...` : "问订单、物流、退款都可以") : "请描述你遇到的问题"} className="max-h-24 min-h-[36px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-xs outline-none placeholder:text-tertiary" /><button type="button" onClick={() => send(input)} disabled={!input.trim() || loading} className="h-9 shrink-0 rounded-lg bg-accent px-3 text-xs font-bold text-white shadow-accent-glow transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0" aria-label="发送">发送</button></div></footer>}
          </div>
        </section>
      )}
    </>
  );
}
