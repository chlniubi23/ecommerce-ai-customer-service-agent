"use client";

import { useEffect, useState } from "react";
import AgentEntry from "@/components/platform/AgentEntry";
import SiteShell from "@/components/platform/SiteShell";
import StatusBadge from "@/components/platform/StatusBadge";
import { commerceApi, getStoredUserId, Order } from "@/services/commerce";
import { formatCurrency, formatDate } from "@/services/format";

export default function OrderDetailClient({ orderId }: { orderId: string }) {
  const [order, setOrder] = useState<Order | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [userId, setUserId] = useState("");
  const [refundMessage, setRefundMessage] = useState("");
  const [refundFailed, setRefundFailed] = useState(false);

  useEffect(() => {
    setUserId(getStoredUserId());
    commerceApi.order(orderId).then(setOrder).catch(() => {
      setOrder(null);
      setLoadError(true);
    });
  }, [orderId]);

  const applyRefund = async () => {
    try {
      const refund = await commerceApi.applyRefund(orderId, "用户从订单详情页申请退款");
      setRefundFailed(false);
      setRefundMessage(`退款单 ${refund.refund_id} 当前状态：${refund.refund_status}`);
    } catch (err) {
      setRefundFailed(true);
      setRefundMessage(`退款申请失败：${err instanceof Error ? err.message : "请稍后重试"}`);
    }
  };

  if (!order) {
    return (
      <SiteShell>
        <div className="app-card p-6">
          {loadError ? `订单 ${orderId} 加载失败，请确认订单号或稍后重试。` : "正在加载订单..."}
        </div>
      </SiteShell>
    );
  }

  return (
    <SiteShell>
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-black text-primary">{order.order_id}</h1>
          <p className="mt-1 text-sm text-secondary">从这里进入客服时，Agent 会自动获得完整订单上下文。</p>
        </div>
        <AgentEntry userId={userId || order.user_id} orderId={order.order_id} label="咨询此订单" />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.08fr_0.92fr]">
        <div className="space-y-5">
          <div className="app-card p-5">
            <div className="flex flex-wrap gap-2">
              <StatusBadge value={order.order_status} />
              <StatusBadge value={order.payment_status} />
              <StatusBadge value={order.shipping_status} />
              <StatusBadge value={order.receipt_status} />
            </div>
            <div className="mt-4 text-3xl font-black tabular-nums text-primary">{formatCurrency(order.total_amount)}</div>
            <div className="mt-1 text-sm text-secondary">下单时间：{formatDate(order.created_at)}</div>
          </div>

          <div className="app-panel p-5">
            <h2 className="font-black text-primary">订单商品</h2>
            <div className="mt-3 space-y-3">
              {order.items.map((item) => (
                <div key={item.order_item_id} className="flex justify-between gap-3 rounded-xl border border-line bg-elevated p-4">
                  <div>
                    <div className="font-bold text-primary">{item.product_name}</div>
                    <div className="mt-1 text-sm text-secondary">{item.sku_id} × {item.quantity}</div>
                  </div>
                  <div className="font-black tabular-nums text-primary">{formatCurrency(item.line_amount)}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="app-panel p-5">
            <h2 className="font-black text-primary">售后操作</h2>
            <p className="mt-1 text-sm text-secondary">这里会创建或读取真实退款记录，并可交给 Refund Agent 继续处理。</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button onClick={applyRefund} className="app-button">
                申请退款
              </button>
              <AgentEntry userId={userId || order.user_id} orderId={order.order_id} label="咨询退款Agent" />
            </div>
            {refundMessage && <div className={`mt-3 rounded-xl border p-3 text-sm ${refundFailed ? "border-danger/30 bg-danger/10 text-danger" : "border-success/30 bg-success/10 text-success"}`}>{refundMessage}</div>}
          </div>
        </div>

        <div className="space-y-5">
          <div className="app-card p-5">
            <h2 className="font-black text-primary">物流信息</h2>
            {order.logistics ? (
              <>
                <div className="mt-3 flex flex-wrap gap-2">
                  <StatusBadge value={order.logistics.current_status} />
                  <span className="rounded-full border border-line bg-elevated px-3 py-1 text-xs text-secondary">{order.logistics.carrier_name} / {order.logistics.tracking_no}</span>
                </div>
                <div className="mt-3 text-sm text-secondary">当前位置：{order.logistics.current_location}</div>
                <div className="mt-1 text-sm text-secondary">预计送达：{formatDate(order.logistics.estimated_delivery_at)}</div>
                <div className="mt-4 space-y-3">
                  {(order.logistics.timeline || []).map((event) => (
                    <div key={event.event_id} className="relative border-l-2 border-line pl-4 text-sm">
                      <div className="absolute -left-[5px] top-1 h-2 w-2 rounded-full bg-accent" />
                      <div className="font-bold text-primary">{event.status}</div>
                      <div className="text-tertiary">{event.location} / {formatDate(event.event_time)}</div>
                      <div className="text-secondary">{event.description}</div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="mt-2 text-sm text-secondary">暂无物流数据。</p>
            )}
          </div>

          <div className="app-panel p-5">
            <h2 className="font-black text-primary">收货地址</h2>
            <div className="mt-3 text-sm leading-7 text-secondary">
              <div>{order.receiver_name} / {order.receiver_phone}</div>
              <div>{order.province} {order.city} {order.district}</div>
              <div>{order.address_line}</div>
            </div>
          </div>
        </div>
      </div>
    </SiteShell>
  );
}
