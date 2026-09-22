/**
 * Agent Trace 类型定义
 *
 * 职责：
 * - 定义前端接收的 Agent 执行追踪数据结构
 * - 供 Debug Panel 组件使用
 * - 与后端 AgentTraceData schema 严格对应
 *
 * 设计理念：
 * - 仅包含 Debug Panel 展示所需的摘要字段
 * - 完整 trace steps 保留在后端日志中
 * - 类型安全，所有字段有明确类型
 *
 * 架构位置：
 * - types/ 层，被 components/debug/ 引用
 * - 与后端 models/message.py 中的 AgentTraceData 一一对应
 *
 * 扩展规划：
 * - Phase 3: 增加 tool_calls 字段
 * - Phase 4: 增加 workflow_steps 字段
 * - Phase 5: 增加 reasoning 字段
 */

/**
 * Agent 执行追踪摘要
 *
 * 从后端 API 响应的 data.trace 字段中获取。
 * 仅在开发模式（后端 APP_DEBUG=true）时返回。
 */
export interface AgentTraceData {
  /** 追踪唯一 ID */
  trace_id: string;

  /** 识别的意图类型 */
  intent: string;

  /** 意图置信度 (0.0 - 1.0) */
  confidence: number;

  /** 选中的 Flow Handler 名称 */
  selected_flow: string;

  /** 使用的 Prompt 标识 */
  selected_prompt: string;

  /** Agent 总耗时（毫秒） */
  duration_ms: number;

  /** 意图中文描述 */
  intent_desc: string;

  /** Agent 内部推理摘要 */
  reasoning: string;

  /** 工具调用记录 */
  tool_calls: ToolCallTrace[];

  /** 会话 ID */
  session_id: string;

  /** FSM 当前状态 */
  current_state: string;

  /** 当前等待的 Slot */
  waiting_for: string;

  /** 已收集的 Slot 值 */
  collected_slots: Record<string, unknown>;

  /** 被挂起的 Flow 列表 */
  suspended_flows?: Array<{
    flow_name: string;
    state: string;
    waiting_for: string;
    slots: Record<string, unknown>;
  }>;

  /** 当前 Slot 重试次数 */
  retry_count?: number;

  // ===== Phase 5.3: Memory + Context =====
  /** 注入 Prompt 的历史消息数 */
  memory_count?: number;

  /** 实际用于 RAG 检索的增强 Query */
  retrieval_query?: string;

  /** 是否使用了 RAG 回答 */
  rag_used?: boolean;

  /** RAG 检索到的 chunk 数 */
  rag_chunks?: number;

  /** RAG 来源文档列表 */
  rag_sources?: string[];

  // ===== Phase 5.4: Tool Calling =====
  /** 选中的工具名称 */
  selected_tool?: string;

  /** 工具调用参数 */
  tool_args?: Record<string, unknown>;

  /** 工具返回结果 */
  tool_result?: Record<string, unknown>;

  /** 工具执行耗时（毫秒） */
  tool_latency_ms?: number;

  /** 工具执行是否成功 */
  tool_success?: boolean;

  /** 工具执行错误信息 */
  tool_error?: string;

  /** Workflow 执行步骤数 */
  workflow_steps?: number;

  // ===== 多来源信息整合：RAG 检索透明化（可选字段，向后兼容） =====
  /** 多路检索各路命中统计（语义路/关键词路） */
  retrieval_routes?: RetrievalRouteStatsMap;

  /** RRF 融合分数 */
  rrf_score?: number;

  /** 二次补检触发信息 */
  revalidation?: RetrievalRevalidation;
}

// ===== RAG 检索透明化类型（G3：Debug Panel 展示用，均为可选，向后兼容） =====

/** 单路检索命中统计 */
export interface RetrievalRouteStats {
  /** 该路命中条数 */
  count?: number;
  /** 该路最高分 */
  top_score?: number;
  /** 关键词路使用的核心词表 */
  terms?: string[];
}

/** 多路检索统计映射（vector=语义路 / keyword=关键词路） */
export interface RetrievalRouteStatsMap {
  vector?: RetrievalRouteStats;
  keyword?: RetrievalRouteStats;
}

/** 二次补检触发信息（相关性校验/覆盖度校验） */
export interface RetrievalRevalidation {
  /** 是否触发补检 */
  triggered?: boolean;
  /** 触发原因：relevance（语义路未命中）/ coverage（关键实体缺失） */
  reason?: string;
  /** 补检使用的重试查询 */
  retry_query?: string;
  /** 补检后结果条数 */
  retry_result_count?: number;
  /** 是否应用实体护栏过滤 */
  entity_guard_applied?: boolean;
}

/** knowledge_search 工具 debug_info 中与检索透明化相关的字段 */
export interface RetrievalDebugInfo {
  fusion?: string;
  routes?: RetrievalRouteStatsMap;
  revalidation?: RetrievalRevalidation;
  expanded_query?: string;
  inferred_category?: string;
}

/**
 * 从 trace 中提取检索透明化数据。
 * 优先读 AgentTraceData 顶层可选字段；否则从 knowledge_search 工具调用的
 * tool_output.debug_info 中提取（后端当前的数据通路）。
 * 无检索 trace（如闲聊）时返回 null。
 */
export function extractRetrievalDebug(
  trace: AgentTraceData | null | undefined,
): RetrievalDebugInfo | null {
  if (!trace) return null;

  if (trace.retrieval_routes || trace.revalidation) {
    return {
      routes: trace.retrieval_routes,
      revalidation: trace.revalidation,
    };
  }

  const knowledgeCall = (trace.tool_calls || []).find(
    (call) => call.tool_name === "knowledge_search" && call.success && call.tool_output,
  );
  const debug = knowledgeCall?.tool_output?.debug_info as RetrievalDebugInfo | undefined;
  if (debug && (debug.routes || debug.revalidation)) {
    return debug;
  }
  return null;
}

/**
 * 工具调用记录
 */
export interface ToolCallTrace {
  /** 工具名称 */
  tool_name: string;
  /** 工具输入参数 */
  tool_input: Record<string, unknown>;
  /** 工具输出结果 */
  tool_output: Record<string, unknown>;
  /** 是否执行成功 */
  success: boolean;
  /** 执行耗时（毫秒） */
  latency_ms?: number;
  /** 是否超时 */
  timed_out?: boolean;
}

/**
 * 置信度等级判定
 *
 * 供 Debug Panel 根据置信度显示不同颜色/标签。
 */
export type ConfidenceLevel = "high" | "medium" | "low";

/**
 * 根据置信度数值判定等级
 */
export function getConfidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= 0.8) return "high";
  if (confidence >= 0.5) return "medium";
  return "low";
}

/**
 * 置信度等级对应的颜色
 */
export const CONFIDENCE_COLORS: Record<ConfidenceLevel, string> = {
  high: "#22c55e",   // green-500
  medium: "#f59e0b", // amber-500
  low: "#ef4444",    // red-500
};
