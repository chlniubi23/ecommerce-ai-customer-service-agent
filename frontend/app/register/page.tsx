"use client";

import { useState } from "react";
import SiteShell from "@/components/platform/SiteShell";
import { commerceApi, saveUser } from "@/services/commerce";

export default function RegisterPage() {
  const [form, setForm] = useState({
    username: "",
    email: "",
    phone: "",
    password: "",
    full_name: "",
  });
  const [error, setError] = useState("");

  const update = (key: keyof typeof form, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const result = await commerceApi.register(form);
      saveUser(result.user);
      window.location.href = "/profile";
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
    }
  };

  const fields: [keyof typeof form, string, string][] = [
    ["full_name", "姓名", "例如：林女士"],
    ["username", "用户名", "例如：customer21"],
    ["email", "邮箱", "例如：demo21@example.com"],
    ["phone", "手机号", "例如：13800000021"],
    ["password", "密码", "至少 3 位"],
  ];

  return (
    <SiteShell>
      <div className="mx-auto max-w-lg app-card p-6">
        <h1 className="text-2xl font-black text-primary">注册账号</h1>
        <p className="mt-2 text-sm text-secondary">注册后会自动创建一个默认中文收货地址，便于演示下单和客服上下文绑定。</p>
        <form onSubmit={submit} className="mt-6 grid gap-4">
          {fields.map(([key, label, placeholder]) => (
            <label key={key} className="block">
              <span className="mb-1 block text-sm font-semibold text-secondary">{label}</span>
              <input
                className="app-input w-full"
                value={form[key]}
                onChange={(e) => update(key, e.target.value)}
                placeholder={placeholder}
                type={key === "password" ? "password" : "text"}
              />
            </label>
          ))}
          {error && <div className="rounded-xl border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{error}</div>}
          <button className="app-button">创建账号</button>
        </form>
      </div>
    </SiteShell>
  );
}
