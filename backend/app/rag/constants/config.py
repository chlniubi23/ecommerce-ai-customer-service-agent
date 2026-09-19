"""
RAG 全局常量配置

职责：
- 集中管理知识库系统的配置参数
- CHUNK_SIZE / CHUNK_OVERLAP / RETRIEVAL_MIN_SCORE 统一读取 Settings
  （.env 可覆盖），保证 rebuild 脚本 / API upload / Pipeline 三处入口一致

架构位置：
- rag/constants/ 层
- 被 loaders, chunkers, pipelines, services 引用
"""

import os

from app.core.config import get_settings

# ===== 文件上传 =====
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "uploads"
)
ALLOWED_EXTENSIONS = {"pdf", "txt", "md"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# ===== Chunking（统一配置来源：Settings.chunk_size / chunk_overlap） =====
_settings = get_settings()
CHUNK_SIZE = _settings.chunk_size
CHUNK_OVERLAP = _settings.chunk_overlap

# ===== 分隔符 (RecursiveCharacterTextSplitter) =====
SEPARATORS = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", " ", ""]

# ===== Retrieval =====
RETRIEVAL_TOP_K = 5
# 真实 Embedding 的相关性下限（Settings.retrieval_min_score，黄金问题校准后回填）
RETRIEVAL_MIN_SCORE = _settings.retrieval_min_score
