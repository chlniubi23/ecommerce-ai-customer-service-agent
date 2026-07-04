"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import AgentEntry from "@/components/platform/AgentEntry";
import EmptyState from "@/components/platform/EmptyState";
import SiteShell from "@/components/platform/SiteShell";
import StatusBadge from "@/components/platform/StatusBadge";
import { Category, commerceApi, getStoredUserId, Product } from "@/services/commerce";
import { formatCurrency, productImage } from "@/services/format";

const sortTabs = ["综合", "销量", "价格", "新品"];

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [keyword, setKeyword] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [userId, setUserId] = useState("");

  const load = (nextCategoryId = categoryId) => {
    commerceApi.products(keyword, nextCategoryId).then(setProducts).catch(() => setProducts([]));
  };

  useEffect(() => {
    setUserId(getStoredUserId());
    commerceApi.categories().then(setCategories).catch(() => setCategories([]));
    commerceApi.products().then(setProducts).catch(() => setProducts([]));
  }, []);

  return (
    <SiteShell>
      <section className="rounded-[28px] bg-gradient-to-r from-[#ff2442] via-[#ff4d67] to-[#ff7a18] p-5 text-white shadow-[0_18px_55px_rgba(255,36,66,0.22)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="text-sm font-bold text-white/75">ShopEase Mall</div>
            <h1 className="mt-1 text-3xl font-black">商城频道</h1>
            <p className="mt-2 text-sm text-white/78">真实类目、品牌、价格、库存与商品图，均由业务数据库实时驱动。</p>
          </div>
          <AgentEntry userId={userId || undefined} label="AI帮我挑" />
        </div>
        <div className="mt-5 flex items-center rounded-full bg-white p-1.5">
          <input
            className="min-w-0 flex-1 rounded-full px-4 py-2 text-sm font-semibold text-slate-700 outline-none placeholder:text-slate-400"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") load();
            }}
            placeholder="搜商品、品牌、SKU 或分类"
          />
          <button onClick={() => load()} className="rounded-full bg-slate-950 px-6 py-2 text-sm font-black text-white">
            搜索
          </button>
        </div>
      </section>

      <section className="mt-4 rounded-[24px] bg-white p-4 shadow-[0_14px_40px_rgba(15,23,42,0.06)]">
        <div className="flex gap-2 overflow-x-auto pb-1">
          <button
            onClick={() => {
              setCategoryId("");
              load("");
            }}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-black ${!categoryId ? "bg-[#ff2442] text-white" : "bg-[#f5f5f6] text-slate-600"}`}
          >
            全部
          </button>
          {categories.map((category) => (
            <button
              key={category.category_id}
              onClick={() => {
                setCategoryId(category.category_id);
                load(category.category_id);
              }}
              className={`shrink-0 rounded-full px-4 py-2 text-sm font-black ${categoryId === category.category_id ? "bg-[#ff2442] text-white" : "bg-[#f5f5f6] text-slate-600"}`}
            >
              {category.category_name}
            </button>
          ))}
        </div>
      </section>

      <section className="mt-4 flex gap-2 overflow-x-auto">
        {sortTabs.map((tab, index) => (
          <button key={tab} className={`shrink-0 rounded-full px-4 py-2 text-sm font-bold ${index === 0 ? "bg-slate-950 text-white" : "bg-white text-slate-600"}`}>
            {tab}
          </button>
        ))}
      </section>

      <section className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {products.map((product) => (
          <div key={product.product_id} className="overflow-hidden rounded-[18px] bg-white shadow-[0_10px_30px_rgba(15,23,42,0.06)] transition hover:-translate-y-0.5">
            <Link href={`/products/${product.product_id}`} className="relative block aspect-[3/4] bg-gradient-to-b from-slate-50 to-slate-100">
              <Image
                src={productImage(product.images?.[0]?.image_url)}
                alt={product.product_name}
                fill
                className="object-cover transition hover:scale-[1.02]"
                sizes="25vw"
                unoptimized
              />
              <span className="absolute left-2 top-2 rounded-full bg-[#ff2442] px-2 py-1 text-[11px] font-black text-white">热卖</span>
            </Link>
            <div className="p-3">
              <div className="text-xs font-bold text-[#ff2442]">{product.brand_name} · {product.category_name}</div>
              <Link href={`/products/${product.product_id}`} className="mt-2 block line-clamp-2 min-h-10 text-sm font-black leading-5 text-slate-950">
                {product.product_name}
              </Link>
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{product.description}</p>
              <div className="mt-3 flex items-end justify-between">
                <div className="text-xl font-black text-[#ff2442]">{formatCurrency(product.price)}</div>
                <div className="text-xs text-slate-400">可售 {product.available_quantity ?? 0}</div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <StatusBadge value={product.product_status} />
                <StatusBadge value={product.inventory_status} />
              </div>
              <div className="mt-4 grid grid-cols-[1fr_auto] gap-2">
                <Link href={`/products/${product.product_id}`} className="inline-flex items-center justify-center rounded-full bg-[#f5f5f6] px-4 py-2 text-sm font-black text-slate-700">
                  详情
                </Link>
                <AgentEntry userId={userId || undefined} productId={product.product_id} label="问AI" />
              </div>
            </div>
          </div>
        ))}
      </section>

      {products.length === 0 && (
        <div className="mt-4">
          <EmptyState title="没有找到匹配的商品" body="换个关键词或切换分类试试，也可以点右上角「AI帮我挑」，让 AI 导购根据你的需求推荐。" />
        </div>
      )}
    </SiteShell>
  );
}
