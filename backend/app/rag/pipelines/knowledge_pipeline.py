"""
KnowledgePipeline - 知识预处理管线

职责：
- 编排完整的知识预处理流程
- Upload → Parse → Chunk → Embed & Store (ChromaDB)
- 统一异常处理和日志

架构位置：
- rag/pipelines/ 层
- 被 services/upload_service.py 调用

扩展规划：
- Phase 5.3: 增加 rerank / hybrid search
- Phase 5.4: 支持多 collection (多知识库)
"""

import time
import logging
from app.rag.schemas.document import UploadedFile, Document, Chunk, PipelineResult
from app.rag.loaders import load_document
from app.rag.chunkers import RecursiveChunker
from app.rag.vectorstore import chroma_store

logger = logging.getLogger(__name__)


class KnowledgePipeline:
    """
    知识预处理管线

    Usage:
        pipeline = KnowledgePipeline()
        result = pipeline.run(uploaded_file)
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100):
        self.chunker = RecursiveChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def run(self, uploaded_file: UploadedFile) -> PipelineResult:
        """
        执行完整知识预处理管线

        流程:
        1. 文档解析 (Loader)
        2. 文本切片 (Chunker)
        3. 向量存储 (ChromaDB embedding + store)

        Args:
            uploaded_file: 上传文件元信息

        Returns:
            PipelineResult: 完整处理结果

        Raises:
            ValueError: 文件类型不支持 / 文件为空
            Exception: Loader 或 Chunker 异常
        """
        start = time.perf_counter()

        logger.info(
            f"[PIPELINE] 开始处理: {uploaded_file.file_name} "
            f"(type={uploaded_file.file_type}, size={uploaded_file.file_size} bytes)"
        )

        # Step 1: 文档解析
        logger.info(f"[PIPELINE] Step 1/3: 文档解析...")
        documents = load_document(uploaded_file)
        logger.info(f"[PIPELINE] 文档解析完成: {len(documents)} 个 Document")

        # Step 2: 文本切片
        logger.info(f"[PIPELINE] Step 2/3: 文本切片...")
        chunks = self.chunker.chunk_documents(documents)
        logger.info(f"[PIPELINE] 文本切片完成: {len(chunks)} 个 Chunk")

        # Step 3: 向量存储
        logger.info(f"[PIPELINE] Step 3/3: 向量存储 (ChromaDB)...")
        stored = chroma_store.add_chunks(chunks)
        logger.info(f"[PIPELINE] 向量存储完成: {stored} 个 chunks 已入库")

        # 构建结果
        duration = (time.perf_counter() - start) * 1000
        result = PipelineResult(
            file_id=uploaded_file.file_id,
            file_name=uploaded_file.file_name,
            file_type=uploaded_file.file_type,
            documents_count=len(documents),
            chunks_count=len(chunks),
            chunks=chunks,
            duration_ms=round(duration, 2),
        )

        logger.info(
            f"[PIPELINE] 处理完成: {uploaded_file.file_name} → "
            f"{result.documents_count} docs, {result.chunks_count} chunks, "
            f"耗时 {result.duration_ms}ms"
        )

        return result
