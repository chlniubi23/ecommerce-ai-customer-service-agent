"""FastAPI application entrypoint for the AI Agent commerce demo."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.state_machine.fsm_registry import init_fsm
from app.api.architecture import router as architecture_router
from app.api.chat import router as chat_router
from app.api.commerce import router as commerce_router
from app.api.metrics import router as metrics_router
from app.api.rag import router as rag_router
from app.core.config import get_settings
from app.models.base_response import success_response
from app.router.agent_router import init_routes
from app.tools.tool_registry import init_tools
from app.workflow import initialize_workflow_system


settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("%s v%s starting in %s", settings.app_name, settings.app_version, settings.app_env)
    logger.info("LLM model: %s", settings.openai_model)
    logger.info("LLM API: %s", settings.openai_base_url)

    init_routes()
    logger.info("Agent routes initialized")

    init_tools()
    logger.info("Tool registry initialized")

    init_fsm()
    logger.info("FSM registry initialized")

    initialize_workflow_system()
    logger.info("Workflow system initialized")

    yield

    logger.info("%s shutting down", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Agent E-commerce Customer Service API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api/v1")
app.include_router(rag_router, prefix="/api/rag")
app.include_router(commerce_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")
app.include_router(architecture_router, prefix="/api")


@app.get(
    "/health",
    tags=["system"],
    summary="Health check",
    description="Returns application health information for local demo monitoring.",
)
async def health_check():
    return success_response(
        data={
            "status": "healthy",
            "app": settings.app_name,
            "version": settings.app_version,
            "env": settings.app_env,
        }
    )
