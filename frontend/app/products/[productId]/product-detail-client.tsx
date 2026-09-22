"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import AgentEntry from "@/components/platform/AgentEntry";
import SiteShell from "@/components/platform/SiteShell";
import StatusBadge from "@/components/platform/StatusBadge";
import { commerceApi, getStoredUserId, Product } from "@/services/commerce";
import { formatCurrency, productImage } from "@/services/format";

export default function ProductDetailClient({ productId }: { productId: string }) {
  const [product, setProduct] = useState<Product | null>(null);
  const [userId, setUserId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setUserId(getStoredUserId());
    commerceApi.product(productId).then(setProduct).catch(() => setProduct(null));
  }, [productId]);

  const createOrder = async () => {
    if (!userId) {
      window.location.href = "/login";
      return;
    }
    try {
      const order = await commerceApi.createOrder(userId, productId, quantity);
      setMessage(`订单 ${order.order_id} 已创建`);
      window.location.href = `/orders/${order.order_id}`;
    } catch (err) {
      setMessage(`下单失败：${err instanceof Error ? err.message : "请稍后重试"}`);
    }
  };

  if (!product) {
    return (
      <SiteShell>
        <div className="app-card p-6">正在加载商品...</div>
      </SiteShell>
    );
  }

  const mainImage = productImage(product.images?.[0]?.image_url);

  return (
    <SiteShell>
      <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="app-card p-5">
          <div className="relative aspect-square overflow-hidden rounded-xl bg-elevated">
            <Image src={mainImage} alt={product.product_name} fill className="object-cover" sizes="50vw" unoptimized />
          </div>
          <div className="mt-4 grid grid-cols-4 gap-3">
            {[1, 2, 3, 4].map((item) => (
              <div key={item} className="relative aspect-square overflow-hidden rounded-xl border border-line bg-elevated">
                <Image src={mainImage} alt={`${product.product_name}-${item}`} fill className="object-cover" sizes="120px" unoptimized />
              </div>
            ))}
          </div>
        </div>

        <div className="app-card p-6">
          <div className="flex flex-wrap gap-2">
            <StatusBadge value={product.product_status} />
            <StatusBadge value={product.inventory_status} />
          </div>
          <h1 className="mt-4 text-3xl font-black leading-tight text-primary">{product.product_name}</h1>
          <p className="mt-3 text-sm leading-7 text-secondary">{product.description}</p>
          <div className="mt-5 flex items-end gap-3">
            <div className="text-3xl font-black tabular-nums text-primary">{formatCurrency(product.price)}</div>
            <div className="pb-1 text-sm text-tertiary">库存 {product.available_quantity ?? 0} 件</div>
          </div>

          <div className="mt-6 grid gap-3 md:grid-cols-3">
            <div className="rounded-xl bg-elevated p-4">
              <div className="text-xs text-secondary">品牌</div>
              <div className="mt-1 font-bold text-primary">{product.brand_name}</div>
            </div>
            <div className="rounded-xl bg-elevated p-4">
              <div className="text-xs text-secondary">分类</div>
              <div className="mt-1 font-bold text-primary">{product.category_name}</div>
            </div>
            <div className="rounded-xl bg-elevated p-4">
              <div className="text-xs text-secondary">SKU</div>
              <div className="mt-1 font-bold text-primary">{product.sku_id}</div>
            </div>
          </div>

          <div className="mt-6 app-panel p-5 shadow-none">
            <h2 className="font-black text-primary">规格参数</h2>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {Object.entries(product.attributes || {}).map(([key, value]) => (
                <div key={key} className="flex justify-between border-b border-line py-2 text-sm">
                  <span className="text-secondary">{key}</span>
                  <span className="font-medium text-primary">{String(value)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <div className="flex items-center overflow-hidden rounded-xl border border-line bg-elevated">
              <button className="px-3 py-2 text-secondary transition hover:text-primary" onClick={() => setQuantity(Math.max(1, quantity - 1))}>-</button>
              <input
                className="w-14 border-x border-line bg-transparent px-2 py-2 text-center text-primary outline-none"
                type="number"
                min={1}
                max={20}
                value={quantity}
                onChange={(e) => setQuantity(Number(e.target.value))}
              />
              <button className="px-3 py-2 text-secondary transition hover:text-primary" onClick={() => setQuantity(Math.min(20, quantity + 1))}>+</button>
            </div>
            <button onClick={createOrder} className="app-button px-8">
              立即下单
            </button>
            <AgentEntry userId={userId || undefined} productId={product.product_id} label="咨询此商品" />
          </div>
          {message && <div className={`mt-4 rounded-xl border p-3 text-sm ${message.startsWith("下单失败") ? "border-danger/30 bg-danger/10 text-danger" : "border-success/30 bg-success/10 text-success"}`}>{message}</div>}
        </div>
      </div>
    </SiteShell>
  );
}
