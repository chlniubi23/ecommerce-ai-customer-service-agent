"""
批量重建知识库向量索引

用法：
    cd backend
    python rebuild_rag_index.py

会把 knowledge_base/knowledge/ 下所有 .txt 文件
通过 KnowledgePipeline 切片 → embed → 存入 vector_store/vectors.json
"""

import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR   = os.path.join(BASE_DIR, "knowledge_base", "knowledge")

sys.path.insert(0, BASE_DIR)

from app.rag.schemas.document import UploadedFile
from app.rag.pipelines import KnowledgePipeline
from app.rag.vectorstore import chroma_store


def collect_txt_files(root: str) -> list[str]:
    paths = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".txt"):
                paths.append(os.path.join(dirpath, fn))
    return sorted(paths)


def run():
    files = collect_txt_files(KB_DIR)
    logger.info(f"找到 {len(files)} 个 .txt 文件，开始索引...")

    pipeline = KnowledgePipeline(chunk_size=600, chunk_overlap=80)
    total_chunks = 0
    errors = []

    for idx, fpath in enumerate(files, 1):
        rel = os.path.relpath(fpath, BASE_DIR)
        try:
            stat      = os.stat(fpath)
            file_name = os.path.basename(fpath)
            # 推断分类：取倒数第二层目录名
            parts     = rel.replace("\\", "/").split("/")
            category  = parts[-2] if len(parts) >= 2 else "general"

            uploaded = UploadedFile(
                file_id   = f"kb_{category}_{file_name.replace('.txt','')}",
                file_name = file_name,
                file_path = fpath,
                file_type = "txt",
                file_size = stat.st_size,
                metadata  = {"category": category, "source": rel},
            )

            result = pipeline.run(uploaded)
            total_chunks += result.chunks_count
            logger.info(f"[{idx:>3}/{len(files)}] {rel} → {result.chunks_count} chunks")

        except Exception as e:
            errors.append((rel, str(e)))
            logger.warning(f"[{idx:>3}/{len(files)}] SKIP {rel}: {e}")

    logger.info(f"\n完成！共索引 {total_chunks} 个 chunks，向量库总量: {chroma_store.count()}")
    if errors:
        logger.warning(f"{len(errors)} 个文件跳过：")
        for p, e in errors:
            logger.warning(f"  {p}: {e}")


if __name__ == "__main__":
    run()
