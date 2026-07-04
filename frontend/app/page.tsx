"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import AgentEntry from "@/components/platform/AgentEntry";
import SiteShell from "@/components/platform/SiteShell";
import { commerceApi, getStoredUserId, Product } from "@/services/commerce";
import { formatCurrency, productImage } from "@/services/format";

const channels = [
  { label: "百亿补贴", href: "/products", icon: "补" },
  { label: "低价秒杀", href: "/products", icon: "秒" },
  { label: "超值购", href: "/products", icon: "值" },
  { label: "品牌馆", href: "/products", icon: "牌" },
  { label: "订单", href: "/orders", icon: "单" },
  { label: "售后", href: "/after-sales", icon: "退" },
  { label: "投诉", href: "/complaints", icon: "诉" },
  { label: "AI导购", href: "", icon: "AI", agent: true },
];

const fallbackCards = [
  "星耀 X1 Pro 5G 手机 · 直播间秒杀价",
  "云感降噪 Pro 耳机 · 通勤降噪之选",
  "轻居智能扫地机器人 · 扫拖一体",
  "悦己修护水乳礼盒 · 保湿修护",
];

export default function Home() {
  const [stats, setStats] = useState<{
    products: { count: number };
    orders: { count: number };
    refunds: { count: number };
    complaints: { count: number };
  } | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [userId, setUserId] = useState("");

  useEffect(() => {
    setUserId(getStoredUserId());
    commerceApi.dashboard().then(setStats).catch(() => setStats(null));
    commerceApi.products("", "").then((items) => setProducts(items.slice(0, 12))).catch(() => setProducts([]));
  }, []);

  const marketStats = useMemo(
    () => [
      { label: "商品", value: stats?.products.count ?? "--" },
      { label: "订单", value: stats?.orders.count ?? "--" },
      { label: "退款", value: stats?.refunds.count ?? "--" },
      { label: "投诉", value: stats?.complaints.count ?? "--" },
    ],
    [stats],
  );

  const dealProducts = products.slice(0, 4);

  return (
    <SiteShell>
      <section className="overflow-hidden rounded-[28px] bg-gradient-to-br from-[#15151f] via-[#201522] to-[#ff2442] p-4 text-white shadow-[0_24px_70px_rgba(255,36,66,0.22)] md:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-stretch">
          <div className="flex min-w-0 flex-1 flex-col justify-between">
            <div>
              <div className="inline-flex rounded-full bg-white/12 px-3 py-1 text-xs font-bold text-white/85">ShopEase 抖音商城风格</div>
              <h1 className="mt-4 max-w-2xl text-4xl font-black leading-tight md:text-6xl">
                边逛边问，AI 导购帮你把服务接住
              </h1>
              <p className="mt-4 max-w-xl text-sm leading-7 text-white/75 md:text-base">
                逛商城、查订单、追物流、退款、投诉，一句话交给 AI 导购。它不只是回答，而是直接帮你把售后单据、投诉工单、人工转接都办好。
              </p>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/products" className="inline-flex items-center justify-center rounded-full bg-white px-6 py-3 text-sm font-black text-[#ff2442] shadow-lg transition hover:-translate-y-0.5">
                逛商城
              </Link>
              <AgentEntry userId={userId || undefined} label="问AI导购" />
            </div>
          </div>

          <div className="relative min-h-[260px] overflow-hidden rounded-[24px] bg-white/10 lg:w-[370px]">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(255,255,255,0.28),transparent_45%)]" />
            <img
              src="/assistant/ai-assistant-avatar.png"
              alt="ShopEase AI 助手"
              className="assistant-avatar-float absolute bottom-0 left-1/2 h-[300px] w-[300px] -translate-x-1/2 object-contain"
            />
            <div className="absolute bottom-4 left-4 right-4 rounded-2xl bg-white/92 p-3 text-slate-950 shadow-xl backdrop-blur">
              <div className="text-xs font-bold text-[#ff2442]">AI 导购在线</div>
              <div className="mt-1 text-sm font-black">咨询商品、订单、物流、退款都可以</div>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-4 rounded-[24px] bg-white p-4 shadow-[0_14px_40px_rgba(15,23,42,0.06)]">
        <div className="flex items-center rounded-full bg-[#f5f5f6] px-4 py-3">
          <span className="mr-2 text-[#ff2442]">⌕</span>
          <Link href="/products" className="flex-1 text-sm font-semibold text-slate-400">
            搜索商品、品牌、售后问题
          </Link>
          <span className="rounded-full bg-[#ff2442] px-4 py-1.5 text-xs font-black text-white">搜索</span>
        </div>

        <div className="mt-4 grid grid-cols-4 gap-3 md:grid-cols-8">
          {channels.map((item) => (
            item.agent ? (
              <button
                key={item.label}
                type="button"
                onClick={() => window.dispatchEvent(new CustomEvent("commerce:open-agent", { detail: { user_id: userId || undefined } }))}
                className="group text-center"
              >
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-[#fff1f3] to-[#fff7ed] text-sm font-black text-[#ff2442] transition group-hover:-translate-y-0.5">
                  {item.icon}
                </div>
                <div className="mt-2 text-xs font-semibold text-slate-700">{item.label}</div>
              </button>
            ) : (
            <Link key={item.label} href={item.href} className="group text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-[#fff1f3] to-[#fff7ed] text-sm font-black text-[#ff2442] transition group-hover:-translate-y-0.5">
                {item.icon}
              </div>
              <div className="mt-2 text-xs font-semibold text-slate-700">{item.label}</div>
            </Link>
            )
          ))}
        </div>
      </section>

      <section className="mt-4 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-[24px] bg-gradient-to-r from-[#fff1f3] via-white to-[#fff7ed] p-5 shadow-[0_14px_40px_rgba(255,36,66,0.08)]">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-black text-[#ff2442]">低价秒杀</div>
              <h2 className="mt-1 text-2xl font-black text-slate-950">今日超值推荐</h2>
            </div>
            <Link href="/products" className="rounded-full bg-slate-950 px-4 py-2 text-xs font-bold text-white">
              更多
            </Link>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {dealProducts.length > 0 ? dealProducts.map((product) => (
              <Link key={product.product_id} href={`/products/${product.product_id}`} className="overflow-hidden rounded-2xl bg-white shadow-sm transition hover:-translate-y-0.5">
                <div className="relative aspect-square bg-slate-100">
                  <Image src={productImage(product.images?.[0]?.image_url)} alt={product.product_name} fill className="object-cover" sizes="180px" unoptimized />
                </div>
                <div className="p-3">
                  <div className="line-clamp-1 text-xs font-bold text-slate-800">{product.product_name}</div>
                  <div className="mt-1 text-base font-black text-[#ff2442]">{formatCurrency(product.price)}</div>
                </div>
              </Link>
            )) : fallbackCards.map((item) => (
              <div key={item} className="rounded-2xl border border-dashed border-pink-100 bg-white/70 p-4 text-sm font-semibold leading-6 text-slate-500">
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[24px] bg-white p-5 shadow-[0_14px_40px_rgba(15,23,42,0.06)]">
          <div className="text-sm font-black text-slate-950">业务数据面板</div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {marketStats.map((item) => (
              <div key={item.label} className="rounded-2xl bg-[#f7f7f8] p-4">
                <div className="text-2xl font-black text-slate-950">{item.value}</div>
                <div className="mt-1 text-xs font-semibold text-slate-500">{item.label}</div>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-2xl bg-slate-950 p-4 text-white">
            <div className="text-xs font-bold text-white/60">全链路真实数据</div>
            <div className="mt-1 text-sm font-black">商品、订单、物流、退款、投诉均由 MySQL 真实驱动，AI 导购直接读写业务库。</div>
          </div>
        </div>
      </section>

      <section className="mt-6">
        <div className="flex items-end justify-between">
          <div>
            <h2 className="text-2xl font-black">猜你喜欢</h2>
            <p className="mt-1 text-sm text-slate-500">AI 导购基于你的浏览与购买记录做个性化推荐。</p>
          </div>
          <Link href="/products" className="text-sm font-black text-[#ff2442]">进入商城 &gt;</Link>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {products.length > 0 ? products.map((product) => (
            <Link key={product.product_id} href={`/products/${product.product_id}`} className="overflow-hidden rounded-[18px] bg-white shadow-[0_10px_30px_rgba(15,23,42,0.06)] transition hover:-translate-y-0.5">
              <div className="relative aspect-[3/4] bg-gradient-to-b from-slate-50 to-slate-100">
                <Image src={productImage(product.images?.[0]?.image_url)} alt={product.product_name} fill className="object-cover" sizes="25vw" unoptimized />
              </div>
              <div className="p-3">
                <div className="line-clamp-2 min-h-10 text-sm font-bold leading-5 text-slate-950">{product.product_name}</div>
                <div className="mt-2 flex items-end justify-between">
                  <div className="text-lg font-black text-[#ff2442]">{formatCurrency(product.price)}</div>
                  <div className="text-xs text-slate-400">已售 1.2万+</div>
                </div>
              </div>
            </Link>
          )) : (
            <div className="col-span-full rounded-[24px] border border-dashed border-pink-100 bg-white p-8 text-center">
              <div className="text-lg font-black text-slate-950">商品加载中</div>
              <p className="mt-2 text-sm text-slate-500">正在从业务数据库读取商品，稍候片刻即可看到最新在售商品。</p>
            </div>
          )}
        </div>
      </section>
    </SiteShell>
  );
}
