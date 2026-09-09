"""
TextLoader - TXT / Markdown 文档加载器

职责：
- 读取 .txt / .md 文件
- 输出统一的 Document 格式

架构位置：
- rag/loaders/ 层
- 被 loader_factory 调用
"""

import logging
from app.rag.loaders.metadata_utils import infer_knowledge_category
from app.rag.loaders.base_loader import BaseLoader
from app.rag.schemas.document import Document, UploadedFile

logger = logging.getLogger(__name__)


class TextLoader(BaseLoader):
    """纯文本 / Markdown 加载器"""

    def load(self, uploaded_file: UploadedFile) -> list[Document]:
        """
        读取 txt/md 文件全文，作为单个 Document 返回

        Args:
            uploaded_file: 上传文件元信息

        Returns:
            list[Document]: 单元素列表
        """
        logger.info(f"[LOADER] 加载文本文件: {uploaded_file.file_name}")

        encodings = ["utf-8", "gbk", "gb2312", "latin-1"]
        content = ""

        for enc in encodings:
            try:
                with open(uploaded_file.file_path, "r", encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if not content.strip():
            raise ValueError(f"文件内容为空: {uploaded_file.file_name}")

        doc = Document(
            page_content=content,
            metadata={
                "file_id": uploaded_file.file_id,
                "file_name": uploaded_file.file_name,
                "source": uploaded_file.file_name,
                "page": 1,
                "file_type": uploaded_file.file_type,
                "knowledge_category": infer_knowledge_category(uploaded_file.file_path, uploaded_file.file_name),
                "document_type": "enterprise_knowledge",
            }
        )

        logger.info(
            f"[LOADER] 文本加载完成: {uploaded_file.file_name}, "
            f"长度={len(content)} 字符"
        )
        return [doc]
