"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";
import { clearStoredUser, commerceApi, DemoUser, getStoredUserId } from "@/services/commerce";

const navItems = [
  { href: "/", label: "首页" },
  { href: "/products", label: "商城" },
  { href: "/orders", label: "订单" },
  { href: "/after-sales", label: "售后" },
  { href: "/complaints", label: "投诉" },
  { href: "/metrics", label: "指标", icon: BarChart3 },
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
    <div className="min-h-screen text-primary">
      <header className="sticky top-0 z-40 border-b border-line bg-elevated/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
          <Link href="/" className="flex shrink-0 items-center gap-2">
            <div className="relative grid h-10 w-10 place-items-center overflow-hidden rounded-2xl bg-accent-gradient text-base font-black text-white shadow-accent-glow">
              小
              <span className="absolute -right-2 -top-2 h-5 w-5 rounded-full bg-white/25" />
            </div>
            <div>
              <div className="text-base font-black leading-tight text-primary">
                小易<span className="text-accent">AI</span>助手
              </div>
              <div className="text-[11px] text-tertiary">AI 客服演示平台</div>
            </div>
          </Link>

          <div className="hidden min-w-0 flex-1 items-center rounded-full border border-line bg-surface px-4 py-2 text-sm text-tertiary md:flex">
            搜商品、找订单、问客服
          </div>

          <nav className="hidden items-center gap-1 lg:flex">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="inline-flex items-center gap-1 rounded-full px-3 py-2 text-sm font-medium text-secondary transition hover:bg-surface hover:text-accent"
              >
                {item.icon && <item.icon className="h-3.5 w-3.5" />}
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {user ? (
              <>
                <Link
                  href="/profile"
                  className="hidden rounded-full bg-accent/10 px-3 py-2 text-sm font-semibold text-accent sm:inline-flex"
                >
                  {user.full_name}
                </Link>
                <button onClick={logout} className="app-button-secondary px-3 py-2">
                  退出
                </button>
              </>
            ) : (
              <>
                <Link href="/login" className="rounded-full px-3 py-2 text-sm font-semibold text-secondary transition hover:text-primary">
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
              className="whitespace-nowrap rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-secondary"
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
