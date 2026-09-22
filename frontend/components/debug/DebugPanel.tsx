"use client";

import { useState } from "react";
import type { AgentTraceData } from "@/types/trace";
import { CONFIDENCE_COLORS, extractRetrievalDebug, getConfidenceLevel } from "@/types/trace";

interface DebugPanelProps {
  trace: AgentTraceData | null;
  alwaysVisible?: boolean;
}

export default function DebugPanel({ trace, alwaysVisible = false }: DebugPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  if ((!alwaysVisible && process.env.NODE_ENV !== "development") || !trace) {
    return null;
  }

  const confidenceLevel = getConfidenceLevel(trace.confidence || 0);
  const confidenceColor = CONFIDENCE_COLORS[confidenceLevel];
  const confidencePercent = Math.round((trace.confidence || 0) * 100);

  return (
    <div className="border-t border-line bg-elevated/60">
      <button
        onClick={() => setIsExpanded((value) => !value)}
        className="flex w-full items-center justify-between px-4 py-2 text-xs text-secondary transition hover:bg-elevated"
      >
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="font-bold text-primary">Agent Trace</span>
          <span style={{ color: confidenceColor }}>
            {trace.intent || "未知意图"}（{confidencePercent}%）
          </span>
          <span className="text-tertiary">-&gt;</span>
          <span>{trace.selected_flow || "未分配"}</span>
          {trace.selected_tool && (
            <>
              <span className="text-tertiary">|</span>
              <span className="text-accent">{trace.selected_tool}</span>
            </>
          )}
          {trace.current_state && (
            <>
              <span className="text-tertiary">|</span>
              <span className="text-accent">{trace.current_state}</span>
            </>
          )}
          <span className="text-tertiary">|</span>
          <span>{trace.duration_ms || 0}ms</span>
        </span>
        <span>{isExpanded ? "收起" : "展开"}</span>
      </button>

      {isExpanded && (
        <div className="grid gap-3 px-4 pb-4 text-xs md:grid-cols-4">
          <TraceCard title="意图" value={trace.intent || "未知"} detail={trace.intent_desc} />
          <div className="rounded-xl border border-line bg-surface p-3">
            <div className="mb-1 text-tertiary">置信度</div>
            <div className="flex items-center gap-2">
              <span className="font-bold" style={{ color: confidenceColor }}>
                {confidencePercent}%
              </span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-base">
                <div className="h-full" style={{ width: `${confidencePercent}%`, backgroundColor: confidenceColor }} />
              </div>
            </div>
          </div>
          <TraceCard title="流程" value={trace.selected_flow || "无"} />
          <TraceCard title="提示词" value={trace.selected_prompt || "无"} />
          <TraceCard title="耗时" value={`${trace.duration_ms || 0}ms`} />
          <TraceCard title="会话" value={trace.session_id || "无"} />
          <TraceCard title="状态" value={trace.current_state || "空闲"} />
          <TraceCard title="等待项" value={trace.waiting_for || "无"} />

          {trace.collected_slots && Object.keys(trace.collected_slots).length > 0 && (
            <TraceJson title="已收集 Slot" value={trace.collected_slots} />
          )}

          {trace.tool_calls && trace.tool_calls.length > 0 && (
            <div className="rounded-xl border border-line bg-surface p-3 md:col-span-4">
              <div className="mb-2 font-bold text-accent">工具调用（{trace.tool_calls.length}）</div>
              <div className="space-y-2">
                {trace.tool_calls.map((toolCall, index) => (
                  <div key={`${toolCall.tool_name}-${index}`} className="rounded-xl border border-line bg-elevated p-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={toolCall.success ? "text-success" : "text-danger"}>{toolCall.success ? "成功" : "失败"}</span>
                      <span className="font-bold text-accent">{toolCall.tool_name}</span>
                      {toolCall.latency_ms !== undefined && <span className="text-tertiary">{Math.round(toolCall.latency_ms)}ms</span>}
                    </div>
                    <div className="mt-1 text-[11px] text-secondary">输入：{JSON.stringify(toolCall.tool_input)}</div>
                    <div className="mt-1 text-[11px] text-secondary">输出：{JSON.stringify(toolCall.tool_output).slice(0, 180)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {trace.tool_error && (
            <div className="rounded-xl border border-danger/30 bg-danger/10 p-3 text-danger md:col-span-4">
              <div className="font-bold">工具错误</div>
              <div className="mt-1">{trace.tool_error}</div>
            </div>
          )}

          {(() => {
            const retrievalDebug = extractRetrievalDebug(trace);
            if (!retrievalDebug) return null;
            const vector = retrievalDebug.routes?.vector;
            const keyword = retrievalDebug.routes?.keyword;
            const revalidation = retrievalDebug.revalidation;
            return (
              <div className="rounded-xl border border-accent/30 bg-accent/10 p-3 md:col-span-4">
                <div className="mb-2 font-bold text-accent">RAG 检索透明化</div>
                <div className="grid gap-2 md:grid-cols-2">
                  <div className="rounded-lg border border-line bg-surface p-2">
                    <div className="mb-1 text-[11px] font-bold text-secondary">多路检索分数</div>
                    <div className="text-[11px] text-secondary">
                      <div>语义路（vector）：命中 {vector?.count ?? 0} 条，最高分 {vector?.top_score ?? "-"}</div>
                      <div>关键词路（keyword）：命中 {keyword?.count ?? 0} 条，最高分 {keyword?.top_score ?? "-"}</div>
                      {retrievalDebug.fusion && <div className="text-tertiary">融合方式：{retrievalDebug.fusion}</div>}
                    </div>
                  </div>
                  {revalidation && (
                    <div className="rounded-lg border border-line bg-surface p-2">
                      <div className="mb-1 text-[11px] font-bold text-secondary">二次补检</div>
                      {revalidation.triggered ? (
                        <div className="text-[11px] text-secondary">
                          <div>
                            触发原因：
                            {revalidation.reason === "relevance"
                              ? "语义路未命中（相关性校验）"
                              : revalidation.reason === "coverage"
                                ? "关键实体缺失（覆盖度校验）"
                                : revalidation.reason || "未知"}
                          </div>
                          {revalidation.retry_query && <div>重试查询：{revalidation.retry_query}</div>}
                          <div>补检后结果：{revalidation.retry_result_count ?? "-"} 条</div>
                        </div>
                      ) : (
                        <div className="text-[11px] text-tertiary">本轮未触发补检</div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })()}

          {trace.reasoning && (
            <div className="rounded-xl border border-line bg-surface p-3 md:col-span-4">
              <div className="font-bold text-accent">推理说明</div>
              <div className="mt-1 whitespace-pre-line text-secondary">{trace.reasoning}</div>
            </div>
          )}

          <TraceCard title="Trace ID" value={trace.trace_id || "无"} className="md:col-span-4" />
        </div>
      )}
    </div>
  );
}

function TraceCard({
  title,
  value,
  detail,
  className = "",
}: {
  title: string;
  value: string;
  detail?: string;
  className?: string;
}) {
  return (
    <div className={`rounded-xl border border-line bg-surface p-3 ${className}`}>
      <div className="mb-1 text-tertiary">{title}</div>
      <div className="break-words font-bold text-primary">{value}</div>
      {detail && <div className="mt-1 text-[11px] text-secondary">{detail}</div>}
    </div>
  );
}

function TraceJson({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3 md:col-span-4">
      <div className="mb-2 font-bold text-accent">{title}</div>
      <pre className="overflow-auto rounded-lg bg-base p-2 text-[11px] text-secondary">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}
