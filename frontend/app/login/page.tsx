"use client";

import Link from "next/link";
import { useState } from "react";
import SiteShell from "@/components/platform/SiteShell";
import { commerceApi, saveUser } from "@/services/commerce";

export default function LoginPage() {
  const [login, setLogin] = useState("13560569291");
  const [password, setPassword] = useState("123456");
  const [error, setError] = useState("");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const result = await commerceApi.login(login, password);
      saveUser(result.user);
      window.location.href = "/profile";
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  };

  return (
    <SiteShell>
      <div className="mx-auto max-w-md app-card p-6">
        <h1 className="text-2xl font-black text-primary">用户登录</h1>
        <p className="mt-2 text-sm text-secondary">使用演示用户访问真实订单、物流、退款和投诉数据。</p>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <input className="app-input w-full" value={login} onChange={(e) => setLogin(e.target.value)} placeholder="用户名 / 邮箱 / 手机号" />
          <input className="app-input w-full" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="密码" type="password" />
          {error && <div className="rounded-xl border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{error}</div>}
          <button className="app-button w-full">登录</button>
        </form>
        <div className="mt-4 rounded-xl border border-accent/30 bg-accent/10 p-3 text-sm text-accent">
          演示账号：手机号 <b>13560569291</b> / 密码 <b>123456</b>（已预填，直接点登录）
        </div>
        <p className="mt-4 text-sm text-secondary">
          还没有账号？ <Link href="/register" className="ai-link font-bold">立即注册</Link>
        </p>
      </div>
    </SiteShell>
  );
}
