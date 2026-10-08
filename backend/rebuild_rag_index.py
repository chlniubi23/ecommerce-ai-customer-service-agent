"""
批量重建知识库向量索引（真实 Embedding + ChromaDB）

用法：
    cd backend
    python rebuild_rag_index.py            # 增量：按 metadata 中记录的 source + 内容 hash 跳过未变化文件
    python rebuild_rag_index.py --force    # 全量：清空 collection 后从 knowledge_base/knowledge/ 全量入库

收集范围：knowledge_base/knowledge/ 下所有 .txt / .md 文件
切片配置：父子块切分（父块 800/150 返回用，子块 250/50 检索用，与 Pipeline 一致）
结束时输出：父/子块数量、向量维度、耗时
"""

import argparse
import hashlib
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base", "knowledge")

sys.path.insert(0, BASE_DIR)

from app.rag.loaders import load_document
from app.rag.chunkers import ParentChildChunker
from app.rag.schemas.document import UploadedFile
from app.rag.vectorstore import chroma_store


def collect_source_files(root: str) -> list[str]:
    """收集 .txt / .md 知识文件"""
    paths = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith((".txt", ".md")):
                paths.append(os.path.join(dirpath, fn))
    return sorted(paths)


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def existing_file_hash(file_name: str, source: str) -> str | None:
    """读取已入库文件的 source_hash（metadata 中记录），未入库返回 None"""
    for item in chroma_store.get_by_file_name(file_name):
        metadata = item.get("metadata", {}) or {}
        if str(metadata.get("source_path", "")) == source:
            return str(metadata.get("source_hash", ""))
    return None


def run(force: bool) -> None:
    files = collect_source_files(KB_DIR)
    mode = "全量重建 (--force)" if force else "增量"
    logger.info("找到 %d 个 .txt/.md 文件，开始索引（%s）...", len(files), mode)

    if force:
        removed = chroma_store.clear()
        logger.info("已清空 collection（删除 %d 个旧 chunks）", removed)

    chunker = ParentChildChunker()
    total_chunks = 0
    total_parents = 0
    total_children = 0
    indexed_files = 0
    skipped_files = 0
    errors: list[tuple[str, str]] = []
    started = time.perf_counter()

    for idx, fpath in enumerate(files, 1):
        rel = os.path.relpath(fpath, BASE_DIR).replace("\\", "/")
        try:
            stat = os.stat(fpath)
            file_name = os.path.basename(fpath)
            source_hash = file_sha256(fpath)

            # 增量：按 metadata 中记录的 source + 内容 hash 跳过未变化文件
            if not force and existing_file_hash(file_name, rel) == source_hash:
                skipped_files += 1
                logger.info("[%3d/%3d] SKIP %s (内容未变化)", idx, len(files), rel)
                continue

            # 推断分类：取倒数第二层目录名
            parts = rel.split("/")
            category = parts[-2] if len(parts) >= 2 else "general"
            file_id = f"kb_{category}_{os.path.splitext(file_name)[0]}"

            # 内容变化 → 先删除该文件旧 chunks，再重新入库（upsert 幂等兜底）
            if not force:
                chroma_store.delete_by_file_id(file_id)

            uploaded = UploadedFile(
                file_id=file_id,
                file_name=file_name,
                file_path=fpath,
                file_type=infer_file_type(fpath),
                file_size=stat.st_size,
            )

            # Loader → 父子块切分（与 KnowledgePipeline 相同组件与配置），
            # 此处单独编排以注入 source/source_hash 元数据供增量判断
            documents = load_document(uploaded)
            parents, children = chunker.chunk_documents(documents)
            for chunk in parents + children:
                chunk.metadata.update({
                    "source_path": rel,
                    "source_hash": source_hash,
                })

            stored = chroma_store.add_chunks(parents + children)
            total_chunks += stored
            total_parents += len(parents)
            total_children += len(children)
            indexed_files += 1
            logger.info("[%3d/%3d] %s → %d 父块 / %d 子块", idx, len(files), rel, len(parents), len(children))

        except Exception as e:
            errors.append((rel, str(e)))
            logger.warning("[%3d/%3d] SKIP %s: %s", idx, len(files), rel, e)

    duration = time.perf_counter() - started
    dimension = chroma_store.dimension
    logger.info(
        "\n完成！耗时 %.1fs | 入库文件 %d (跳过 %d) | 本次新增 父块 %d / 子块 %d | "
        "向量库总量 %d | 向量维度 %s | Embedding provider 见启动日志",
        duration, indexed_files, skipped_files, total_parents, total_children,
        chroma_store.count(), dimension,
    )
    if errors:
        logger.warning("%d 个文件跳过：", len(errors))
        for p, e in errors:
            logger.warning("  %s: %s", p, e)

    # 守卫：入库为 0 或全部文件报错时以非零退出，防止下游（CI 评测/容器启动）
    # 拿到空索引才暴露问题。2026-10-08 CI 事故：transformers 传递依赖漂移导致
    # 模型导入失败，79 文件全部 SKIP 仍 exit 0，评测全灭才被发现。
    if indexed_files == 0 and files:
        raise SystemExit(
            f"索引重建失败：{len(files)} 个文件全部未入库（错误 {len(errors)} 个）。"
            "通常是 Embedding 依赖加载失败，检查上方 SKIP 日志。"
        )

    try:
        chroma_store._client.close()
    except Exception:
        pass


def infer_file_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext if ext in {"pdf", "txt", "md"} else "txt"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="重建知识库向量索引 (ChromaDB)")
    parser.add_argument(
        "--force", action="store_true",
        help="清空 collection 后全量重建（默认增量：按 source+hash 跳过未变化文件）",
    )
    args = parser.parse_args()
    run(force=args.force)
