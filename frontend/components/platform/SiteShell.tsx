"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { clearStoredUser, commerceApi, DemoUser, getStoredUserId } from "@/services/commerce";

const navItems = [
  { href: "/", label: "首页" },
  { href: "/products", label: "商城" },
  { href: "/orders", label: "订单" },
  { href: "/after-sales", label: "售后" },
  { href: "/complaints", label: "投诉" },
  { href: "/metrics", label: "📊 指标" },
];

export default function SiteShell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<DemoUser | null>(null);

  useEffect(() => {
    const userId = getStoredUserId();
    if (!userId) return;
    commerceApi.getUser(userId).then(setUser).catch(() => clearStoredUser());
  }, []);

  const logout = () => {
    clearStoredUser();
    setUser(null);
    window.location.href = "/";
  };

  return (
    <div className="min-h-screen text-slate-950">
      <header className="sticky top-0 z-40 border-b border-pink-100/70 bg-white/95 shadow-[0_10px_30px_rgba(236,72,153,0.05)] backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
          <Link href="/" className="flex shrink-0 items-center gap-2">
            <div className="relative grid h-10 w-10 place-items-center overflow-hidden rounded-2xl bg-gradient-to-br from-[#ff2442] to-[#ff7a18] text-base font-black text-white shadow-[0_10px_24px_rgba(255,36,66,0.24)]">
              小
              <span className="absolute -right-2 -top-2 h-5 w-5 rounded-full bg-white/25" />
            </div>
            <div>
              <div className="text-base font-black leading-tight">
                <span className="text-[#ff2442]">小易</span>电商助手
              </div>
              <div className="text-[11px] text-slate-400">抖音商城风格电商平台</div>
            </div>
          </Link>

          <div className="hidden min-w-0 flex-1 items-center rounded-full border border-pink-100 bg-[#fff7fa] px-4 py-2 text-sm text-slate-400 md:flex">
            <span className="mr-2 text-[#ff2442]">⌕</span>
            搜商品、找订单、问客服
          </div>

          <nav className="hidden items-center gap-1 lg:flex">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-full px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-pink-50 hover:text-[#ff2442]"
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {user ? (
              <>
                <Link
                  href="/profile"
                  className="hidden rounded-full bg-pink-50 px-3 py-2 text-sm font-semibold text-[#ff2442] sm:inline-flex"
                >
                  {user.full_name}
                </Link>
                <button onClick={logout} className="app-button-secondary px-3 py-2">
                  退出
                </button>
              </>
            ) : (
              <>
                <Link href="/login" className="rounded-full px-3 py-2 text-sm font-semibold text-slate-600">
                  登录
                </Link>
                <Link href="/register" className="app-button px-3 py-2">
                  注册
                </Link>
              </>
            )}
          </div>
        </div>
        <div className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 pb-3 lg:hidden">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="whitespace-nowrap rounded-full border border-pink-100 bg-white px-3 py-1.5 text-xs font-medium text-slate-600"
            >
              {item.label}
            </Link>
          ))}
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
