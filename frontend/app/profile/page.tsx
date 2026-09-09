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
            <div className="bg-gradient-to-r from-[#edf5ff] to-white p-6">
              <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-4">
                  <div className="grid h-16 w-16 place-items-center rounded-full bg-white text-2xl font-black text-[#ff2442] shadow-sm">
                    {user.full_name.slice(0, 1)}
                  </div>
                  <div>
                    <div className="text-sm text-slate-500">Hello，{user.full_name}</div>
                    <h1 className="mt-1 text-2xl font-black">个人中心</h1>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <StatusBadge value={user.status} />
                      <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-500">ID {user.user_id}</span>
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
                <div key={label} className="rounded-2xl bg-[#fafafa] p-4 text-center">
                  <div className="text-2xl font-black">{value}</div>
                  <div className="mt-1 text-sm text-slate-500">{label}</div>
                </div>
              ))}
            </div>
          </section>

          <div className="grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
            <div className="app-panel p-5">
              <h2 className="font-black">账户信息</h2>
              <div className="mt-4 space-y-3 text-sm text-slate-600">
                <div>邮箱：{user.email}</div>
                <div>手机：{user.phone}</div>
                <div>最近登录：{formatDate(user.last_login_at)}</div>
              </div>
              <h3 className="mt-6 font-black">收货地址</h3>
              <div className="mt-3 space-y-3">
                {(user.addresses || []).map((address) => (
                  <div key={address.address_id} className="rounded-2xl border border-slate-100 bg-[#fafafa] p-4 text-sm text-slate-600">
                    <div className="font-bold text-slate-900">{address.receiver_name} / {address.phone}</div>
                    <div className="mt-1">{address.province} {address.city} {address.district}</div>
                    <div>{address.address_line}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="app-panel p-5">
              <div className="flex items-center justify-between">
                <h2 className="font-black">最近订单</h2>
                <Link href="/orders" className="text-sm font-bold text-[#ff2442]">全部订单 &gt;</Link>
              </div>
              <div className="mt-3 space-y-3">
                {orders.slice(0, 6).map((order) => (
                  <Link key={order.order_id} href={`/orders/${order.order_id}`} className="block rounded-2xl border border-slate-100 p-4 transition hover:bg-pink-50/40">
                    <div className="flex justify-between gap-3">
                      <span className="font-bold">{order.order_id}</span>
                      <span className="font-black text-[#ff2442]">{formatCurrency(order.total_amount)}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <StatusBadge value={order.order_status} />
                      <StatusBadge value={order.shipping_status} />
                    </div>
                    <div className="mt-2 text-xs text-slate-400">{formatDate(order.created_at)}</div>
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
