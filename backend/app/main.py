"""FastAPI application entrypoint for the AI Agent commerce demo."""

import asyncio
from contextlib import asynccontextmanager
import logging
import time

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

    # Embedding 模型预热（G3）：后台加载 local BGE 模型，消除首次知识查询 ~11.9s 的加载等待。
    # 预热失败仅告警，不阻塞服务启动；测试环境经 EMBEDDING_WARMUP=false 关闭。
    # 注意：模型加载是同步阻塞调用，必须丢到线程池执行——若直接在事件循环上运行，
    # 断网时 huggingface.co 的超时重试会把整个 asyncio loop 卡死数分钟，导致所有请求 Failed to fetch。
    if settings.embedding_warmup and settings.embedding_provider == "local":
        async def _warmup_embedding_model() -> None:
            try:
                from app.rag.vectorstore.embedding_provider import get_embedding_provider

                started = time.perf_counter()
                await asyncio.to_thread(get_embedding_provider().embed_query, "预热")
                logger.info(
                    "Embedding warmup completed in %.1fs (model=%s)",
                    time.perf_counter() - started,
                    settings.embedding_model,
                )
            except Exception as exc:  # 预热失败不影响启动
                logger.warning("Embedding warmup skipped: %s", exc)

        asyncio.create_task(_warmup_embedding_model())
        logger.info("Embedding warmup task scheduled (model=%s)", settings.embedding_model)

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

# CORS 来源组装：
# - 本地开发：localhost/127.0.0.1 的 3000/3001 端口 + settings.frontend_url；
# - 服务器部署：设 CORS_EXTRA_ORIGINS="http://<服务器IP>:3000"（逗号分隔可多个），
#   容器部署经 docker-compose.yml environment 透传，直跑则写 backend/.env。
_extra_origins = [
    origin.strip()
    for origin in settings.cors_extra_origins.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        *_extra_origins,
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
