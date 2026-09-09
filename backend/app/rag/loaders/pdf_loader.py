"""
PDFLoader - PDF 文档加载器

职责：
- 逐页读取 PDF 文件
- 每页输出一个 Document
- 使用 PyPDF2 解析

架构位置：
- rag/loaders/ 层
- 被 loader_factory 调用

依赖：
- PyPDF2
"""

import logging
from PyPDF2 import PdfReader
from app.rag.loaders.metadata_utils import infer_knowledge_category
from app.rag.loaders.base_loader import BaseLoader
from app.rag.schemas.document import Document, UploadedFile

logger = logging.getLogger(__name__)


class PDFLoader(BaseLoader):
    """PDF 文档加载器"""

    def load(self, uploaded_file: UploadedFile) -> list[Document]:
        """
        逐页解析 PDF，每页生成一个 Document

        Args:
            uploaded_file: 上传文件元信息

        Returns:
            list[Document]: 每页一个 Document
        """
        logger.info(f"[LOADER] 加载 PDF 文件: {uploaded_file.file_name}")

        reader = PdfReader(uploaded_file.file_path)
        documents: list[Document] = []

        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if not text or not text.strip():
                logger.warning(f"[LOADER] PDF 第 {page_num} 页为空，跳过")
                continue

            doc = Document(
                page_content=text.strip(),
                metadata={
                    "file_id": uploaded_file.file_id,
                    "file_name": uploaded_file.file_name,
                    "source": uploaded_file.file_name,
                    "page": page_num,
                    "file_type": "pdf",
                    "knowledge_category": infer_knowledge_category(uploaded_file.file_path, uploaded_file.file_name),
                    "document_type": "enterprise_knowledge",
                }
            )
            documents.append(doc)

        if not documents:
            raise ValueError(f"PDF 文件无可提取文本: {uploaded_file.file_name}")

        logger.info(
            f"[LOADER] PDF 加载完成: {uploaded_file.file_name}, "
            f"共 {len(documents)} 页"
        )
        return documents
