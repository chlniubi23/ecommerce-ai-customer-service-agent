"""Read-only production architecture inspection API."""

from fastapi import APIRouter

from app.architecture import PRODUCTION_ARCHITECTURE
from app.models.base_response import success_response

router = APIRouter(prefix="/architecture", tags=["architecture"])


@router.get("/production")
async def production_architecture():
    """Return the canonical production architecture map used across the system."""
    return success_response(data=PRODUCTION_ARCHITECTURE)
