"""
RAG 全局常量配置

职责：
- 集中管理知识库系统的配置参数
- 方便后续调参和环境配置

架构位置：
- rag/constants/ 层
- 被 loaders, chunkers, pipelines, services 引用
"""

import os

# ===== 文件上传 =====
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "uploads"
)
ALLOWED_EXTENSIONS = {"pdf", "txt", "md"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# ===== Chunking =====
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

# ===== 分隔符 (RecursiveCharacterTextSplitter) =====
SEPARATORS = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", " ", ""]

# ===== Retrieval =====
RETRIEVAL_TOP_K = 5
RETRIEVAL_MIN_SCORE = 0.01
