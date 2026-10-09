export function formatCurrency(value?: number | string | null) {
  const amount = Number(value ?? 0);
  return `¥${amount.toFixed(2)}`;
}

export function formatDate(value?: string | null) {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const statusMap: Record<string, string> = {
  active: "正常",
  locked: "已锁定",
  draft: "预售",
  archived: "下架",
  in_stock: "有货",
  low_stock: "库存紧张",
  out_of_stock: "无货",
  created: "待支付",
  paid: "已支付",
  shipped: "已发货",
  delivered: "已送达",
  completed: "已完成",
  after_sale: "售后中",
  cancelled: "已取消",
  exception: "异常",
  unpaid: "未支付",
  refunded: "已退款",
  partial_refund: "部分退款",
  pending: "待处理",
  packing: "备货中",
  in_transit: "运输中",
  not_required: "无需配送",
  not_received: "未收货",
  received: "已收货",
  confirmed: "已确认",
  picked_up: "已揽收",
  arrived_city: "到达同城",
  out_for_delivery: "派送中",
  pending_review: "待审核",
  reviewing: "审核中",
  approved: "已通过",
  rejected: "已拒绝",
  processing: "处理中",
  submitted: "已提交",
  escalated: "已升级",
  closed: "已结案",
  high: "高",
  urgent: "紧急",
  normal: "普通",
};

export function zhStatus(value?: string | null) {
  if (!value) return "未知";
  return statusMap[value] || value;
}

export function statusTone(value?: string | null) {
  const text = zhStatus(value);
  // Dark Premium：彩色圆点 + 文字方案，禁止彩色渐变徽章（仅状态提示小面积功能色）
  if (/(异常|拒绝|取消|无货|锁定|失败)/.test(text)) {
    return "border-danger/30 bg-danger/10 text-danger";
  }
  if (/(升级|高|紧急)/.test(text)) {
    return "border-warning/30 bg-warning/10 text-warning";
  }
  if (/(待|审核|处理|运输|派送|紧张|售后|预售|升级|备货)/.test(text)) {
    return "border-warning/30 bg-warning/10 text-warning";
  }
  if (/(完成|签收|通过|正常|有货|支付|收货|解决|上架)/.test(text)) {
    return "border-success/30 bg-success/10 text-success";
  }
  return "border-line bg-elevated text-secondary";
}

const PRODUCT_IMAGE_FALLBACK = "/products/placeholder.svg";

export function productImage(src?: string | null) {
  if (!src) return PRODUCT_IMAGE_FALLBACK;
  return src;
}
