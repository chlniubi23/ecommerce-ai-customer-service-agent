"""Knowledge Agent models for Phase 8 Stage 3.

This module defines the enterprise knowledge layer around the existing RAG
infrastructure. It does not introduce a new retriever or vector store.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class KnowledgeCategory(str, Enum):
    POLICY = "policy"
    PRODUCT = "product"
    FAQ = "faq"
    SOP = "sop"
    LOGISTICS = "logistics"
    REFUND = "refund"
    COMPLAINT = "complaint"
    MEMBERSHIP = "membership"
    COUPON = "coupon"
    OPERATION = "operation"
    OTHER = "other"


class KnowledgeDocumentStatus(str, Enum):
    DISCOVERED = "discovered"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"
    ARCHIVED = "archived"


class VectorizationStatus(str, Enum):
    NOT_STARTED = "not_started"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class KnowledgeIntentType(str, Enum):
    RULE_CONSULTATION = "rule_consultation"
    POLICY_CONSULTATION = "policy_consultation"
    SYSTEM_CONSULTATION = "system_consultation"
    FAQ_CONSULTATION = "faq_consultation"
    PRODUCT_DOCUMENTATION = "product_documentation"
    PLATFORM_HELP = "platform_help"
    KNOWLEDGE_QA = "knowledge_qa"


@dataclass
class KnowledgeDocumentRecord:
    document_id: str
    file_name: str
    file_path: str
    file_type: str
    category: KnowledgeCategory = KnowledgeCategory.OTHER
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.DISCOVERED
    vectorization_status: VectorizationStatus = VectorizationStatus.NOT_STARTED
    chunks_count: int = 0
    checksum: str = ""
    source: str = "knowledge_base"
    last_error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    indexed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass
class KnowledgeSourceCitation:
    document_name: str
    document_id: str
    chunk_id: str
    similarity_score: float
    category: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass
class KnowledgeSearchRequest:
    query: str
    workflow_id: str = "knowledge_workflow"
    session_id: str = ""
    category: KnowledgeCategory | None = None
    top_k: int = 5
    min_score: float = 0.01
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass
class KnowledgeSearchResult:
    query: str
    retrieval_query: str
    documents: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    citations: list[KnowledgeSourceCitation] = field(default_factory=list)
    context: str = ""
    answer_constraints: list[str] = field(default_factory=list)
    has_relevant: bool = False
    debug_info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass
class KnowledgeWorkflowResult:
    answer: str
    search_result: KnowledgeSearchResult
    tool_call: dict[str, Any]
    trace_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


def _to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_dict(v) for k, v in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _to_dict(v) for k, v in value.items()}
    return value
