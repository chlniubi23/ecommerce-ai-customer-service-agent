"""
RAG Schema 定义

职责：
- 定义知识库系统的核心数据模型
- UploadedFile: 上传文件元信息
- Document: 文档解析结果（对应一页/一段）
- Chunk: 文本切片结果（对应一个 embedding 单元）
- PipelineResult: 完整 Pipeline 输出

架构位置：
- rag/schemas/ 层
- 被 loaders, chunkers, pipelines, services, api 引用

扩展规划：
- Phase 5.2: Chunk 增加 embedding 向量字段
- Phase 5.3: 增加 KnowledgeBase 多知识库模型
"""

import time
import uuid
from typing import Any
from pydantic import BaseModel, Field


class UploadedFile(BaseModel):
    """
    上传文件元信息

    Attributes:
        file_id: 文件唯一标识
        file_name: 原始文件名
        file_type: 文件类型 (pdf/txt/md)
        file_size: 文件大小 (bytes)
        file_path: 服务端存储路径
        uploaded_at: 上传时间戳
    """
    file_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:12],
        description="文件唯一标识"
    )
    file_name: str = Field(..., description="原始文件名")
    file_type: str = Field(..., description="文件类型: pdf/txt/md")
    file_size: int = Field(..., description="文件大小 (bytes)")
    file_path: str = Field(..., description="服务端存储路径")
    uploaded_at: float = Field(
        default_factory=time.time,
        description="上传时间戳"
    )


class Document(BaseModel):
    """
    文档解析结果

    一个 Document 对应文档中的一页或一个段落。
    由 Loader 解析后输出。

    Attributes:
        page_content: 文本内容
        metadata: 元信息 (file_id, file_name, source, page 等)
    """
    page_content: str = Field(..., description="文本内容")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="元信息"
    )


class Chunk(BaseModel):
    """
    文本切片

    一个 Chunk 是最终进入 Embedding / 向量化的最小单元。
    由 Chunker 切片后输出。

    Attributes:
        chunk_id: 切片唯一标识
        content: 切片文本内容
        metadata: 元信息 (继承自 Document + chunk 索引)
    """
    chunk_id: str = Field(
        default_factory=lambda: f"chunk_{uuid.uuid4().hex[:8]}",
        description="切片唯一标识"
    )
    content: str = Field(..., description="切片文本内容")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="元信息"
    )


class PipelineResult(BaseModel):
    """
    Knowledge Pipeline 完整输出

    封装一次 upload → parse → chunk 的全部结果。

    Attributes:
        file_id: 文件 ID
        file_name: 原始文件名
        file_type: 文件类型
        documents_count: 解析出的 Document 数量
        chunks_count: 切片后的 Chunk 数量
        chunks: 全部 Chunk 列表
        duration_ms: Pipeline 处理耗时 (毫秒)
    """
    file_id: str = Field(..., description="文件 ID")
    file_name: str = Field(..., description="原始文件名")
    file_type: str = Field(..., description="文件类型")
    documents_count: int = Field(..., description="解析出的 Document 数量")
    chunks_count: int = Field(..., description="切片后的 Chunk 数量")
    chunks: list[Chunk] = Field(default_factory=list, description="全部 Chunk 列表")
    duration_ms: float = Field(default=0, description="Pipeline 处理耗时 (ms)")
