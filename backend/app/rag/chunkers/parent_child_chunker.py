"""ParentChildChunker - 父子块切分器（多来源信息整合 - 检索粒度优化）

设计（修 D7：切分粒度单一）：
- 父块 = 自然段落级（800 字符 / 150 重叠），承载完整上下文，用于**返回**；
- 子块 = 250 字符 / 50 重叠，小粒度提高检索命中率，用于**检索**；
- 每个子块 metadata 记录 parent_id；父块全量入库（chunk_type=parent），
  子块 chunk_type=child；检索时只命中子块，返回时按 parent_id 回取父块完整内容。

架构位置：
- rag/chunkers/ 层，被 KnowledgePipeline / rebuild_rag_index 使用
"""

import hashlib
import logging

from app.rag.chunkers import RecursiveChunker
from app.rag.schemas.document import Chunk, Document

logger = logging.getLogger(__name__)

# 父/子块切分参数（开发方案 B1 固定值）
PARENT_CHUNK_SIZE = 800
PARENT_CHUNK_OVERLAP = 150
CHILD_CHUNK_SIZE = 250
CHILD_CHUNK_OVERLAP = 50


class ParentChildChunker:
    """父子双层切分器：父块承载完整上下文，子块用于精确检索。"""

    def __init__(
        self,
        parent_size: int = PARENT_CHUNK_SIZE,
        parent_overlap: int = PARENT_CHUNK_OVERLAP,
        child_size: int = CHILD_CHUNK_SIZE,
        child_overlap: int = CHILD_CHUNK_OVERLAP,
        separators: list[str] | None = None,
    ):
        self.parent_chunker = RecursiveChunker(
            chunk_size=parent_size, chunk_overlap=parent_overlap, separators=separators
        )
        self.child_chunker = RecursiveChunker(
            chunk_size=child_size, chunk_overlap=child_overlap, separators=separators
        )

    def chunk_documents(self, documents: list[Document]) -> tuple[list[Chunk], list[Chunk]]:
        """切分文档为 (父块列表, 子块列表)。

        子块 metadata 含 parent_id / chunk_type=child / parent_index；
        父块 metadata 含 chunk_type=parent / parent_index。
        chunk_id 确定性生成（基于 file_id），保证 rebuild 幂等 upsert。
        """
        parents: list[Chunk] = []
        children: list[Chunk] = []

        for doc in documents:
            base_id = str((doc.metadata or {}).get("file_id") or "")
            if not base_id:
                name = str((doc.metadata or {}).get("file_name") or "")
                base_id = hashlib.md5(name.encode("utf-8")).hexdigest()[:12]

            doc_parents = self.parent_chunker.chunk_documents([doc])
            for p_idx, parent in enumerate(doc_parents):
                parent_id = f"{base_id}_p{p_idx:04d}"
                parent.chunk_id = parent_id
                parent.metadata["chunk_type"] = "parent"
                parent.metadata["parent_index"] = p_idx
                parent.metadata["chunk_index"] = p_idx

                # 子块在父块内容上二次切分（继承文档元数据）
                child_doc = Document(
                    page_content=parent.content, metadata=dict(doc.metadata or {})
                )
                doc_children = self.child_chunker.chunk_documents([child_doc])
                for c_idx, child in enumerate(doc_children):
                    child.chunk_id = f"{parent_id}_c{c_idx:04d}"
                    child.metadata["chunk_type"] = "child"
                    child.metadata["parent_id"] = parent_id
                    child.metadata["parent_index"] = p_idx
                    child.metadata["chunk_index"] = c_idx

                parents.append(parent)
                children.extend(doc_children)

        logger.info(
            "[ParentChildChunker] 切分完成: %d 个文档 → %d 父块 / %d 子块",
            len(documents), len(parents), len(children),
        )
        return parents, children
