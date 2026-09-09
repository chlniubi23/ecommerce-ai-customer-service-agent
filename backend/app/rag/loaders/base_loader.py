"""
Loader 抽象基类

职责：
- 定义文档加载器的统一接口
- 所有具体 Loader 必须实现 load() 方法

架构位置：
- rag/loaders/ 层
- 被 pdf_loader, text_loader 实现

扩展规划：
- Phase 5.3: 增加 DocxLoader, HtmlLoader 等
"""

import logging
from abc import ABC, abstractmethod
from app.rag.schemas.document import Document, UploadedFile

logger = logging.getLogger(__name__)


class BaseLoader(ABC):
    """文档加载器抽象基类"""

    @abstractmethod
    def load(self, uploaded_file: UploadedFile) -> list[Document]:
        """
        加载文档并返回 Document 列表

        Args:
            uploaded_file: 上传文件元信息

        Returns:
            list[Document]: 解析后的文档列表
        """
        ...
