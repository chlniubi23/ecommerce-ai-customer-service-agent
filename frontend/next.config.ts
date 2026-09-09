/**
 * Next.js 配置文件
 *
 * 当前阶段：基础配置
 * 扩展规划：
 * - 后续可增加 API 代理重写规则
 * - 生产环境可配置 CDN、图片优化等
 */

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* 允许开发环境的跨域预览访问 */
  allowedDevOrigins: ["http://localhost:3000", "http://127.0.0.1:3000"],
  /* 指定项目根目录，消除多 lockfile 警告 */
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
