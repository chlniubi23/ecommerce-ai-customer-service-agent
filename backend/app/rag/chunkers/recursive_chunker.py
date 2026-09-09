"""
RecursiveChunker - 递归字符文本切片器

职责：
- 将 Document 列表切分为固定大小的 Chunk
- 使用多级分隔符递归切分，保留语义完整性
- 支持 overlap 防止语义截断

算法：
1. 按优先级尝试分隔符: \n\n → \n → 。→ . → 空格 → 逐字
2. 尝试用当前分隔符切分文本
3. 如果切片 > chunk_size，递归用下一级分隔符继续切分
4. 合并相邻小切片直到接近 chunk_size

架构位置：
- rag/chunkers/ 层
- 被 pipeline 调用

扩展规划：
- Phase 5.2: 增加 SemanticChunker (基于 embedding 相似度切分)
"""

import logging
from app.rag.schemas.document import Document, Chunk
from app.rag.constants.config import CHUNK_SIZE, CHUNK_OVERLAP, SEPARATORS

logger = logging.getLogger(__name__)


class RecursiveChunker:
    """递归字符文本切片器"""

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        separators: list[str] | None = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or SEPARATORS

    def chunk_documents(self, documents: list[Document]) -> list[Chunk]:
        """
        将 Document 列表切分为 Chunk 列表

        Args:
            documents: Loader 输出的 Document 列表

        Returns:
            list[Chunk]: 切片结果
        """
        all_chunks: list[Chunk] = []

        for doc in documents:
            text = doc.page_content
            if not text.strip():
                continue

            splits = self._split_text(text)
            for idx, split_text in enumerate(splits):
                chunk = Chunk(
                    content=split_text,
                    metadata={
                        **doc.metadata,
                        "chunk_index": idx,
                    }
                )
                all_chunks.append(chunk)

        logger.info(
            f"[CHUNKER] 切片完成: {len(documents)} 个文档 → {len(all_chunks)} 个 chunks "
            f"(size={self.chunk_size}, overlap={self.chunk_overlap})"
        )
        return all_chunks

    def _split_text(self, text: str) -> list[str]:
        """
        递归切分文本

        Args:
            text: 待切分文本

        Returns:
            list[str]: 切分后的文本片段
        """
        return self._recursive_split(text, self.separators)

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """递归切分核心逻辑"""
        final_chunks: list[str] = []

        # 选择当前最优分隔符
        separator = separators[-1]  # 默认最后一个
        for sep in separators:
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                break

        # 切分
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        # 合并小片段
        current_parts: list[str] = []
        current_length = 0

        for split in splits:
            piece = split.strip()
            if not piece:
                continue

            piece_len = len(piece)

            if current_length + piece_len + 1 <= self.chunk_size:
                current_parts.append(piece)
                current_length += piece_len + 1
            else:
                # 当前累积的 parts 输出为一个 chunk
                if current_parts:
                    chunk_text = separator.join(current_parts) if separator else "".join(current_parts)
                    final_chunks.append(chunk_text)

                # 如果单个 piece 超过 chunk_size → 递归切分
                if piece_len > self.chunk_size:
                    remaining_seps = separators[separators.index(separator) + 1:] if separator in separators else separators[1:]
                    if remaining_seps:
                        sub_chunks = self._recursive_split(piece, remaining_seps)
                        final_chunks.extend(sub_chunks)
                    else:
                        # 没有更细的分隔符了，强制按 chunk_size 切
                        for i in range(0, len(piece), self.chunk_size - self.chunk_overlap):
                            final_chunks.append(piece[i:i + self.chunk_size])
                    current_parts = []
                    current_length = 0
                else:
                    # overlap: 保留尾部部分
                    overlap_parts = self._get_overlap_parts(current_parts, separator)
                    current_parts = overlap_parts + [piece]
                    current_length = sum(len(p) for p in current_parts) + len(current_parts) - 1

        # 最后剩余
        if current_parts:
            chunk_text = separator.join(current_parts) if separator else "".join(current_parts)
            if chunk_text.strip():
                final_chunks.append(chunk_text)

        return final_chunks

    def _get_overlap_parts(self, parts: list[str], separator: str) -> list[str]:
        """获取 overlap 部分"""
        if not parts or self.chunk_overlap <= 0:
            return []

        overlap_parts: list[str] = []
        overlap_length = 0

        for part in reversed(parts):
            if overlap_length + len(part) > self.chunk_overlap:
                break
            overlap_parts.insert(0, part)
            overlap_length += len(part) + 1

        return overlap_parts
