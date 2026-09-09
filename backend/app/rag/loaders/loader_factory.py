"""
Loader Factory - 文档加载器工厂

职责：
- 根据文件类型自动选择对应的 Loader
- 统一入口，屏蔽 Loader 选择逻辑

架构位置：
- rag/loaders/ 层
- 被 pipeline 调用

扩展规划：
- 新增文件类型只需注册新 Loader
"""

import logging
from app.rag.loaders.base_loader import BaseLoader
from app.rag.loaders.text_loader import TextLoader
from app.rag.loaders.pdf_loader import PDFLoader
from app.rag.schemas.document import Document, UploadedFile

logger = logging.getLogger(__name__)

# 文件类型 → Loader 映射
LOADER_REGISTRY: dict[str, BaseLoader] = {
    "txt": TextLoader(),
    "md": TextLoader(),
    "pdf": PDFLoader(),
}


def load_document(uploaded_file: UploadedFile) -> list[Document]:
    """
    根据文件类型自动选择 Loader 并加载文档

    Args:
        uploaded_file: 上传文件元信息

    Returns:
        list[Document]: 解析后的文档列表

    Raises:
        ValueError: 不支持的文件类型
    """
    file_type = uploaded_file.file_type.lower()
    loader = LOADER_REGISTRY.get(file_type)

    if not loader:
        raise ValueError(f"不支持的文件类型: {file_type}")

    logger.info(
        f"[LOADER] 使用 {loader.__class__.__name__} "
        f"加载: {uploaded_file.file_name}"
    )
    return loader.load(uploaded_file)
