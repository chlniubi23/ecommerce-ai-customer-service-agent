"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import FileList from "@/components/knowledge/FileList";
import UploadZone from "@/components/knowledge/UploadZone";
import { uploadKnowledgeFile } from "@/services/knowledge";
import type { UploadRecord } from "@/types/knowledge";

export default function KnowledgeBasePage() {
  const [records, setRecords] = useState<UploadRecord[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [currentPhase, setCurrentPhase] = useState("idle");

  const completedCount = records.filter((record) => record.status === "completed").length;
  const totalChunks = records
    .filter((record) => record.status === "completed")
    .reduce((sum, record) => sum + record.chunksCount, 0);

  const handleFileSelect = useCallback(async (file: File) => {
    const tempId = crypto.randomUUID();
    const newRecord: UploadRecord = {
      id: tempId,
      fileName: file.name,
      fileType: file.name.split(".").pop()?.toLowerCase() || "unknown",
      fileSize: file.size,
      status: "uploading",
      chunksCount: 0,
      documentsCount: 0,
      durationMs: 0,
      uploadedAt: new Date(),
    };

    setRecords((prev) => [newRecord, ...prev]);
    setIsUploading(true);
    setCurrentPhase("uploading");

    try {
      const result = await uploadKnowledgeFile(file, (phase) => {
        setCurrentPhase(phase);
        setRecords((prev) =>
          prev.map((record) =>
            record.id === tempId ? { ...record, status: phase as UploadRecord["status"] } : record
          )
        );
      });

      setRecords((prev) =>
        prev.map((record) =>
          record.id === tempId
            ? {
                ...record,
                id: result.file_id,
                status: "completed" as const,
                chunksCount: result.chunks_count,
                documentsCount: result.documents_count,
                durationMs: result.duration_ms,
                chunks: result.chunks,
              }
            : record
        )
      );
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "上传失败，请重试";
      setRecords((prev) =>
        prev.map((record) =>
          record.id === tempId ? { ...record, status: "failed" as const, error: errorMessage } : record
        )
      );
    } finally {
      setIsUploading(false);
      setCurrentPhase("idle");
    }
  }, []);

  return (
    <main className="min-h-screen bg-[#f7fbff]">
      <nav className="border-b border-blue-100 bg-white px-6 py-3">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-[#2563eb] text-sm font-bold text-white">AI</div>
            <span className="text-sm font-bold text-slate-800">电商智能客服</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/" className="text-sm text-slate-500 hover:text-[#2563eb]">首页</Link>
            <span className="text-sm font-bold text-[#2563eb]">知识库</span>
          </div>
        </div>
      </nav>

      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-black text-slate-900">知识库管理</h1>
          <p className="mt-1 text-sm text-slate-500">上传文档构建知识库，系统会自动解析并切片为检索单元。</p>
        </div>

        <div className="mb-8 grid grid-cols-3 gap-4">
          <div className="app-panel px-5 py-4">
            <p className="mb-1 text-xs text-slate-400">已上传文件</p>
            <p className="text-2xl font-black text-slate-800">{completedCount}</p>
          </div>
          <div className="app-panel px-5 py-4">
            <p className="mb-1 text-xs text-slate-400">切片总数</p>
            <p className="text-2xl font-black text-[#2563eb]">{totalChunks}</p>
          </div>
          <div className="app-panel px-5 py-4">
            <p className="mb-1 text-xs text-slate-400">支持格式</p>
            <p className="mt-1 text-sm font-semibold text-slate-600">PDF / TXT / MD</p>
          </div>
        </div>

        <div className="mb-8">
          <h2 className="mb-3 text-sm font-bold text-slate-700">上传文档</h2>
          <UploadZone onFileSelect={handleFileSelect} isUploading={isUploading} currentPhase={currentPhase} />
        </div>

        <div>
          <h2 className="mb-3 text-sm font-bold text-slate-700">文件列表</h2>
          <FileList records={records} />
        </div>
      </div>
    </main>
  );
}
