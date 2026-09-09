"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AgentEntry from "@/components/platform/AgentEntry";
import EmptyState from "@/components/platform/EmptyState";
import SiteShell from "@/components/platform/SiteShell";
import StatusBadge from "@/components/platform/StatusBadge";
import { commerceApi, Complaint, getStoredUserId, Order } from "@/services/commerce";
import { formatDate } from "@/services/format";

export default function ComplaintsPage() {
  const [userId, setUserId] = useState("");
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [orderId, setOrderId] = useState("");
  const [content, setContent] = useState("");
  const [complaintType, setComplaintType] = useState("服务体验");
  const [message, setMessage] = useState("");

  const load = (id: string) => {
    commerceApi.complaints(id).then(setComplaints).catch(() => setComplaints([]));
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
    if (!content) return;
    try {
      const complaint = await commerceApi.createComplaint({
        user_id: userId,
        order_id: orderId || undefined,
        complaint_type: complaintType,
        content,
      });
      setMessage(`投诉单 ${complaint.complaint_id} 已提交`);
      setContent("");
      load(userId);
    } catch (err) {
      setMessage(`投诉提交失败：${err instanceof Error ? err.message : "请稍后重试"}`);
    }
  };

  return (
    <SiteShell>
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-black">投诉中心</h1>
          <p className="mt-1 text-sm text-slate-500">投诉、处理记录和 Supervisor 升级信息全部来自数据库。</p>
        </div>
        <AgentEntry userId={userId || undefined} label="咨询投诉Agent" />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="app-card p-5">
          <h2 className="font-black">提交投诉</h2>
          <div className="mt-4 space-y-3">
            <select className="app-input w-full" value={orderId} onChange={(e) => setOrderId(e.target.value)}>
              <option value="">不关联订单</option>
              {orders.map((order) => (
                <option key={order.order_id} value={order.order_id}>{order.order_id}</option>
              ))}
            </select>
            <select className="app-input w-full" value={complaintType} onChange={(e) => setComplaintType(e.target.value)}>
              <option value="服务体验">服务体验</option>
              <option value="物流问题">物流问题</option>
              <option value="退款问题">退款问题</option>
              <option value="商品质量">商品质量</option>
            </select>
            <textarea className="app-input min-h-28 w-full" value={content} onChange={(e) => setContent(e.target.value)} placeholder="请描述你遇到的问题" />
            <button onClick={submit} className="app-button">提交投诉</button>
            {message && <div className={`rounded-xl border p-3 text-sm ${message.includes("失败") ? "border-red-100 bg-red-50 text-red-600" : "border-emerald-100 bg-emerald-50 text-emerald-700"}`}>{message}</div>}
          </div>
        </div>
        <div className="space-y-3">
          {complaints.map((complaint) => (
            <div key={complaint.complaint_id} className="app-panel p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="font-black">{complaint.complaint_id}</div>
                  {complaint.order_id && <Link href={`/orders/${complaint.order_id}`} className="text-sm font-semibold text-[#ff2442]">{complaint.order_id}</Link>}
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge value={complaint.complaint_status} />
                  <StatusBadge value={complaint.priority} />
                </div>
              </div>
              <div className="mt-3 text-sm leading-6 text-slate-600">{complaint.content}</div>
              <div className="mt-2 text-xs text-slate-400">{formatDate(complaint.created_at)}</div>
              {(complaint.escalations || []).length > 0 && (
                <div className="mt-3 rounded-2xl border border-pink-100 bg-pink-50 p-3 text-sm text-[#ff2442]">
                  已升级至 Supervisor：{complaint.escalations?.[0]?.escalation_status}
                </div>
              )}
            </div>
          ))}
          {complaints.length === 0 && <EmptyState title="暂无投诉记录" body="提交一条投诉后即可演示 Complaint Agent 和 Supervisor 升级流程。" />}
        </div>
      </div>
    </SiteShell>
  );
}
