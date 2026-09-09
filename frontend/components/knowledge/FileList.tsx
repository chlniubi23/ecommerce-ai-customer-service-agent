/**
 * 文件列表组件
 *
 * 职责：
 * - 展示已上传文件列表
 * - 显示文件状态、chunk 数量等信息
 * - 支持展开查看 chunk 详情
 */

"use client";

import { useState } from "react";
import type { UploadRecord } from "@/types/knowledge";

interface FileListProps {
  records: UploadRecord[];
}

/** 文件类型图标 */
function FileIcon({ type }: { type: string }) {
  const colors: Record<string, string> = {
    pdf: "bg-red-100 text-red-600",
    txt: "bg-blue-100 text-blue-600",
    md: "bg-purple-100 text-purple-600",
  };
  const labels: Record<string, string> = {
    pdf: "PDF",
    txt: "TXT",
    md: "MD",
  };
  const cls = colors[type] || "bg-gray-100 text-gray-600";

  return (
    <div
      className={`w-10 h-10 rounded-lg ${cls} flex items-center justify-center text-xs font-bold flex-shrink-0`}
    >
      {labels[type] || type.toUpperCase()}
    </div>
  );
}

/** 状态 Badge */
function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { bg: string; text: string; label: string }> = {
    uploading: { bg: "bg-blue-100", text: "text-blue-700", label: "上传中" },
    parsing: { bg: "bg-yellow-100", text: "text-yellow-700", label: "解析中" },
    chunking: {
      bg: "bg-blue-100",
      text: "text-blue-700",
      label: "切片中",
    },
    completed: {
      bg: "bg-emerald-100",
      text: "text-emerald-700",
      label: "已完成",
    },
    failed: { bg: "bg-red-100", text: "text-red-700", label: "失败" },
  };
  const c = config[status] || {
    bg: "bg-gray-100",
    text: "text-gray-700",
    label: status,
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${c.bg} ${c.text}`}
    >
      {status === "completed" && (
        <svg
          className="w-3 h-3 mr-1"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path
            fillRule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      )}
      {c.label}
    </span>
  );
}

/** 格式化文件大小 */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** 格式化时间 */
function formatTime(date: Date): string {
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function FileList({ records }: FileListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (records.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
          <svg
            className="w-8 h-8 text-gray-300"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
            />
          </svg>
        </div>
        <p className="text-sm text-gray-400">暂无上传文件</p>
        <p className="text-xs text-gray-300 mt-1">
          上传文档后将在此显示处理结果
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {records.map((record) => {
        const isExpanded = expandedId === record.id;

        return (
          <div
            key={record.id}
            className="bg-white rounded-xl border border-gray-200 overflow-hidden transition-all duration-200 hover:shadow-sm"
          >
            {/* 文件行 */}
            <div
              className="flex items-center gap-4 px-4 py-3 cursor-pointer"
              onClick={() =>
                setExpandedId(isExpanded ? null : record.id)
              }
            >
              <FileIcon type={record.fileType} />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {record.fileName}
                  </p>
                  <StatusBadge status={record.status} />
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-xs text-gray-400">
                    {formatSize(record.fileSize)}
                  </span>
                  {record.status === "completed" && (
                    <>
                      <span className="text-xs text-gray-300">|</span>
                      <span className="text-xs text-emerald-600 font-medium">
                        {record.chunksCount} chunks
                      </span>
                      <span className="text-xs text-gray-300">|</span>
                      <span className="text-xs text-gray-400">
                        {record.durationMs.toFixed(0)}ms
                      </span>
                    </>
                  )}
                  <span className="text-xs text-gray-300">|</span>
                  <span className="text-xs text-gray-400">
                    {formatTime(record.uploadedAt)}
                  </span>
                </div>
              </div>

              {/* 展开箭头 */}
              {record.status === "completed" && record.chunks && (
                <svg
                  className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${
                    isExpanded ? "rotate-180" : ""
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              )}
            </div>

            {/* 错误信息 */}
            {record.status === "failed" && record.error && (
              <div className="px-4 pb-3">
                <div className="px-3 py-2 bg-red-50 rounded-lg text-xs text-red-600">
                  {record.error}
                </div>
              </div>
            )}

            {/* Chunk 详情 */}
            {isExpanded && record.chunks && record.chunks.length > 0 && (
              <div className="border-t border-gray-100 px-4 py-3 bg-gray-50/50">
                <p className="text-xs font-medium text-gray-500 mb-2">
                  Chunks ({record.chunks.length})
                </p>
                <div className="space-y-2 max-h-64 overflow-y-auto chat-scrollbar">
                  {record.chunks.map((chunk, idx) => (
                    <div
                      key={chunk.chunk_id}
                      className="bg-white rounded-lg px-3 py-2 border border-gray-100 text-xs"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded font-mono text-[10px]">
                          #{idx}
                        </span>
                        {chunk.metadata.page && (
                          <span className="px-1.5 py-0.5 bg-blue-50 text-blue-500 rounded text-[10px]">
                            p.{chunk.metadata.page}
                          </span>
                        )}
                        <span className="text-gray-300 text-[10px]">
                          {chunk.content.length} 字符
                        </span>
                      </div>
                      <p className="text-gray-600 leading-relaxed whitespace-pre-wrap line-clamp-3">
                        {chunk.content}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
