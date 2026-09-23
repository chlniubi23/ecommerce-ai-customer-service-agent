# 后端镜像 —— FastAPI + qdrant 本地模式 + BGE 本地 Embedding
#
# Embedding 双变体（build arg EMBEDDING_PRELOAD）：
#   true  （默认，本地开发）：安装 torch CPU 版 + sentence-transformers，预下载
#         BAAI/bge-small-zh-v1.5 进镜像（离线可用、启动快；镜像约 2GB+）。
#   false （2核2G 服务器部署）：跳过 torch 与 sentence-transformers 及模型下载，
#         运行时配 EMBEDDING_PROVIDER=openai 走 OpenAI 兼容 Embedding API；
#         镜像约 500MB。索引为空时启动脚本会自动用当前 provider 重建。
#
# 构建示例：
#   docker build ./backend                                    # 本地全量变体
#   docker build --build-arg EMBEDDING_PRELOAD=false ./backend # 服务器 slim 变体

FROM python:3.12-slim

ARG EMBEDDING_PRELOAD=true
# HF 下载端点：构建环境在国内网络，默认走镜像站；海外网络可覆盖为官方空值/https://huggingface.co
ARG HF_ENDPOINT=https://hf-mirror.com
# pip 源：国内网络直连 PyPI 响应易被截断（JSONDecodeError），默认清华镜像；
# 海外构建可 --build-arg PIP_INDEX_URL=https://pypi.org/simple 覆盖
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    # 模型缓存固定路径：构建期预下载与运行期加载共用，容器内不再联网
    HF_HOME=/opt/hf-cache

# pip 通过环境变量读取 ARG 的源配置（torch 的 --index-url 显式指定 CPU 源，优先级更高）
ENV PIP_INDEX_URL=$PIP_INDEX_URL

WORKDIR /app

# 系统依赖最小化：纯 Python 栈无需编译链，curl 仅供容器内调试
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

# torch 必须 CPU 索引安装（Linux 下 PyPI 默认 torch 拉全套 CUDA 依赖，镜像会超 6GB）。
# requirements.txt 已锁 torch==2.6.0（Windows 下 c10.dll 兼容版本），两处来源版本一致：
# 先从 CPU 索引装 torch，再装 requirements 时 pip 见版本已满足不会重装。
# slim 变体（EMBEDDING_PRELOAD=false）剔除 torch 与 sentence-transformers
# （代码侧 embedding_provider 为懒加载 import，provider=openai 时不触发）。
RUN if [ "$EMBEDDING_PRELOAD" = "true" ]; then \
        pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu \
        && pip install -r requirements.txt; \
    else \
        grep -vE '^(sentence-transformers|torch)==' requirements.txt > requirements-slim.txt \
        && pip install -r requirements-slim.txt; \
    fi

# 预下载 BGE 模型进镜像层（ARG HF_ENDPOINT 在此 RUN 生效）
RUN if [ "$EMBEDDING_PRELOAD" = "true" ]; then \
        python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"; \
    fi

COPY . .

# 非 root 运行；预建 qdrant 目录并授权（命名卷首次挂载会继承镜像内属主）
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/vector_store/qdrant /opt/hf-cache \
    && chown -R appuser:appuser /app /opt/hf-cache
USER appuser

EXPOSE 8000

# 启动前置：等待 MySQL 可连 → 向量索引为空则全量重建（幂等）→ 起 uvicorn
CMD ["sh", "-c", "python scripts/docker_init.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
