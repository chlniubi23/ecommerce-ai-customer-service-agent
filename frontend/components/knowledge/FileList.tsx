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
    pdf: "bg-danger/15 text-danger",
    txt: "bg-accent/15 text-accent",
    md: "bg-accent/15 text-accent",
  };
  const labels: Record<string, string> = {
    pdf: "PDF",
    txt: "TXT",
    md: "MD",
  };
  const cls = colors[type] || "bg-elevated text-secondary";

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
    uploading: { bg: "bg-accent/15", text: "text-accent", label: "上传中" },
    parsing: { bg: "bg-warning/15", text: "text-warning", label: "解析中" },
    chunking: {
      bg: "bg-accent/15", text: "text-accent", label: "切片中",
    },
    completed: {
      bg: "bg-success/15", text: "text-success",
      label: "已完成",
    },
    failed: { bg: "bg-danger/15", text: "text-danger", label: "失败" },
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
        <div className="w-16 h-16 rounded-full bg-elevated flex items-center justify-center mx-auto mb-4">
          <svg
            className="w-8 h-8 text-tertiary"
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
        <p className="text-sm text-tertiary">暂无上传文件</p>
        <p className="text-xs text-tertiary mt-1">
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
            className="bg-surface rounded-xl border border-line overflow-hidden transition-all duration-200 hover:shadow-sm"
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
                  <p className="text-sm font-medium text-primary truncate">
                    {record.fileName}
                  </p>
                  <StatusBadge status={record.status} />
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-xs text-tertiary">
                    {formatSize(record.fileSize)}
                  </span>
                  {record.status === "completed" && (
                    <>
                      <span className="text-xs text-tertiary">|</span>
                      <span className="text-xs text-success font-medium">
                        {record.chunksCount} chunks
                      </span>
                      <span className="text-xs text-tertiary">|</span>
                      <span className="text-xs text-tertiary">
                        {record.durationMs.toFixed(0)}ms
                      </span>
                    </>
                  )}
                  <span className="text-xs text-tertiary">|</span>
                  <span className="text-xs text-tertiary">
                    {formatTime(record.uploadedAt)}
                  </span>
                </div>
              </div>

              {/* 展开箭头 */}
              {record.status === "completed" && record.chunks && (
                <svg
                  className={`w-4 h-4 text-tertiary transition-transform duration-200 ${
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
                <div className="px-3 py-2 bg-danger/10 rounded-lg text-xs text-danger">
                  {record.error}
                </div>
              </div>
            )}

            {/* Chunk 详情 */}
            {isExpanded && record.chunks && record.chunks.length > 0 && (
              <div className="border-t border-line px-4 py-3 bg-elevated/50">
                <p className="text-xs font-medium text-secondary mb-2">
                  Chunks ({record.chunks.length})
                </p>
                <div className="space-y-2 max-h-64 overflow-y-auto chat-scrollbar">
                  {record.chunks.map((chunk, idx) => (
                    <div
                      key={chunk.chunk_id}
                      className="bg-surface rounded-lg px-3 py-2 border border-line text-xs"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="px-1.5 py-0.5 bg-elevated text-secondary rounded font-mono text-[10px]">
                          #{idx}
                        </span>
                        {chunk.metadata.page && (
                          <span className="px-1.5 py-0.5 bg-accent/15 text-accent rounded text-[10px]">
                            p.{chunk.metadata.page}
                          </span>
                        )}
                        <span className="text-tertiary text-[10px]">
                          {chunk.content.length} 字符
                        </span>
                      </div>
                      <p className="text-secondary leading-relaxed whitespace-pre-wrap line-clamp-3">
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
