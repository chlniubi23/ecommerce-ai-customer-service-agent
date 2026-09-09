/**
 * Knowledge Base API 服务层
 *
 * 职责：
 * - 封装知识库文件上传 API 调用
 * - 处理 multipart/form-data 上传
 * - 统一解析信封格式
 *
 * 架构位置：
 * - services/ 层
 * - 被 knowledge-base 页面组件调用
 */

import type { PipelineResult } from "@/types/knowledge";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/** 上传响应信封 */
interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string } | null;
}

/**
 * 上传知识库文件
 *
 * 使用 multipart/form-data 上传文件到后端 RAG pipeline。
 * 后端自动执行: 保存 → 解析 → 切片
 *
 * @param file - 待上传的 File 对象
 * @param onProgress - 上传进度回调 (0-100)
 * @returns PipelineResult
 */
export async function uploadKnowledgeFile(
  file: File,
  onProgress?: (phase: string) => void
): Promise<PipelineResult> {
  const url = `${API_BASE_URL}/api/rag/upload`;

  const formData = new FormData();
  formData.append("file", file);

  // 通知上传中
  onProgress?.("uploading");

  const response = await fetch(url, {
    method: "POST",
    body: formData,
    // 不设置 Content-Type，让浏览器自动设置 boundary
  });

  // 通知解析中
  onProgress?.("parsing");

  const envelope: ApiEnvelope<PipelineResult> = await response.json();

  if (!envelope.success || !envelope.data) {
    const msg = envelope.error?.message || "文件上传失败";
    throw new Error(msg);
  }

  // 通知完成
  onProgress?.("completed");

  return envelope.data;
}

/** 支持的文件扩展名 */
export const ALLOWED_EXTENSIONS = ["pdf", "txt", "md"];

/** 最大文件大小 (10MB) */
export const MAX_FILE_SIZE = 10 * 1024 * 1024;

/**
 * 校验文件
 *
 * @returns 错误信息，null 表示通过
 */
export function validateFile(file: File): string | null {
  const ext = file.name.split(".").pop()?.toLowerCase() || "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `不支持的文件格式: .${ext}，支持: ${ALLOWED_EXTENSIONS.join(", ")}`;
  }
  if (file.size > MAX_FILE_SIZE) {
    return `文件过大: ${(file.size / 1024 / 1024).toFixed(1)}MB，最大: 10MB`;
  }
  if (file.size === 0) {
    return "文件为空";
  }
  return null;
}
