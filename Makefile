# ==============================================================================
# E-commerce AI Customer Service Agent —— 常用命令一键入口
#
# 本机（Windows / Git Bash）与 Linux 服务器的差异：
#   - Python：本机必须用 backend/.venv/Scripts/python.exe（项目 venv，系统
#     Anaconda 缺依赖）；Linux 服务器等价命令为 backend/.venv/bin/python。
#     本 Makefile 统一经 PY 变量取本机路径，Linux 上可 `make PY=backend/.venv/bin/python <target>` 覆盖。
#   - docker compose：两平台一致（服务器需先装 Docker Engine + compose 插件）。
#   - 服务器部署三步：make build EMBEDDING_PRELOAD=false → 设 CORS_EXTRA_ORIGINS
#     与 NEXT_PUBLIC_API_BASE_URL → make up（详见 docker-compose.yml 注释）。
# ==============================================================================

# 注意：本 Makefile 的 PY 为 backend/ 内相对路径（所有配方均先 cd backend 再调用）；
# Linux 服务器覆盖示例：make PY=.venv/bin/python test
PY := .venv/Scripts/python.exe

.PHONY: help up down logs ps build test eval rebuild-index reset-data install dev-backend dev-frontend

help:  ## 显示所有目标说明
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------- Docker 编排（docker compose 封装） ----------

up:  ## 启动全栈（db + backend + frontend，首启自动初始化）
	docker compose up -d

down:  ## 停止全栈（数据卷保留；彻底清数据加 -v 手动执行）
	docker compose down

logs:  ## 跟随查看全栈日志（Ctrl+C 退出）
	docker compose logs -f

ps:  ## 查看容器状态
	docker compose ps

build:  ## 构建镜像（本地全量变体：torch CPU + BGE 预下载，约 2.3GB）
	@echo "服务器（2核2G）slim 变体示例（约 412MB，跳过 torch/模型，配 EMBEDDING_PROVIDER=openai）："
	@echo "  docker build --build-arg EMBEDDING_PRELOAD=false -t backend-slim ./backend"
	@echo "或经 compose：在 docker-compose.yml backend.build.args 中改 EMBEDDING_PRELOAD: \"false\""
	docker compose build

# ---------- 测试与评测 ----------

test:  ## 后端 pytest 全量（须用项目 venv；依赖本机 MySQL）
	cd backend && $(PY) -m pytest tests/ -q

eval:  ## 路由评测（离线）+ RAG 评测连跑（不需 LLM API）
	cd backend && $(PY) -m evaluation.run_eval
	cd backend && $(PY) -m evaluation.run_rag_eval

# ---------- 数据与索引（宿主机直跑，需本机 venv 与 MySQL） ----------

rebuild-index:  ## 全量重建 RAG 向量索引（--force 清空重建）
	cd backend && $(PY) rebuild_rag_index.py --force

reset-data:  ## 演示业务数据重置（订单/物流/退款/投诉回到初始演示态）
	cd backend && $(PY) scripts/reset_business_data.py

# ---------- 本地开发（非容器模式） ----------

install:  ## 后端 venv 建立与依赖安装 + 前端 npm install
	cd backend && python -m venv .venv && $(PY) -m pip install -r requirements.txt
	cd frontend && npm install

dev-backend:  ## 本地启动后端（uvicorn，需 backend/.env）
	cd backend && $(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:  ## 本地启动前端（next dev，默认连 http://localhost:8000）
	cd frontend && npm run dev
