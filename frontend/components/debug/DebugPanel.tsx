"use client";

import { useState } from "react";
import type { AgentTraceData } from "@/types/trace";
import { CONFIDENCE_COLORS, getConfidenceLevel } from "@/types/trace";

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
    <div className="border-t border-blue-100 bg-blue-50/40">
      <button
        onClick={() => setIsExpanded((value) => !value)}
        className="flex w-full items-center justify-between px-4 py-2 text-xs text-slate-500 transition hover:bg-blue-50"
      >
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="font-bold text-slate-700">Agent Trace</span>
          <span style={{ color: confidenceColor }}>
            {trace.intent || "未知意图"}（{confidencePercent}%）
          </span>
          <span className="text-slate-300">-&gt;</span>
          <span>{trace.selected_flow || "未分配"}</span>
          {trace.selected_tool && (
            <>
              <span className="text-slate-300">|</span>
              <span className="text-[#2563eb]">{trace.selected_tool}</span>
            </>
          )}
          {trace.current_state && (
            <>
              <span className="text-slate-300">|</span>
              <span className="text-purple-600">{trace.current_state}</span>
            </>
          )}
          <span className="text-slate-300">|</span>
          <span>{trace.duration_ms || 0}ms</span>
        </span>
        <span>{isExpanded ? "收起" : "展开"}</span>
      </button>

      {isExpanded && (
        <div className="grid gap-3 px-4 pb-4 text-xs md:grid-cols-4">
          <TraceCard title="意图" value={trace.intent || "未知"} detail={trace.intent_desc} />
          <div className="rounded-xl border border-blue-100 bg-white p-3">
            <div className="mb-1 text-slate-400">置信度</div>
            <div className="flex items-center gap-2">
              <span className="font-bold" style={{ color: confidenceColor }}>
                {confidencePercent}%
              </span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
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
            <div className="rounded-xl border border-blue-100 bg-white p-3 md:col-span-4">
              <div className="mb-2 font-bold text-[#2563eb]">工具调用（{trace.tool_calls.length}）</div>
              <div className="space-y-2">
                {trace.tool_calls.map((toolCall, index) => (
                  <div key={`${toolCall.tool_name}-${index}`} className="rounded-xl border border-slate-100 bg-[#fafafa] p-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={toolCall.success ? "text-emerald-600" : "text-red-600"}>{toolCall.success ? "成功" : "失败"}</span>
                      <span className="font-bold text-[#2563eb]">{toolCall.tool_name}</span>
                      {toolCall.latency_ms !== undefined && <span className="text-slate-400">{Math.round(toolCall.latency_ms)}ms</span>}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500">输入：{JSON.stringify(toolCall.tool_input)}</div>
                    <div className="mt-1 text-[11px] text-slate-500">输出：{JSON.stringify(toolCall.tool_output).slice(0, 180)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {trace.tool_error && (
            <div className="rounded-xl border border-red-100 bg-red-50 p-3 text-red-700 md:col-span-4">
              <div className="font-bold">工具错误</div>
              <div className="mt-1">{trace.tool_error}</div>
            </div>
          )}

          {trace.reasoning && (
            <div className="rounded-xl border border-blue-100 bg-white p-3 md:col-span-4">
              <div className="font-bold text-[#2563eb]">推理说明</div>
              <div className="mt-1 whitespace-pre-line text-slate-700">{trace.reasoning}</div>
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
    <div className={`rounded-xl border border-blue-100 bg-white p-3 ${className}`}>
      <div className="mb-1 text-slate-400">{title}</div>
      <div className="break-words font-bold text-slate-800">{value}</div>
      {detail && <div className="mt-1 text-[11px] text-slate-500">{detail}</div>}
    </div>
  );
}

function TraceJson({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <div className="rounded-xl border border-blue-100 bg-white p-3 md:col-span-4">
      <div className="mb-2 font-bold text-[#2563eb]">{title}</div>
      <pre className="overflow-auto rounded-lg bg-[#fafafa] p-2 text-[11px] text-slate-600">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}
