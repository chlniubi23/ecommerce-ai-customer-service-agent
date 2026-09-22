/**
 * TailwindCSS 配置
 *
 * 配置 Tailwind 扫描范围和自定义主题。
 * 引入 @tailwindcss/typography 插件用于渲染 Markdown 内容。
 *
 * Dark Premium 设计 Token（唯一事实源，与 app/globals.css 同步）：
 * - 背景基底：bg-base / bg-surface / bg-elevated / border-line
 * - 文字：text-primary / text-secondary / text-tertiary
 * - Accent：全站唯一主色 accent（indigo），禁止第二种彩色
 * - 功能色：仅状态提示，极小面积
 */

import type { Config } from "tailwindcss";
// Node 24+ 将 .ts 按 ESM 加载，配置文件内不能使用 CommonJS 的 require，
// 插件改为静态 import（对旧版 Node 同样兼容）。
import typography from "@tailwindcss/typography";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // ===== 背景基底 =====
        base: "#0A0A0F",       // 页面底色（bg-base）
        surface: "#12121A",    // 卡片/面板（bg-surface）
        elevated: "#1A1A26",   // 悬浮层/浮窗（bg-elevated）
        line: "rgba(255,255,255,0.08)", // 边框线（border-line）

        // ===== 文字 =====
        primary: "#F4F4F6",    // 主文字（text-primary）
        secondary: "#A1A1B0",  // 次要文字（text-secondary）
        tertiary: "#6B6B7B",   // 弱提示文字（text-tertiary）

        // ===== Accent：全站唯一主色 =====
        accent: {
          DEFAULT: "#6366F1",  // indigo-500
          hover: "#818CF8",
          glow: "rgba(99,102,241,0.35)",
        },

        // ===== 功能色（仅状态提示，极小面积） =====
        success: "#34D399",
        warning: "#FBBF24",
        danger: "#F87171",
      },
      boxShadow: {
        // 极淡内阴影（卡片质感，不用大圆角粉影）
        "card-inset": "inset 0 1px 0 0 rgba(255,255,255,0.04)",
        // 主按钮 hover 的 accent 光晕
        "accent-glow": "0 0 24px rgba(99,102,241,0.35)",
      },
      backgroundImage: {
        // 仅用于点睛：主按钮、数字人光环、核心数据
        "accent-gradient": "linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%)",
      },
      fontFamily: {
        sans: ["Arial", "Microsoft YaHei", "PingFang SC", "sans-serif"],
      },
    },
  },
  plugins: [
    typography,
  ],
};

export default config;
