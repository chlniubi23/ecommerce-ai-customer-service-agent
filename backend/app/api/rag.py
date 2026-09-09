"""RAG and Knowledge Base API routes."""

import logging

from fastapi import APIRouter, File, UploadFile

from app.knowledge_agent import KnowledgeCategory, knowledge_management_service, knowledge_sync_service
from app.architecture import PRODUCTION_ARCHITECTURE
from app.models.base_response import error_response, success_response
from app.rag.services import upload_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rag"])


@router.post("/upload")
async def upload_knowledge_file(file: UploadFile = File(...)):
    """Upload a knowledge document and run the existing parse/chunk/embed pipeline."""
    try:
        result = await upload_service.process_upload(file)
        logger.info(
            "[API] knowledge upload succeeded: %s -> %s chunks (%sms)",
            result.file_name,
            result.chunks_count,
            result.duration_ms,
        )
        data = result.model_dump()
        data["production_knowledge_entry"] = PRODUCTION_ARCHITECTURE["knowledge_entry"]
        data["knowledge_tool"] = PRODUCTION_ARCHITECTURE["knowledge_tool"]
        return success_response(data=data)
    except ValueError as e:
        logger.warning("[API] upload validation failed: %s", e)
        return error_response(
            code="UPLOAD_VALIDATION_ERROR",
            message=str(e),
        )
    except Exception as e:
        logger.error("[API] upload processing failed: %s", e, exc_info=True)
        return error_response(
            code="UPLOAD_PROCESSING_ERROR",
            message="文件处理失败，请稍后重试",
            detail=str(e),
        )


@router.get("/documents")
async def list_knowledge_documents(category: str | None = None):
    """List indexed knowledge documents for the management console."""
    return success_response(
        data={
            "documents": knowledge_management_service.list_documents(category=category),
            "stats": knowledge_management_service.stats(),
            "production_architecture": {
                "knowledge_entry": PRODUCTION_ARCHITECTURE["knowledge_entry"],
                "knowledge_tool": PRODUCTION_ARCHITECTURE["knowledge_tool"],
                "retriever": PRODUCTION_ARCHITECTURE["retriever"],
                "vector_store": PRODUCTION_ARCHITECTURE["vector_store"],
            },
        }
    )


@router.get("/documents/stats")
async def knowledge_document_stats():
    """Return document, category and vectorization statistics."""
    data = knowledge_management_service.stats()
    data["production_architecture"] = {
        "knowledge_entry": PRODUCTION_ARCHITECTURE["knowledge_entry"],
        "knowledge_tool": PRODUCTION_ARCHITECTURE["knowledge_tool"],
        "retriever": PRODUCTION_ARCHITECTURE["retriever"],
        "vector_store": PRODUCTION_ARCHITECTURE["vector_store"],
    }
    return success_response(data=data)


@router.get("/categories")
async def knowledge_categories():
    """Return supported enterprise knowledge categories."""
    return success_response(data={"categories": [item.value for item in KnowledgeCategory]})


@router.post("/sync")
async def sync_knowledge_base(directory: str | None = None):
    """Incrementally sync files from the knowledge base directory into the existing RAG pipeline."""
    try:
        result = knowledge_sync_service.sync_directory(directory)
        result["production_knowledge_entry"] = PRODUCTION_ARCHITECTURE["knowledge_entry"]
        result["knowledge_tool"] = PRODUCTION_ARCHITECTURE["knowledge_tool"]
        return success_response(data=result)
    except Exception as e:
        logger.error("[API] knowledge sync failed: %s", e, exc_info=True)
        return error_response(
            code="KNOWLEDGE_SYNC_ERROR",
            message="知识库同步失败",
            detail=str(e),
        )
