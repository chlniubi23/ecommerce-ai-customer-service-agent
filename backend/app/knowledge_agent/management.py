"""Knowledge document management and sync services."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any
from datetime import datetime

from app.knowledge_agent.models import (
    KnowledgeCategory,
    KnowledgeDocumentRecord,
    KnowledgeDocumentStatus,
    VectorizationStatus,
)
from app.rag.constants.config import UPLOAD_DIR
from app.rag.pipelines.knowledge_pipeline import KnowledgePipeline
from app.rag.schemas.document import UploadedFile


KNOWLEDGE_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))) / "knowledge_base"
SUPPORTED_SYNC_EXTENSIONS = {"txt", "md", "pdf", "docx"}


class KnowledgeManagementService:
    """In-memory management facade for indexed knowledge documents."""

    def __init__(self):
        self._documents: dict[str, KnowledgeDocumentRecord] = {}
        self._checksum_index: dict[str, str] = {}

    def upsert(self, record: KnowledgeDocumentRecord) -> KnowledgeDocumentRecord:
        record.updated_at = datetime.now()
        self._documents[record.document_id] = record
        if record.checksum:
            self._checksum_index[record.checksum] = record.document_id
        return record

    def get(self, document_id: str) -> KnowledgeDocumentRecord | None:
        return self._documents.get(document_id)

    def get_by_checksum(self, checksum: str) -> KnowledgeDocumentRecord | None:
        document_id = self._checksum_index.get(checksum)
        return self._documents.get(document_id) if document_id else None

    def list_documents(self, category: str | None = None) -> list[dict[str, Any]]:
        records = list(self._documents.values())
        if category:
            records = [record for record in records if record.category.value == category]
        return [record.to_dict() for record in sorted(records, key=lambda item: item.updated_at, reverse=True)]

    def stats(self) -> dict[str, Any]:
        categories = {item.value: 0 for item in KnowledgeCategory}
        status_counts: dict[str, int] = {}
        vector_status_counts: dict[str, int] = {}
        chunks_count = 0
        for record in self._documents.values():
            categories[record.category.value] = categories.get(record.category.value, 0) + 1
            status_counts[record.status.value] = status_counts.get(record.status.value, 0) + 1
            vector_status_counts[record.vectorization_status.value] = vector_status_counts.get(record.vectorization_status.value, 0) + 1
            chunks_count += record.chunks_count
        return {
            "documents_count": len(self._documents),
            "chunks_count": chunks_count,
            "categories": categories,
            "status_counts": status_counts,
            "vectorization_status_counts": vector_status_counts,
        }


class KnowledgeSyncService:
    """Discovers files and feeds them into the existing KnowledgePipeline."""

    def __init__(self, management: KnowledgeManagementService):
        self.management = management
        self.pipeline = KnowledgePipeline()

    def sync_directory(self, directory: str | None = None) -> dict[str, Any]:
        root = Path(directory) if directory else KNOWLEDGE_ROOT
        root.mkdir(parents=True, exist_ok=True)
        discovered = list(self._iter_supported_files(root))
        indexed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for path in discovered:
            checksum = _checksum(path)
            existing = self.management.get_by_checksum(checksum)
            if existing:
                skipped.append({"file_path": str(path), "reason": "already_indexed", "document_id": existing.document_id})
                continue
            try:
                record = self._index_file(path, root, checksum)
                indexed.append(record.to_dict())
            except Exception as exc:
                failed.append({"file_path": str(path), "error": str(exc)})

        return {
            "directory": str(root),
            "discovered": len(discovered),
            "indexed": indexed,
            "skipped": skipped,
            "failed": failed,
            "stats": self.management.stats(),
        }

    def _iter_supported_files(self, root: Path):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower().lstrip(".") in SUPPORTED_SYNC_EXTENSIONS:
                yield path

    def _index_file(self, path: Path, root: Path, checksum: str) -> KnowledgeDocumentRecord:
        file_type = path.suffix.lower().lstrip(".")
        category = _category_from_path(path, root)
        record = KnowledgeDocumentRecord(
            document_id=f"kb_{checksum[:16]}",
            file_name=path.name,
            file_path=str(path),
            file_type=file_type,
            category=category,
            status=KnowledgeDocumentStatus.INDEXING,
            vectorization_status=VectorizationStatus.PROCESSING,
            checksum=checksum,
            metadata={"sync_root": str(root), "relative_path": str(path.relative_to(root))},
        )
        self.management.upsert(record)

        if file_type == "docx":
            converted = _docx_to_text_file(path, record.document_id)
            pipeline_file = converted
            pipeline_type = "txt"
        else:
            pipeline_file = path
            pipeline_type = file_type

        uploaded = UploadedFile(
            file_id=record.document_id,
            file_name=path.name,
            file_type=pipeline_type,
            file_size=path.stat().st_size,
            file_path=str(pipeline_file),
        )
        result = self.pipeline.run(uploaded)
        record.status = KnowledgeDocumentStatus.INDEXED
        record.vectorization_status = VectorizationStatus.COMPLETED
        record.chunks_count = result.chunks_count
        record.indexed_at = record.updated_at
        record.metadata.update({"documents_count": result.documents_count, "indexed_file_type": pipeline_type})
        self.management.upsert(record)
        return record


def _category_from_path(path: Path, root: Path) -> KnowledgeCategory:
    rel_parts = [part.lower() for part in path.relative_to(root).parts]
    candidates = " ".join(rel_parts + [path.stem.lower()])
    if any(keyword in candidates for keyword in ["coupon", "discount", "promo"]):
        return KnowledgeCategory.COUPON
    if any(keyword in candidates for keyword in ["operation", "campaign", "pricing", "inventory"]):
        return KnowledgeCategory.OPERATION
    mapping = {
        KnowledgeCategory.REFUND: ["refund", "return", "退款", "退货"],
        KnowledgeCategory.LOGISTICS: ["logistics", "shipping", "delivery", "配送", "物流"],
        KnowledgeCategory.COMPLAINT: ["complaint", "投诉", "升级"],
        KnowledgeCategory.MEMBERSHIP: ["membership", "member", "会员"],
        KnowledgeCategory.SOP: ["sop", "客服", "规范"],
        KnowledgeCategory.FAQ: ["faq", "问答", "常见问题"],
        KnowledgeCategory.PRODUCT: ["product", "商品", "参数", "说明"],
        KnowledgeCategory.POLICY: ["policy", "rule", "规则", "政策", "制度"],
    }
    for category, keywords in mapping.items():
        if any(keyword in candidates for keyword in keywords):
            return category
    return KnowledgeCategory.OTHER


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _docx_to_text_file(path: Path, document_id: str) -> Path:
    try:
        import zipfile
        import xml.etree.ElementTree as ET

        with zipfile.ZipFile(path) as archive:
            xml_data = archive.read("word/document.xml")
        root = ET.fromstring(xml_data)
        texts = [node.text for node in root.iter() if node.tag.endswith("}t") and node.text]
        text = "\n".join(texts).strip()
    except Exception:
        text = ""
    target_dir = Path(UPLOAD_DIR) / document_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{path.stem}.txt"
    if text:
        target.write_text(text, encoding="utf-8")
    else:
        shutil.copyfile(path, target)
    return target


knowledge_management_service = KnowledgeManagementService()
knowledge_sync_service = KnowledgeSyncService(knowledge_management_service)
