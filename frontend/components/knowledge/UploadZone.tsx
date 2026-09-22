/**
 * 文件上传区域组件
 *
 * 职责：
 * - Drag & Drop 上传
 * - 点击选择文件上传
 * - 文件格式/大小前端校验
 * - 显示上传状态
 */

"use client";

import { useState, useRef, useCallback } from "react";
import { validateFile, ALLOWED_EXTENSIONS } from "@/services/knowledge";

interface UploadZoneProps {
  onFileSelect: (file: File) => void;
  isUploading: boolean;
  currentPhase: string;
}

export default function UploadZone({
  onFileSelect,
  isUploading,
  currentPhase,
}: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File) => {
      setValidationError(null);
      const error = validateFile(file);
      if (error) {
        setValidationError(error);
        return;
      }
      onFileSelect(file);
    },
    [onFileSelect]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleClick = useCallback(() => {
    if (!isUploading) {
      fileInputRef.current?.click();
    }
  }, [isUploading]);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
      // 清空 input 以支持重复上传同一文件
      e.target.value = "";
    },
    [handleFile]
  );

  /** 上传阶段文案 */
  const phaseLabel: Record<string, string> = {
    uploading: "上传中...",
    parsing: "解析文档中...",
    chunking: "文本切片中...",
    completed: "处理完成",
  };

  return (
    <div className="w-full">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleClick}
        className={`
          relative border-2 border-dashed rounded-xl p-8
          flex flex-col items-center justify-center gap-3
          cursor-pointer transition-all duration-200 min-h-[200px]
          ${
            isUploading
              ? "border-accent/50 bg-accent/10 cursor-wait"
              : isDragging
              ? "border-success bg-success/10 scale-[1.01]"
              : "border-line bg-surface hover:border-accent/60 hover:bg-elevated"
          }
        `}
      >
        {isUploading ? (
          /* 上传中状态 */
          <div className="flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-accent/15 flex items-center justify-center">
              <svg
                className="w-6 h-6 text-accent animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            </div>
            <p className="text-sm font-medium text-accent">
              {phaseLabel[currentPhase] || "处理中..."}
            </p>
            {/* 进度条 */}
            <div className="w-48 h-1.5 bg-elevated rounded-full overflow-hidden">
              <div
                className="h-full bg-accent-gradient rounded-full transition-all duration-500"
                style={{
                  width:
                    currentPhase === "uploading"
                      ? "33%"
                      : currentPhase === "parsing"
                      ? "66%"
                      : "100%",
                }}
              />
            </div>
          </div>
        ) : (
          /* 默认状态 */
          <>
            <div className="w-14 h-14 rounded-full bg-elevated flex items-center justify-center">
              <svg
                className="w-7 h-7 text-tertiary"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-secondary">
                拖拽文件到此处，或{" "}
                <span className="text-accent">点击上传</span>
              </p>
              <p className="text-xs text-tertiary mt-1">
                支持 {ALLOWED_EXTENSIONS.map((e) => `.${e}`).join(" / ")}
                ，最大 10MB
              </p>
            </div>
          </>
        )}
      </div>

      {/* 校验错误 */}
      {validationError && (
        <div className="mt-3 px-4 py-2 bg-danger/10 border border-danger/30 rounded-lg text-sm text-danger flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {validationError}
        </div>
      )}

      {/* 隐藏的文件输入 */}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".pdf,.txt,.md"
        onChange={handleInputChange}
      />
    </div>
  );
}
