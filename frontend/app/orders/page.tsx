"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import EmptyState from "@/components/platform/EmptyState";
import SiteShell from "@/components/platform/SiteShell";
import StatusBadge from "@/components/platform/StatusBadge";
import { commerceApi, getStoredUserId, Order } from "@/services/commerce";
import { formatCurrency, formatDate } from "@/services/format";

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);

  useEffect(() => {
    const userId = getStoredUserId();
    if (!userId) {
      window.location.href = "/login";
      return;
    }
    commerceApi.orders(userId).then(setOrders).catch(() => setOrders([]));
  }, []);

  return (
    <SiteShell>
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-black text-primary">订单中心</h1>
          <p className="mt-1 text-sm text-secondary">打开订单后，AI 客服会自动获得订单、商品、物流、退款和投诉上下文。</p>
        </div>
        <Link href="/products" className="app-button-secondary">继续购物</Link>
      </div>
      <div className="mt-5 space-y-3">
        {orders.map((order) => (
          <Link key={order.order_id} href={`/orders/${order.order_id}`} className="app-panel block p-4 transition hover:border-accent/60">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="text-base font-black text-primary">{order.order_id}</div>
                <div className="mt-1 text-sm text-secondary">
                  {order.items?.[0]?.product_name || "订单商品"} · {formatDate(order.created_at)}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <StatusBadge value={order.order_status} />
                  <StatusBadge value={order.shipping_status || order.logistics_status} />
                </div>
              </div>
              <div className="text-right">
                <div className="text-xl font-black tabular-nums text-primary">{formatCurrency(order.total_amount)}</div>
                <div className="mt-1 text-xs text-tertiary">查看详情 &gt;</div>
              </div>
            </div>
          </Link>
        ))}
        {orders.length === 0 && <EmptyState title="暂无订单" body="请先浏览商品并创建订单。" />}
      </div>
    </SiteShell>
  );
}
