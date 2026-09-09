const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string; detail?: string } | null;
  metadata: { trace_id: string; timestamp: string };
}

export interface DemoUser {
  user_id: string;
  username: string;
  email: string;
  phone: string;
  full_name: string;
  status: string;
  created_at?: string;
  last_login_at?: string | null;
  addresses?: Address[];
}

export interface Address {
  address_id: string;
  receiver_name: string;
  phone: string;
  province: string;
  city: string;
  district: string;
  address_line: string;
  postal_code?: string;
  is_default: number | boolean;
}

export interface Product {
  product_id: string;
  sku_id: string;
  product_name: string;
  description: string;
  brand_name: string;
  category_name: string;
  category_path?: string;
  price: number;
  currency: string;
  product_status: string;
  tags?: string[];
  attributes?: Record<string, unknown>;
  quantity?: number;
  available_quantity?: number;
  reserved_quantity?: number;
  safety_stock?: number;
  inventory_status?: string;
  images?: { image_url: string; alt_text?: string; is_primary?: number }[];
}

export interface Category {
  category_id: string;
  parent_id?: string | null;
  category_name: string;
  category_level: number;
  category_path: string;
}

export interface OrderItem {
  order_item_id: string;
  product_id: string;
  sku_id: string;
  product_name: string;
  quantity: number;
  unit_price: number;
  line_amount: number;
}

export interface Logistics {
  shipment_id: string;
  order_id: string;
  carrier_name: string;
  tracking_no: string;
  current_status: string;
  current_location: string;
  estimated_delivery_at?: string;
  timeline?: {
    event_id: string;
    event_time: string;
    location: string;
    status: string;
    description: string;
  }[];
}

export interface Order {
  order_id: string;
  user_id: string;
  username?: string;
  full_name?: string;
  order_status: string;
  payment_status: string;
  shipping_status: string;
  receipt_status: string;
  logistics_status?: string;
  total_amount: number;
  currency: string;
  created_at: string;
  paid_at?: string;
  completed_at?: string;
  receiver_name?: string;
  receiver_phone?: string;
  province?: string;
  city?: string;
  district?: string;
  address_line?: string;
  estimated_delivery_at?: string;
  items: OrderItem[];
  logistics?: Logistics | null;
  refund?: Refund | null;
}

export interface Refund {
  refund_id: string;
  order_id: string;
  user_id: string;
  refund_reason: string;
  refund_amount: number;
  audit_status: string;
  refund_status: string;
  created_at: string;
  updated_at: string;
}

export interface Complaint {
  complaint_id: string;
  ticket_id: string;
  user_id: string;
  order_id?: string;
  complaint_type: string;
  content: string;
  complaint_status: string;
  priority: string;
  created_at: string;
  updated_at: string;
  escalations?: {
    escalation_id: string;
    escalation_reason: string;
    escalated_to: string;
    supervisor_result?: string;
    escalation_status: string;
  }[];
}

export interface AgentContext {
  user?: DemoUser | null;
  product?: Product | null;
  order?: Order | null;
  logistics?: Logistics | null;
  refund?: Refund | null;
  complaints?: Complaint[];
}

export type AssistantInsightSeverity = "urgent" | "high" | "medium" | "low";

export interface AssistantInsight {
  insight_id: string;
  type: string;
  severity: AssistantInsightSeverity;
  title: string;
  description: string;
  action_label: string;
  action_prompt: string;
  order_id?: string | null;
  related_id?: string | null;
  created_at?: string | null;
}

export interface AssistantQuickAction {
  label: string;
  prompt: string;
}

export interface AssistantInsights {
  user_id: string;
  summary: string;
  counts: {
    orders: number;
    active_orders: number;
    refunds: number;
    open_refunds: number;
    complaints: number;
    open_complaints: number;
  };
  insights: AssistantInsight[];
  quick_actions: AssistantQuickAction[];
  pain_point_coverage: string[];
}

export interface AssistantEvent {
  event_id: string;
  event_type: string;
  severity: AssistantInsightSeverity;
  title: string;
  description: string;
  order_id?: string | null;
  related_id?: string | null;
  created_at?: string | null;
  assistant_prompt: string;
  requires_user_attention: boolean;
}

export interface AssistantEvents {
  user_id: string;
  events: AssistantEvent[];
  poll_after_seconds: number;
  source: string;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...options,
  });
  const envelope: ApiResponse<T> = await response.json();
  if (!envelope.success) {
    throw new Error(envelope.error?.message || "Request failed");
  }
  return envelope.data as T;
}

export const commerceApi = {
  login: (login: string, password: string) =>
    request<{ token: string; user: DemoUser }>("/api/commerce/auth/login", {
      method: "POST",
      body: JSON.stringify({ login, password }),
    }),
  register: (payload: {
    username: string;
    email: string;
    phone: string;
    password: string;
    full_name: string;
  }) =>
    request<{ token: string; user: DemoUser }>("/api/commerce/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  dashboard: () =>
    request<{
      products: { count: number };
      orders: { count: number };
      refunds: { count: number };
      complaints: { count: number };
      recent_audits: unknown[];
      recent_workflows: unknown[];
    }>("/api/commerce/dashboard"),
  getUser: (userId: string) => request<DemoUser>(`/api/commerce/users/${userId}`),
  categories: () => request<Category[]>("/api/commerce/categories"),
  products: (keyword = "", categoryId = "") => {
    const params = new URLSearchParams();
    if (keyword) params.set("keyword", keyword);
    if (categoryId) params.set("category_id", categoryId);
    return request<Product[]>(`/api/commerce/products?${params.toString()}`);
  },
  product: (productId: string) => request<Product>(`/api/commerce/products/${productId}`),
  createOrder: (user_id: string, product_id: string, quantity: number) =>
    request<Order>("/api/commerce/orders", {
      method: "POST",
      body: JSON.stringify({ user_id, product_id, quantity }),
    }),
  orders: (userId: string) => request<Order[]>(`/api/commerce/users/${userId}/orders`),
  order: (orderId: string) => request<Order>(`/api/commerce/orders/${orderId}`),
  refunds: (userId: string) => request<Refund[]>(`/api/commerce/users/${userId}/refunds`),
  applyRefund: (order_id: string, reason: string) =>
    request<Refund>("/api/commerce/refunds", {
      method: "POST",
      body: JSON.stringify({ order_id, reason }),
    }),
  complaints: (userId: string) =>
    request<Complaint[]>(`/api/commerce/users/${userId}/complaints`),
  createComplaint: (payload: {
    user_id?: string;
    order_id?: string;
    complaint_type: string;
    content: string;
  }) =>
    request<Complaint>("/api/commerce/complaints", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  agentContext: (params: { user_id?: string; order_id?: string; product_id?: string }) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value) search.set(key, value);
    });
    return request<AgentContext>(`/api/commerce/agent/context?${search.toString()}`);
  },
  agentInsights: (userId: string) =>
    request<AssistantInsights>(`/api/commerce/agent/insights?user_id=${encodeURIComponent(userId)}`),
  agentEvents: (userId: string, minSeverity = "medium") =>
    request<AssistantEvents>(
      `/api/commerce/agent/events?user_id=${encodeURIComponent(userId)}&min_severity=${encodeURIComponent(minSeverity)}`,
    ),
  markAgentEventRead: (eventId: string) =>
    request<{ event_id: string; event_status: string }>(
      `/api/commerce/agent/events/${encodeURIComponent(eventId)}/read`,
      { method: "POST" },
    ),
  agentTrace: () =>
    request<{ audits: unknown[]; workflows: unknown[] }>("/api/commerce/agent/trace"),
};

const AUTH_KEY = "commerce_demo_user_id";

export function saveUser(user: DemoUser) {
  if (typeof window !== "undefined") {
    localStorage.setItem(AUTH_KEY, user.user_id);
  }
}

export function getStoredUserId() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(AUTH_KEY) || "";
}

export function clearStoredUser() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(AUTH_KEY);
  }
}
