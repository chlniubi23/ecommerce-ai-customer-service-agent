"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AgentEntry from "@/components/platform/AgentEntry";
import EmptyState from "@/components/platform/EmptyState";
import SiteShell from "@/components/platform/SiteShell";
import StatusBadge from "@/components/platform/StatusBadge";
import { commerceApi, getStoredUserId, Order, Refund } from "@/services/commerce";
import { formatCurrency, formatDate } from "@/services/format";

export default function AfterSalesPage() {
  const [userId, setUserId] = useState("");
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [selectedOrder, setSelectedOrder] = useState("");
  const [reason, setReason] = useState("商品质量问题");
  const [message, setMessage] = useState("");

  const load = (id: string) => {
    commerceApi.refunds(id).then(setRefunds).catch(() => setRefunds([]));
    commerceApi.orders(id).then(setOrders).catch(() => setOrders([]));
  };

  useEffect(() => {
    const id = getStoredUserId();
    if (!id) {
      window.location.href = "/login";
      return;
    }
    setUserId(id);
    load(id);
  }, []);

  const submit = async () => {
    if (!selectedOrder) return;
    try {
      const refund = await commerceApi.applyRefund(selectedOrder, reason);
      setMessage(`退款单 ${refund.refund_id} 已提交，当前状态：${refund.refund_status}`);
      load(userId);
    } catch (err) {
      setMessage(`退款申请失败：${err instanceof Error ? err.message : "请稍后重试"}`);
    }
  };

  return (
    <SiteShell>
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-black">售后中心</h1>
          <p className="mt-1 text-sm text-slate-500">退款记录、审核状态和进度均来自真实数据库。</p>
        </div>
        <AgentEntry userId={userId || undefined} label="咨询退款Agent" />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="app-card p-5">
          <h2 className="font-black">申请退款</h2>
          <div className="mt-4 space-y-3">
            <select className="app-input w-full" value={selectedOrder} onChange={(e) => setSelectedOrder(e.target.value)}>
              <option value="">选择订单</option>
              {orders.map((order) => (
                <option key={order.order_id} value={order.order_id}>{order.order_id} / {formatCurrency(order.total_amount)}</option>
              ))}
            </select>
            <input className="app-input w-full" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="退款原因" />
            <button onClick={submit} className="app-button">提交退款申请</button>
            {message && <div className={`rounded-xl border p-3 text-sm ${message.includes("失败") ? "border-red-100 bg-red-50 text-red-600" : "border-emerald-100 bg-emerald-50 text-emerald-700"}`}>{message}</div>}
          </div>
        </div>
        <div className="space-y-3">
          {refunds.map((refund) => (
            <div key={refund.refund_id} className="app-panel p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="font-black">{refund.refund_id}</div>
                  <Link href={`/orders/${refund.order_id}`} className="text-sm font-semibold text-[#ff2442]">{refund.order_id}</Link>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge value={refund.audit_status} />
                  <StatusBadge value={refund.refund_status} />
                </div>
              </div>
              <div className="mt-3 text-sm text-slate-600">{refund.refund_reason}</div>
              <div className="mt-2 flex items-center justify-between">
                <span className="text-xs text-slate-400">{formatDate(refund.created_at)}</span>
                <span className="font-black text-[#ff2442]">{formatCurrency(refund.refund_amount)}</span>
              </div>
            </div>
          ))}
          {refunds.length === 0 && <EmptyState title="暂无退款记录" body="可以在这里或订单详情页发起退款申请。" />}
        </div>
      </div>
    </SiteShell>
  );
}
