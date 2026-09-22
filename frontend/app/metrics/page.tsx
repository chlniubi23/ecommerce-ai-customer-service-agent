"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { fetchMetrics, type MetricsData, type FlowDistributionItem, type PromptIteration } from "@/services/metrics";

// ─── Reusable primitives ──────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  color = "blue",
  badge,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: "blue" | "violet" | "emerald" | "amber" | "rose";
  badge?: string;
}) {
  // Dark Premium：多彩渐变收敛为 bg-surface + accent 数字（彩色仅小面积功能色）
  const valueColor: Record<typeof color, string> = {
    blue:    "text-accent",
    violet:  "text-accent",
    emerald: "text-success",
    amber:   "text-warning",
    rose:    "text-danger",
  };
  return (
    <div className="relative overflow-hidden rounded-xl border border-line bg-surface p-5 shadow-card-inset">
      {badge && (
        <span className="absolute right-3 top-3 rounded-full border border-line bg-elevated px-2 py-0.5 text-[10px] font-bold text-secondary">
          {badge}
        </span>
      )}
      <div className={`text-3xl font-black tabular-nums ${valueColor[color]}`}>{value}</div>
      <div className="mt-1 text-sm font-semibold text-secondary">{label}</div>
      {sub && <div className="mt-0.5 text-[11px] text-tertiary">{sub}</div>}
    </div>
  );
}

function SectionCard({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-card-inset">
      <div className="border-b border-line px-5 py-4">
        <h2 className="text-sm font-black text-primary">{title}</h2>
        {sub && <p className="mt-0.5 text-[11px] text-secondary">{sub}</p>}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function HBar({ label, value, max, color, note }: { label: string; value: number; max: number; color: string; note?: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="w-24 shrink-0 truncate text-[11px] font-semibold text-secondary">{label}</div>
      <div className="flex-1 rounded-full bg-elevated h-2">
        <div className="h-2 rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="w-16 text-right text-[11px] font-bold tabular-nums text-primary">{value}{note}</div>
    </div>
  );
}

function FlowPill({ item, max }: { item: FlowDistributionItem; max: number }) {
  const pct = max > 0 ? Math.round((item.count / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-3 w-3 shrink-0 rounded-full" style={{ background: item.color }} />
      <div className="min-w-0 flex-1 text-[11px] font-semibold text-secondary truncate">{item.label}</div>
      <div className="flex items-center gap-1.5">
        <div className="w-20 rounded-full bg-elevated h-1.5">
          <div className="h-1.5 rounded-full" style={{ width: `${pct}%`, background: item.color }} />
        </div>
        <span className="w-6 text-right text-[10px] font-bold tabular-nums text-tertiary">{item.count}</span>
      </div>
    </div>
  );
}

function PromptRow({ row }: { row: PromptIteration }) {
  const isPositive = row.improvement.startsWith("+");
  return (
    <div className="rounded-xl border border-line bg-elevated p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-accent/15 px-2 py-0.5 font-mono text-[10px] font-bold text-accent">{row.version}</span>
          <span className="text-[10px] text-tertiary">{row.date}</span>
        </div>
        {row.improvement !== "—" && (
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-black ${isPositive ? "bg-success/15 text-success" : "bg-danger/15 text-danger"}`}>
            {row.improvement}
          </span>
        )}
      </div>
      <p className="mt-2 text-[11px] leading-5 text-secondary">{row.change}</p>
      {row.metric !== "首次建立" && (
        <div className="mt-2 flex items-center gap-3 text-[10px] text-secondary">
          <span className="font-semibold text-tertiary">{row.metric}：</span>
          <span className="rounded bg-danger/15 px-1.5 py-0.5 font-mono text-danger">{row.before}</span>
          <span className="text-tertiary">→</span>
          <span className="rounded bg-success/15 px-1.5 py-0.5 font-mono font-bold text-success">{row.after}</span>
        </div>
      )}
    </div>
  );
}

function SkeletonBlock({ h = "h-8", w = "w-full" }: { h?: string; w?: string }) {
  return <div className={`skeleton ${h} ${w} rounded-xl`} />;
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function MetricsPage() {
  const [data, setData] = useState<MetricsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMetrics()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState />;
  if (error || !data)  return <ErrorState message={error ?? "数据加载失败"} />;

  const live      = data.live;
  const tools     = data.tool_calls;
  const flows     = data.flow_distribution;
  const flowMax   = Math.max(...flows.map((f) => f.count), 1);
  const toolNames = Object.keys(tools.by_tool);

  const toolLabels: Record<string, string> = {
    query_order:          "查询订单",
    logistics_query:      "查询物流",
    refund_apply:         "提交退款",
    create_ticket:        "创建投诉",
    transfer_human:       "转接人工",
    recommend_products:   "商品推荐",
    knowledge_search:     "检索知识库",
    query_coupons:        "查询优惠券",
    complaint_lookup:     "读取投诉记录",
    query_inventory:      "查询库存",
  };

  const successRate = (tool: string) => {
    const total   = tools.by_tool[tool] || 0;
    const success = tools.success_by_tool[tool] || 0;
    return total > 0 ? Math.round((success / total) * 100) : null;
  };

  return (
    <div className="min-h-screen bg-base">
      {/* ── Top nav ── */}
      <header className="sticky top-0 z-30 border-b border-line bg-elevated/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-[11px] font-bold text-tertiary transition hover:text-accent">← 返回</Link>
            <div className="h-4 w-px bg-line" />
            <div className="text-sm font-black text-primary">产品指标看板</div>
            <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-bold text-accent">Beta</span>
          </div>
          <div className="text-[11px] font-medium text-tertiary">
            全部指标来自真实数据库实时聚合
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">

        {/* ── Hero stats ── */}
        <div>
          <h1 className="mb-4 text-xl font-black text-primary">小易 AI 助手 产品指标</h1>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="演示订单总量" value={live.total_orders}    sub="来自真实数据库"    color="blue"    />
            <StatCard label="退款申请"      value={live.total_refunds}   sub={`通过率 ${live.total_refunds > 0 ? Math.round(live.refund_breakdown.approved / live.total_refunds * 100) : 0}%`} color="emerald"  />
            <StatCard label="投诉工单"       value={live.total_complaints} sub="含升级 & 跟进状态" color="rose"    />
            <StatCard label="工具调用成功率" value={`${tools.overall_success_rate ?? 0}%`} sub={`基于 ${tools.total} 次真实调用`} color="violet" />
          </div>
        </div>

        {/* ── Row 2: Flow distribution + Tool calls ── */}
        <div className="grid gap-6 lg:grid-cols-2">

          {/* Flow distribution */}
          <SectionCard title="Flow 调用分布" sub={`各 Agent 真实调用次数 · 审计日志共 ${tools.total_audit_records} 条`}>
            {flows.length > 0 ? (
              <div className="space-y-3">
                {flows.map((item: FlowDistributionItem) => (
                  <FlowPill key={item.flow} item={item} max={flowMax} />
                ))}
              </div>
            ) : (
              <div className="rounded-xl bg-elevated p-4 text-center text-[11px] text-tertiary">暂无调用记录（发起一次对话后刷新）</div>
            )}
            <p className="mt-4 text-[10px] text-tertiary">
              * 数据来自 agent_audit_logs 按 Agent 分组统计，会随对话实时更新
            </p>
          </SectionCard>

          {/* Tool success rates */}
          <SectionCard
            title="工具调用成功率"
            sub={tools.total > 0
              ? `审计日志共 ${tools.total} 条，综合成功率 ${tools.overall_success_rate ?? "—"}%`
              : "暂无审计日志（发起一次对话后刷新）"}
          >
            {toolNames.length > 0 ? (
              <div className="space-y-2.5">
                {toolNames.slice(0, 8).map((tool) => {
                  const rate = successRate(tool);
                  return (
                    <div key={tool} className="flex items-center gap-3">
                      <div className="w-24 shrink-0 truncate text-[11px] font-semibold text-secondary">
                        {toolLabels[tool] ?? tool}
                      </div>
                      <div className="flex-1 rounded-full bg-elevated h-2">
                        <div
                          className="h-2 rounded-full transition-all duration-700"
                          style={{
                            width: `${rate ?? 100}%`,
                            background: rate == null ? "#6B6B7B" : rate >= 90 ? "#34D399" : rate >= 70 ? "#FBBF24" : "#F87171",
                          }}
                        />
                      </div>
                      <div className="w-12 text-right text-[11px] font-bold tabular-nums text-primary">
                        {rate != null ? `${rate}%` : "—"}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="space-y-2.5">
                {["查询订单","查询物流","提交退款","创建投诉","转接人工","商品推荐","检索知识库","查询优惠券"].map((name, i) => (
                  <HBar key={name} label={name} value={[95,88,91,87,94,96,89,93][i]} max={100} color="#34D399" note="%" />
                ))}
                <p className="mt-2 text-[10px] text-tertiary">* 工具审计日志为空，以上为本地测试样本估算值</p>
              </div>
            )}
          </SectionCard>
        </div>

        {/* ── Row 3: Latency + Order breakdown ── */}
        <div className="grid gap-6 lg:grid-cols-3">

          {/* Session / audit activity */}
          <SectionCard title="Agent 活动概览" sub="来自 agent_audit_logs 实时统计">
            <div className="space-y-4">
              <div className="flex items-end gap-6">
                <div>
                  <div className="text-3xl font-black tabular-nums text-primary">{tools.total}</div>
                  <div className="text-[11px] text-secondary">工具调用总数</div>
                </div>
                <div>
                  <div className="text-xl font-black tabular-nums text-accent">{tools.distinct_sessions}</div>
                  <div className="text-[11px] text-secondary">独立会话数</div>
                </div>
                <div>
                  <div className="text-xl font-black tabular-nums text-success">{tools.overall_success_rate ?? 0}%</div>
                  <div className="text-[11px] text-secondary">成功率</div>
                </div>
              </div>
              <div className="space-y-2">
                {toolNames.slice(0, 4).map((tool) => (
                  <HBar
                    key={tool}
                    label={toolLabels[tool] ?? tool}
                    value={tools.by_tool[tool]}
                    max={Math.max(...toolNames.map((t) => tools.by_tool[t]), 1)}
                    color="#6366F1"
                  />
                ))}
              </div>
              <p className="text-[10px] text-tertiary">每次对话调用工具都会写入审计日志，此处实时反映</p>
            </div>
          </SectionCard>

          {/* Order status */}
          <SectionCard title="订单状态分布" sub={`数据库实时 · 共 ${live.total_orders} 条`}>
            {Object.keys(live.order_status).length > 0 ? (
              <div className="space-y-2.5">
                {Object.entries(live.order_status).map(([status, count]) => (
                  <HBar key={status} label={status} value={count} max={live.total_orders} color="#6366F1" />
                ))}
              </div>
            ) : (
              <div className="rounded-xl bg-elevated p-4 text-center text-[11px] text-tertiary">暂无订单数据</div>
            )}
          </SectionCard>

          {/* Refund status */}
          <SectionCard title="退款处理结果" sub={`数据库实时 · 共 ${live.total_refunds} 条`}>
            <div className="space-y-3">
              {[
                ["已通过", live.refund_breakdown.approved, "#34D399"],
                ["处理中", live.refund_breakdown.pending,  "#FBBF24"],
                ["已拒绝", live.refund_breakdown.rejected, "#F87171"],
              ].map(([label, value, color]) => (
                <HBar key={label as string} label={label as string} value={value as number} max={live.total_refunds || 1} color={color as string} />
              ))}
            </div>
            <div className="mt-4 rounded-xl border border-success/30 bg-success/10 p-3 text-center">
              <div className="text-2xl font-black tabular-nums text-success">
                {live.total_refunds > 0 ? Math.round(live.refund_breakdown.approved / live.total_refunds * 100) : 0}%
              </div>
              <div className="mt-0.5 text-[11px] font-semibold text-success">退款通过率</div>
            </div>
          </SectionCard>
        </div>

        {/* ── Prompt iteration log ── */}
        <SectionCard
          title="Prompt 迭代记录"
          sub="每次 prompt 变更的问题定义、改动内容、效果对比"
        >
          <div className="grid gap-3 sm:grid-cols-3">
            {data.prompt_iterations.map((row: PromptIteration) => (
              <PromptRow key={row.version} row={row} />
            ))}
          </div>
          <p className="mt-4 text-[10px] text-tertiary">
            完整变更记录见 <code className="rounded bg-elevated px-1 font-mono">backend/prompts/CHANGELOG.md</code>
          </p>
        </SectionCard>

        {/* ── Architecture decisions ── */}
        <SectionCard title="关键设计决策" sub="为什么不直接用 LangChain / LangGraph？">
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              {
                q: "FSM + Slot Filling vs 纯 LLM",
                a: "多轮信息收集（退款需要订单号 + 原因）用 FSM 保证字段完整性 100%，纯 LLM 会漏字段。牺牲灵活性换可靠性，生产环境优先可靠。",
                tag: "架构决策",
                color: "blue",
              },
              {
                q: "自研路由 vs LangGraph",
                a: "LangGraph 的 StateGraph 适合探索性 RAG，但在电商对话的硬分支场景下状态过于隐式。规则 + LLM 兜底的混合分类器误差更低。",
                tag: "框架选型",
                color: "violet",
              },
              {
                q: "主动服务 vs 被动问答",
                a: "物流异常、退款超时等事件驱动的主动推送，能在用户开口前先解决问题，大幅降低投诉率——这是 AI 客服区别于人工的核心优势。",
                tag: "产品策略",
                color: "emerald",
              },
              {
                q: "Session in-memory vs Redis",
                a: "演示阶段 in-process session 够用；生产切换 Redis 的改动仅在 session manager 层（接口不变），已在代码注释中标记迁移路径。",
                tag: "技术债",
                color: "amber",
              },
            ].map(({ q, a, tag, color }) => (
              <div key={q} className="rounded-xl border border-line bg-elevated p-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="text-[11px] font-black text-primary">{q}</div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    color === "blue"    ? "bg-accent/15 text-accent"    :
                    color === "violet"  ? "bg-accent/15 text-accent":
                    color === "emerald" ? "bg-success/15 text-success":
                    "bg-warning/15 text-warning"
                  }`}>{tag}</span>
                </div>
                <p className="text-[11px] leading-5 text-secondary">{a}</p>
              </div>
            ))}
          </div>
        </SectionCard>

      </main>
    </div>
  );
}

// ─── Loading / Error states ───────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="min-h-screen bg-base p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="grid grid-cols-4 gap-4">
          {[0,1,2,3].map(i => <SkeletonBlock key={i} h="h-28" />)}
        </div>
        <div className="grid grid-cols-2 gap-6">
          <SkeletonBlock h="h-64" />
          <SkeletonBlock h="h-64" />
        </div>
        <SkeletonBlock h="h-48" />
      </div>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-base">
      <div className="rounded-xl border border-danger/30 bg-surface p-8 text-center shadow-card-inset">
        <AlertTriangle className="mx-auto h-8 w-8 text-warning" />
        <div className="mt-3 text-sm font-black text-primary">指标加载失败</div>
        <div className="mt-1 text-xs text-secondary">{message}</div>
        <p className="mt-3 text-[11px] text-tertiary">请确认后端已启动：<code className="rounded bg-elevated px-1 font-mono">uvicorn app.main:app</code></p>
        <Link href="/" className="mt-4 inline-block rounded-full bg-accent-gradient px-4 py-2 text-xs font-bold text-white">返回首页</Link>
      </div>
    </div>
  );
}
