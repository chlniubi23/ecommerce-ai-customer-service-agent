"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AgentEntry from "@/components/platform/AgentEntry";
import EmptyState from "@/components/platform/EmptyState";
import SiteShell from "@/components/platform/SiteShell";
import StatusBadge from "@/components/platform/StatusBadge";
import { commerceApi, DemoUser, getStoredUserId, Order } from "@/services/commerce";
import { formatCurrency, formatDate } from "@/services/format";

export default function ProfilePage() {
  const [user, setUser] = useState<DemoUser | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);

  useEffect(() => {
    const userId = getStoredUserId();
    if (!userId) {
      window.location.href = "/login";
      return;
    }
    commerceApi.getUser(userId).then(setUser);
    commerceApi.orders(userId).then(setOrders).catch(() => setOrders([]));
  }, []);

  return (
    <SiteShell>
      {user ? (
        <div className="space-y-5">
          <section className="app-card overflow-hidden">
            <div className="relative overflow-hidden bg-elevated p-6">
              <div className="pointer-events-none absolute -top-20 right-0 h-40 w-72 rounded-full bg-accent/10 blur-3xl" />
              <div className="relative flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-4">
                  <div className="grid h-16 w-16 place-items-center rounded-full bg-accent-gradient text-2xl font-black text-white shadow-accent-glow">
                    {user.full_name.slice(0, 1)}
                  </div>
                  <div>
                    <div className="text-sm text-secondary">Hello，{user.full_name}</div>
                    <h1 className="mt-1 text-2xl font-black text-primary">个人中心</h1>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <StatusBadge value={user.status} />
                      <span className="rounded-full border border-line bg-surface px-3 py-1 text-xs text-secondary">ID {user.user_id}</span>
                    </div>
                  </div>
                </div>
                <AgentEntry userId={user.user_id} label="带用户上下文咨询" />
              </div>
            </div>
            <div className="grid gap-4 p-5 sm:grid-cols-4">
              {[
                ["我的订单", orders.length],
                ["待处理", orders.filter((item) => item.order_status.includes("待") || item.shipping_status.includes("待")).length],
                ["物流中", orders.filter((item) => item.shipping_status.includes("运输") || item.shipping_status.includes("发货")).length],
                ["售后相关", orders.filter((item) => item.order_status.includes("售后")).length],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl bg-elevated p-4 text-center">
                  <div className="text-2xl font-black tabular-nums text-primary">{value}</div>
                  <div className="mt-1 text-sm text-secondary">{label}</div>
                </div>
              ))}
            </div>
          </section>

          <div className="grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
            <div className="app-panel p-5">
              <h2 className="font-black text-primary">账户信息</h2>
              <div className="mt-4 space-y-3 text-sm text-secondary">
                <div>邮箱：{user.email}</div>
                <div>手机：{user.phone}</div>
                <div>最近登录：{formatDate(user.last_login_at)}</div>
              </div>
              <h3 className="mt-6 font-black text-primary">收货地址</h3>
              <div className="mt-3 space-y-3">
                {(user.addresses || []).map((address) => (
                  <div key={address.address_id} className="rounded-xl border border-line bg-elevated p-4 text-sm text-secondary">
                    <div className="font-bold text-primary">{address.receiver_name} / {address.phone}</div>
                    <div className="mt-1">{address.province} {address.city} {address.district}</div>
                    <div>{address.address_line}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="app-panel p-5">
              <div className="flex items-center justify-between">
                <h2 className="font-black text-primary">最近订单</h2>
                <Link href="/orders" className="ai-link text-sm font-bold">全部订单 &gt;</Link>
              </div>
              <div className="mt-3 space-y-3">
                {orders.slice(0, 6).map((order) => (
                  <Link key={order.order_id} href={`/orders/${order.order_id}`} className="block rounded-xl border border-line bg-elevated p-4 transition hover:border-accent/60">
                    <div className="flex justify-between gap-3">
                      <span className="font-bold text-primary">{order.order_id}</span>
                      <span className="font-black tabular-nums text-primary">{formatCurrency(order.total_amount)}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <StatusBadge value={order.order_status} />
                      <StatusBadge value={order.shipping_status} />
                    </div>
                    <div className="mt-2 text-xs text-tertiary">{formatDate(order.created_at)}</div>
                  </Link>
                ))}
                {orders.length === 0 && <EmptyState title="暂无订单" body="从商品详情页创建订单后，这里会自动显示。" />}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="app-card p-6">正在加载个人信息...</div>
      )}
    </SiteShell>
  );
}
