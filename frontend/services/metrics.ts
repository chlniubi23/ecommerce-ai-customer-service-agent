const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface FlowDistributionItem {
  flow: string;
  label: string;
  count: number;
  color: string;
}

export interface PromptIteration {
  version: string;
  date: string;
  change: string;
  metric: string;
  before: string;
  after: string;
  improvement: string;
}

export interface MetricsData {
  live: {
    total_orders: number;
    total_refunds: number;
    total_complaints: number;
    product_count: number;
    total_users: number;
    order_status: Record<string, number>;
    refund_breakdown: { approved: number; pending: number; rejected: number };
    refund_status_raw: Record<string, number>;
    complaint_priority: Record<string, number>;
  };
  tool_calls: {
    total: number;
    total_audit_records: number;
    distinct_sessions: number;
    overall_success_rate: number | null;
    by_tool: Record<string, number>;
    success_by_tool: Record<string, number>;
  };
  flow_distribution: FlowDistributionItem[];
  prompt_iterations: PromptIteration[];
}

export async function fetchMetrics(): Promise<MetricsData> {
  const res = await fetch(`${API_BASE_URL}/api/metrics`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Metrics API ${res.status}`);
  const json = await res.json();
  if (!json.success || !json.data) throw new Error(json.error?.message ?? "Unknown error");
  return json.data as MetricsData;
}
