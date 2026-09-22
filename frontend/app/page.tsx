"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BookOpenText,
  Headset,
  Megaphone,
  PackageSearch,
  ReceiptText,
  Sparkles,
  Truck,
} from "lucide-react";
import SiteShell from "@/components/platform/SiteShell";
import { commerceApi, getStoredUserId, Product } from "@/services/commerce";
import { formatCurrency, productImage } from "@/services/format";
import { fetchMetrics, type MetricsData } from "@/services/metrics";

const OPEN_EVENT = "commerce:open-agent";

/** 数字滚动动画（requestAnimationFrame 纯 JS，尊重 prefers-reduced-motion） */
function useCountUp(target: number | null, duration = 1100) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    if (target == null) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplay(target);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      setDisplay(Math.round(target * (1 - Math.pow(1 - progress, 3))));
      if (progress < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return display;
}

function openAgent(userId?: string) {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: { user_id: userId } }));
}

export default function Home() {
  const [stats, setStats] = useState<{
    products: { count: number };
    orders: { count: number };
    refunds: { count: number };
    complaints: { count: number };
  } | null>(null);
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [userId, setUserId] = useState("");

  useEffect(() => {
    setUserId(getStoredUserId());
    commerceApi.dashboard().then(setStats).catch(() => setStats(null));
    fetchMetrics().then(setMetrics).catch(() => setMetrics(null));
    commerceApi.products("", "").then((items) => setProducts(items.slice(0, 8))).catch(() => setProducts([]));
  }, []);

  const orderCount = stats?.orders.count ?? null;
  const productCount = stats?.products.count ?? null;
  const refundCount = stats?.refunds.count ?? null;
  const complaintCount = stats?.complaints.count ?? null;
  const toolRate = metrics?.tool_calls.overall_success_rate ?? null;

  const statItems = useMemo(
    () => [
      { label: "在库商品", value: productCount },
      { label: "真实订单", value: orderCount },
      { label: "退款工单", value: refundCount },
      { label: "投诉工单", value: complaintCount },
    ],
    [productCount, orderCount, refundCount, complaintCount],
  );

  const toolBars = useMemo(() => {
    if (!metrics) return [];
    const labels: Record<string, string> = {
      query_order: "查订单",
      logistics_query: "查物流",
      refund_apply: "退款",
      knowledge_search: "知识检索",
      complaint_lookup: "查投诉",
    };
    const byTool = metrics.tool_calls.by_tool || {};
    const successByTool = metrics.tool_calls.success_by_tool || {};
    return Object.keys(labels)
      .filter((name) => (byTool[name] || 0) > 0)
      .slice(0, 5)
      .map((name) => {
        const total = byTool[name] || 0;
        const success = successByTool[name] || 0;
        return {
          label: labels[name],
          rate: total > 0 ? Math.round((success / total) * 100) : 0,
          count: total,
        };
      });
  }, [metrics]);

  const capabilities = useMemo(
    () => [
      {
        icon: PackageSearch,
        title: "查订单",
        desc: "实时核对订单、支付与商品明细，一句话直达真实数据库。",
        accent: orderCount != null ? `${orderCount} 单真实订单在库` : "订单数据实时可读",
        span: "md:col-span-2",
      },
      {
        icon: Truck,
        title: "追物流",
        desc: "轨迹、时效、异常件一站追踪，物流状态张口即得。",
        accent: "轨迹事件实时可读",
        span: "",
      },
      {
        icon: ReceiptText,
        title: "退款售后",
        desc: "七天无理由、到账时效、拒绝场景，规则内一步办妥。",
        accent: refundCount != null ? `${refundCount} 张退款工单已处理` : "退款流程全链路可查",
        span: "",
      },
      {
        icon: Megaphone,
        title: "投诉升级",
        desc: "受理、分类、升级、主管跟进，复杂问题不漏一环。",
        accent: complaintCount != null ? `${complaintCount} 张投诉工单在跟进` : "投诉升级通道在线",
        span: "",
      },
      {
        icon: Headset,
        title: "转人工",
        desc: "超出规则的问题无缝转接人工坐席，排队状态实时可查。",
        accent: "人工通道实时排队",
        span: "",
      },
      {
        icon: BookOpenText,
        title: "知识问答",
        desc: "退款、物流、优惠券、商品参数，10 类企业知识即问即答。",
        accent: metrics ? `${metrics.tool_calls.by_tool?.knowledge_search ?? 0} 次知识检索真实发生` : "企业知识库已索引",
        span: "md:col-span-3",
      },
    ],
    [orderCount, refundCount, complaintCount, metrics],
  );

  return (
    <SiteShell>
      {/* ══ Hero 区：AI 能力为视觉 C 位 ══ */}
      <section className="rise-in relative overflow-hidden rounded-2xl border border-line bg-surface">
        <div className="hero-glow pointer-events-none absolute -top-40 left-1/4 h-80 w-[42rem] rounded-full bg-accent/15 blur-3xl" />
        <div className="relative grid gap-8 p-6 md:p-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-bold text-accent">
              <Sparkles className="h-3.5 w-3.5" />
              小易 AI 电商助手 · 任务执行型 Agent
            </div>
            <h1 className="mt-5 max-w-2xl text-4xl font-black leading-tight tracking-tight text-primary md:text-6xl">
              一句话，AI 帮你把售后办完
            </h1>
            <p className="mt-5 max-w-xl text-sm leading-7 text-secondary md:text-base">
              查订单、追物流、退款、投诉、转人工——不是只回答问题，而是直接读写真实业务库，把单据和工单都办好。所有回答有据可查，所有写入必经确认。
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => openAgent(userId || undefined)}
                className="inline-flex items-center gap-2 rounded-xl bg-accent-gradient px-6 py-3 text-sm font-bold text-white transition hover:-translate-y-0.5 hover:shadow-accent-glow"
              >
                立即对话
                <ArrowRight className="h-4 w-4" />
              </button>
              <Link
                href="/products"
                className="inline-flex items-center rounded-xl border border-line bg-elevated px-6 py-3 text-sm font-bold text-primary transition hover:-translate-y-0.5 hover:border-accent/60 hover:text-accent"
              >
                逛商城
              </Link>
            </div>
          </div>

          {/* 数字人 + 对话预览气泡 */}
          <div className="relative mx-auto w-full max-w-sm">
            <div className="assistant-aura absolute bottom-8 left-1/2 h-40 w-64 rounded-full bg-accent/30 blur-2xl" />
            <img
              src="/assistant/ai-assistant-avatar.png"
              alt="小易 AI 助手"
              className="assistant-avatar-float relative z-10 mx-auto h-[280px] w-[280px] object-contain"
            />
            <div className="relative z-20 -mt-10 space-y-2">
              <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-xs font-semibold leading-5 text-white shadow-lg">
                订单 ORD_DEMO_003 的退款帮我办一下
              </div>
              <div className="w-fit max-w-[92%] rounded-2xl rounded-bl-sm border border-line bg-elevated px-4 py-2.5 text-xs leading-5 text-primary shadow-lg">
                退款已提交，单号 RF_DEMO_002，审核通过后 1-3 个工作日原路退回。物流轨迹我也一并核对了。
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ══ 能力 Bento 网格 ══ */}
      <section className="mt-6">
        <div className="rise-in flex items-end justify-between">
          <div>
            <h2 className="text-2xl font-black tracking-tight text-primary">AI 能力全景</h2>
            <p className="mt-1 text-sm text-secondary">六个能力域，全部由真实工具与业务数据驱动。</p>
          </div>
        </div>
        <div className="rise-group mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
          {capabilities.map((item) => (
            <div
              key={item.title}
              className={`group relative overflow-hidden rounded-xl border border-line bg-surface p-5 shadow-card-inset transition duration-300 hover:-translate-y-1 hover:border-accent/60 ${item.span}`}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/10 text-accent transition group-hover:bg-accent/20">
                <item.icon className="h-5 w-5" />
              </div>
              <div className="mt-4 text-base font-black text-primary">{item.title}</div>
              <p className="mt-1.5 text-[13px] leading-6 text-secondary">{item.desc}</p>
              <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-line bg-elevated px-2.5 py-1 text-[11px] font-semibold text-accent">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                {item.accent}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ══ 实时业务数据带 ══ */}
      <section className="rise-in mt-6 rounded-2xl border border-line bg-surface p-6 shadow-card-inset md:p-8">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-xl font-black tracking-tight text-primary">实时业务数据</h2>
            <p className="mt-1 text-sm text-secondary">商品、订单、退款、投诉由 MySQL 真实驱动，AI 直接读写。</p>
          </div>
          {toolRate != null && (
            <div className="text-sm font-bold text-success">工具调用成功率 {toolRate}%</div>
          )}
        </div>
        <div className="rise-group mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {statItems.map((item) => (
            <StatNumber key={item.label} label={item.label} value={item.value} />
          ))}
        </div>
        {toolBars.length > 0 && (
          <div className="mt-6 grid gap-2.5 rounded-xl border border-line bg-elevated p-4 sm:grid-cols-2 lg:grid-cols-5">
            {toolBars.map((bar) => (
              <div key={bar.label} className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px] font-semibold">
                  <span className="text-secondary">{bar.label}</span>
                  <span className="tabular-nums text-primary">{bar.rate}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-base">
                  <div
                    className="h-full rounded-full bg-accent-gradient transition-all duration-700"
                    style={{ width: `${bar.rate}%` }}
                  />
                </div>
                <div className="text-[10px] text-tertiary">{bar.count} 次调用</div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ══ 精选商品（降级为小卡片流） ══ */}
      <section className="rise-in mt-6">
        <div className="flex items-end justify-between">
          <div>
            <h2 className="text-xl font-black tracking-tight text-primary">精选商品</h2>
            <p className="mt-1 text-sm text-secondary">真实类目、价格与库存，来自业务数据库。</p>
          </div>
          <Link href="/products" className="text-sm font-bold text-accent transition hover:text-accent-hover">
            进入商城 &gt;
          </Link>
        </div>
        <div className="rise-group mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {products.length > 0 ? products.map((product) => (
            <Link
              key={product.product_id}
              href={`/products/${product.product_id}`}
              className="group overflow-hidden rounded-xl border border-line bg-surface shadow-card-inset transition hover:-translate-y-0.5 hover:border-accent/60"
            >
              <div className="relative aspect-[4/3] bg-elevated">
                <Image
                  src={productImage(product.images?.[0]?.image_url)}
                  alt={product.product_name}
                  fill
                  className="object-cover transition group-hover:scale-[1.02]"
                  sizes="25vw"
                  unoptimized
                />
              </div>
              <div className="p-3">
                <div className="line-clamp-1 text-sm font-bold text-primary">{product.product_name}</div>
                <div className="mt-1.5 flex items-end justify-between">
                  <div className="ai-price text-lg">{formatCurrency(product.price)}</div>
                  <div className="text-[11px] text-tertiary">可售 {product.available_quantity ?? 0}</div>
                </div>
              </div>
            </Link>
          )) : (
            <div className="col-span-full rounded-xl border border-dashed border-line bg-surface p-8 text-center">
              <div className="text-base font-black text-primary">商品加载中</div>
              <p className="mt-2 text-sm text-secondary">正在从业务数据库读取商品，稍候片刻即可看到最新在售商品。</p>
            </div>
          )}
        </div>
      </section>
    </SiteShell>
  );
}

/** 数据带大数字（tabular-nums + 滚动动画） */
function StatNumber({ label, value }: { label: string; value: number | null }) {
  const display = useCountUp(value);
  return (
    <div className="rounded-xl border border-line bg-elevated p-4">
      <div className="text-3xl font-black tabular-nums text-primary md:text-4xl">
        {value == null ? "--" : display}
      </div>
      <div className="mt-1 text-xs font-semibold text-secondary">{label}</div>
    </div>
  );
}
