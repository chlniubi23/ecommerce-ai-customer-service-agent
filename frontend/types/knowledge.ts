/**
 * Knowledge Base 类型定义
 *
 * 职责：
 * - 定义知识库上传/管理相关的数据结构
 * - 供 Knowledge Base 页面和 service 使用
 *
 * 架构位置：
 * - types/ 层
 * - 与后端 rag/schemas/document.py 对应
 */

/** 文件上传状态 */
export type UploadStatus =
  | "idle"
  | "uploading"
  | "parsing"
  | "chunking"
  | "completed"
  | "failed";

/** Chunk 元信息 */
export interface ChunkMetadata {
  file_id: string;
  file_name: string;
  source: string;
  page: number;
  file_type: string;
  chunk_index: number;
}

/** 单个 Chunk */
export interface Chunk {
  chunk_id: string;
  content: string;
  metadata: ChunkMetadata;
}

/** Pipeline 处理结果 (后端返回) */
export interface PipelineResult {
  file_id: string;
  file_name: string;
  file_type: string;
  documents_count: number;
  chunks_count: number;
  chunks: Chunk[];
  duration_ms: number;
}

/** 前端文件上传记录 */
export interface UploadRecord {
  id: string;
  fileName: string;
  fileType: string;
  fileSize: number;
  status: UploadStatus;
  chunksCount: number;
  documentsCount: number;
  durationMs: number;
  uploadedAt: Date;
  error?: string;
  /** 展开查看 chunks */
  expanded?: boolean;
  chunks?: Chunk[];
}
