# PROJECT_CONTEXT.md — 项目全景理解基线

> 生成日期：2026-09-23。
> 本文由对项目源码的逐文件实际阅读整理而成（非根据 README/文件名推测），作为后续所有需求分析、方案讨论与开发 Prompt 生成的事实基线。
> 原则：只记录当前真实状态，不含任何期望或规划。若代码与本文冲突，以代码为准并回改本文。

---

## 1. 项目定位

**电商 AI 客服 Agent 演示平台**（全栈、中文场景）：

- 一个真实可用的迷你电商站点：登录注册、商品浏览、下单、订单/物流/退款/投诉管理、知识库管理、实时指标看板。
- 一个悬浮 AI 客服助手"小易"（FloatingAIAssistant）：能查真实订单/物流/库存/优惠券，走**带用户确认闸门**的退款与投诉创建流程，基于 RAG 回答平台规则类知识问题，支持跨域多任务协作与主动待办提醒，并提供完整 Agent 决策 Trace（Debug 面板可视化）。
- 定位是演示/教学级项目（"demo"在代码与配置中反复出现），非生产部署。安全、持久化、鉴权均为演示级实现（见 §14）。

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 15（App Router）、React 19、TypeScript、Tailwind CSS 3（Dark Premium 视觉体系，Design Token 化）、lucide-react、react-markdown + remark-gfm |
| 后端 | Python、FastAPI 0.115、pydantic-settings、AsyncOpenAI SDK 1.58（OpenAI 兼容接口，当前配置指向 DeepSeek：`deepseek-v4-flash`）、PyPDF2、python-multipart |
| 数据库 | MySQL（库名 `ai_agent_commerce_demo`，约 20 张表，pymysql 直连，无 ORM） |
| 向量库 | qdrant-client 1.19 **本地模式**（纯 Python，持久化于 `backend/vector_store/qdrant/`）。首选 ChromaDB 因 Windows 下 Rust 绑定崩溃而回退，历史包袱：存储模块文件名仍为 `chroma_store.py` |
| Embedding | 默认本地 `sentence-transformers` + `BAAI/bge-small-zh-v1.5`（512 维，查询侧带官方 instruction 前缀）；可切 OpenAI 兼容 Embedding API（`embedding_provider.py` 工厂，支持测试注入） |
| 测试 | pytest 8.3 + httpx（Starlette TestClient，SSE 端点测试） |
| 部署 | Docker Compose 三服务（MySQL 8 + 后端 + 前端），一键 `docker compose up -d`，首启自动建库+种子用户+演示数据+RAG 索引重建（见 §4.1） |

## 3. 目录结构导览（关键路径）

```
├── PROJECT_CONTEXT.md               # 本文
├── README.md                        # 公开仓库主页（3 分钟看懂：定位/QuickStart/实测指标）
├── docs/ARCHITECTURE.md             # 深入架构文档（分层/模块职责/流程/设计决策/技术债）
├── docs/screenshots/                # 截图占位目录
├── docker-compose.yml               # 一键全栈编排（db/backend/frontend + 命名卷持久化）
├── backend/
│   ├── Dockerfile                   # 后端镜像（EMBEDDING_PRELOAD 双变体：本地 BGE 2.3GB / slim 412MB）
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口 + lifespan（路由/工具/FSM/workflow 初始化 + embedding 预热）
│   │   ├── core/config.py           # 全部环境变量集中配置（pydantic-settings，读 backend/.env）
│   │   ├── api/                     # HTTP 层：chat / commerce / rag / metrics / architecture
│   │   ├── agents/                  # Agent 决策核心：agent.py(主编排~1900行)、classifier、coordinator、enhanced_flow、context_facts、complaint_intent
│   │   ├── agent/                   # 多轮对话基座：memory/session、slots/slot_manager、state_machine/(refund_fsm, logistics_fsm)、interrupt、recovery
│   │   ├── router/                  # flow_registry + agent_router.route()（意图→Flow 查表调度）
│   │   ├── flows/                   # 9 个业务 Flow（refund/logistics/order/product/knowledge/coupon/ticket/human_transfer/general）
│   │   ├── tools/                   # tool_registry(11工具)、tool_router(参数提取与决策)、executors/tool_executor(统一执行)、implementations/
│   │   ├── knowledge_agent/         # 知识问答独立 Agent：services(KnowledgeWorkflow/KnowledgeAgent)、query_understanding、context、management
│   │   ├── rag/                     # RAG 基础设施：pipelines、services(retrieval_service 融合检索)、vectorstore(qdrant 实现的 chroma_store.py + embedding_provider)、chunkers(父子块)、loaders
│   │   ├── workflow/                # ⚠️ 大型编排引擎（~25 文件）：已建成但基本未接入聊天主链路（见 §14.1）
│   │   ├── database/                # connection.py(pymysql) + repositories.py(~1120行，全部 SQL 的唯一边界)
│   │   ├── services/                # llm.py(唯一 LLM 通道+SSE ContextVar)、proactive.py(主动事件安全封装)、response_style.py
│   │   ├── prompts/                 # 各 Flow 系统提示词 + router 分类提示词
│   │   ├── schemas/、models/        # IntentType/Trace 数据类、统一响应信封 BaseResponse
│   │   └── architecture/production.py  # 生产架构声明表（生产入口、intent→flow/agent/tool 映射、已移除层清单）
│   ├── database/schema.sql          # MySQL 建库建表（另有 demo_minimal_cn.sql / reset_empty.sql / docker_seed_users.sql）
│   ├── Dockerfile                   # （容器）双变体构建：EMBEDDING_PRELOAD=true 预下载 BGE；false 走 OpenAI 兼容 Embedding（slim）
│   ├── knowledge_base/              # 真实知识库文档（~70 个 txt，原子知识卡风格，按 refund/logistics/coupon/membership/complaint/sop/operation/faq/product 分类）
│   ├── vector_store/qdrant/         # 向量持久化（gitignore）
│   ├── workflow_repository/         # workflow 引擎的 JSON 定义与 trace 落盘（gitignore）
│   ├── evaluation/                  # 路由评测(dataset.py/run_eval.py) + RAG 评测(rag_dataset.py 30条/run_rag_eval.py)
│   ├── scripts/                     # docker_init（容器启动前置：等 MySQL/空索引重建）/ smoke_test / golden_question_validation / 数据重置脚本
│   ├── rebuild_rag_index.py         # 全量重建向量索引（--force 清空重建）
│   └── tests/                       # 27 个测试文件 + conftest.py（强制 EMBEDDING_WARMUP=false / HF_HUB_OFFLINE=1）
└── frontend/
    ├── app/                         # 13 条路由：首页/商品(列表+详情)/订单(列表+详情)/售后/投诉/知识库/指标/登录/注册/个人中心
    ├── components/chat/FloatingAIAssistant.tsx   # AI 浮窗核心（~1540 行）：上下文注入、会话、Trace/卡片渲染
    ├── components/debug/DebugPanel.tsx           # Agent Trace 可视化（含 RAG 检索透明化区块）
    ├── components/knowledge/、platform/          # 知识库上传组件、站点外壳
    ├── services/                    # chat.ts(SSE流式)/commerce.ts/knowledge.ts/metrics.ts/format.ts
    └── types/                       # message.ts / trace.ts(AgentTraceData) / knowledge.ts
```

## 4. 整体架构与数据流

```
浏览器（Next.js，Dark Premium 商城 + AI 浮窗）
  │  fetch（统一信封 ApiResponse<T>）
  ▼
FastAPI（backend/app/main.py，端口默认 8000）
  ├── /api/v1/chat|chat/stream ──► agents/agent.py run()  ←—— 生产聊天入口（唯一）
  │        ├── Session（内存 dict，TTL 30min）
  │        ├── 投诉/退款确认闸门（写库前强制确认 + 查重）
  │        ├── classifier（规则层 → LLM）→ router → flows/（9个）
  │        ├── agent/ FSM + Slot Filling（refund/logistics 需要 order_id）
  │        └── tools/ tool_executor ──► MySQL repositories（真实业务数据）
  │                                   └── services/llm.py（DeepSeek 兼容 API；SSE 经 ContextVar 流式）
  ├── /api/rag/* ──► knowledge_agent（上传/同步/列表）──► 知识管道 ──► qdrant 本地向量库
  ├── /api/commerce/* ──► database/repositories.py ──► MySQL（电商业务 + 洞察 + 主动事件）
  ├── /api/metrics ──► 实时 SQL 聚合（无假数据）
  └── /health、/api/architecture/production
```

关键架构事实：

- **生产聊天入口唯一**：`/api/v1/chat`（及流式变体），由 `app/architecture/production.py` 声明为 canonical entry；早期 LangGraph 实验层（app.graph/app.state/app.workflows/mock_backend）已移除。
- **知识问答生产链路**：`KnowledgeFlow → KnowledgeWorkflow → KnowledgeAgent → knowledge_search 工具 → RetrievalService → VectorStore`；直连 `rag_answer` 的 legacy RAGFlow 分支仍在 `agent.py` 中但被硬编码开关 `production_disable_legacy_rag = True` 关闭。
- **`app/workflow/` 引擎（AgentGraph/SupervisorAgent/Checkpoint/Branch/Governance/Handoff 等）不在聊天主链路上**：仅启动时 `initialize_workflow_system()` 注册，主链路只借用其 `decision_tracer` 写 trace JSON（`backend/workflow_repository/trace/decision_*.json`）。
- **数据库边界统一**：所有 SQL 都在 `database/repositories.py`；工具层不直接写 SQL。
- **前端→后端上下文协议**：前端把页面快照与任务指令以魔法文本注入用户消息（见 §15），后端多处 split 解析。

### 4.1 Docker 部署体系（2026-09-23 新增）

- **一键全栈**：`docker compose up -d` 起 MySQL 8 + 后端 + 前端；命名卷 `mysql_data`/`qdrant_data` 持久化；二启幂等（initdb 只在空卷跑、空索引才重建）。
- **MySQL 首启初始化链**（`/docker-entrypoint-initdb.d/` 字典序）：`01-schema.sql`（建表）→ `02-seed-users.sql`（**docker_seed_users.sql**，种子演示用户 USR_DEMO_001/demo123456 + 地址；因 demo_minimal_cn.sql 只引用"最新已存在用户"不建用户，空库直接跑会 NULL 失败）→ `03-demo.sql`（演示数据）。
- **后端容器 CMD 前置** `scripts/docker_init.py`：等 MySQL（60s 兜底重试）→ qdrant 索引为空则调 `rebuild_rag_index.run(force=True)`（重建后 client 已关闭，不能再 count）→ uvicorn。
- **Embedding 双变体**（build arg `EMBEDDING_PRELOAD`）：`true` 默认（torch CPU 索引安装 + BGE 预下载进镜像层，HF_HOME=/opt/hf-cache，镜像 2.3GB，离线可用）；`false` slim（剔除 torch/sentence-transformers，412MB，配 `EMBEDDING_PROVIDER=openai` 走 API，代码侧 embedding_provider 懒加载保证可 import）。
- **国内网络适配**：基础镜像经 daocloud 代理拉取 retag（auth.docker.io 被 DNS 污染）；Dockerfile 默认 `HF_ENDPOINT=hf-mirror.com`、`PIP_INDEX_URL=清华源`（PyPI 直连响应截断）；Dockerfile 不可用 `# syntax=docker/dockerfile:1`（会拉语法前端镜像失败）。
- **前端构建期注入**：`NEXT_PUBLIC_API_BASE_URL` 经 build arg 在 `next build` 时内联（compose 默认 localhost:8000，服务器部署需改）。
- **CORS 环境变量化（2026-09-23）**：`Settings.cors_extra_origins`（env `CORS_EXTRA_ORIGINS`，逗号分隔多来源），main.py 在 localhost 基础列表外合并解析；不配置时行为与原 localhost 列表完全一致（已 curl 双向实测）。服务器部署在 compose 设 `CORS_EXTRA_ORIGINS=http://<IP>:3000`。
- **Makefile 一键入口（根目录）**：up/down/logs/ps/build（含 slim 变体说明）/test/eval/rebuild-index/reset-data/install/dev-backend/dev-frontend。注意：PY 变量为 backend/ 内相对路径（配方均先 cd backend）；Windows Git Bash 无 make 二进制，验证靠严格解析脚本，Linux 服务器原生可用。

## 5. API 接口清单（实际存在的路由）

### 聊天（prefix `/api/v1`）
| 方法+路径 | 说明 |
|---|---|
| POST `/api/v1/chat` | 非流式聊天；返回统一信封，Debug 模式附 AgentTraceData |
| POST `/api/v1/chat/stream` | SSE 流式：`start → delta*（LLM 增量）→ done（完整信封）`；闸门类模板回复无 delta，前端两种都兼容 |

### 电商业务（prefix `/api/commerce`，全部走真实 MySQL）
- `GET /dashboard`（全库计数 + 最近审计/工作流记录）
- `POST /auth/login`、`POST /auth/register`（密码 SHA-256 无盐；token 即 user_id 明文）
- `GET /users/{user_id}`、`POST /users/{user_id}/addresses`
- `GET /categories`、`GET /products`、`GET /products/{product_id}`
- `POST /orders`、`GET /users/{user_id}/orders`、`GET /orders/{order_id}`（附带 logistics+refund）、`GET /orders/{order_id}/logistics`
- `GET /users/{user_id}/refunds`、`POST /refunds`（页面直提，无确认闸门——闸门仅约束 AI 链路）
- `GET /users/{user_id}/complaints`、`POST /complaints`（同上）
- `GET /agent/context`（按 user/product/order 拉取页面上下文快照）
- `GET /agent/insights`（洞察引擎：订单/退款/投诉状态 → 分级待办 + 快捷动作）
- `GET /agent/events`（扫描业务状态落**去重**主动事件，只返回未读）+ `POST /agent/events/{event_id}/read`
- `GET /agent/trace`（最近 agent_audit_logs + workflow_runtime_records）

### 知识库（prefix `/api/rag`）
- `POST /api/rag/upload`（上传文档 → 解析/父子块切分/向量化入库）
- `GET /api/rag/documents`、`GET /api/rag/documents/stats`、`GET /api/rag/categories`
- `POST /api/rag/sync`（从 knowledge_base 目录增量同步）

### 其他
- `GET /api/metrics`（看板全部指标实时聚合自 MySQL：计数、订单/退款/投诉状态分布、按工具成功率、按 Agent 流量分布；`prompt_iterations` 为唯一非实时字段，是明确标注的变更日志）
- `GET /api/architecture/production`（只读架构声明表）
- `GET /health`

## 6. 核心模块与职责

### 6.1 Agent 决策链（`app/agents/` + `app/agent/` + `app/router/`）

- **`agents/agent.py`（`run()`，~1900 行）**：唯一编排入口。顺序：生成 trace_id → Session 加载 → **pending 投诉/退款短路**（有草稿且本轮是确认/取消/等原因 → 直达对应闸门；无关话题则丢弃过期草稿继续正常路由）→ **Flow 恢复关键词检测**（挂起栈 + "继续"）→ **会话恢复分支**（FSM 进行中：中断检测 interrupt_manager / 继续槽位填充 + recovery_manager 重试上限）→ **多意图协调检测**（coordinator.should_coordinate）→ 正常分支：classify → 投诉闸门（intent=ticket）→ 退款闸门（intent=refund）→ [legacy RAG 已禁用] → FSM 注册检查（有 FSM 走 Slot Filling；无 FSM 直接 route）→ Slot Ready 时 **refund 强制改道确认闸门**（FSM 收齐槽位也不得绕过卡片）→ Flow 执行 → Trace 构建与落盘。
- **`agents/classifier.py`**：三层意图分类。①`_classify_business_intent_by_rule`：匹配前端注入的可信指令（"本轮任务：物流查询"等）与显式投诉创建/跟进（用 `complaint_intent.py` 判定，仅基于用户可见输入）；优惠券/推荐提示词复用 Flow 层常量作单一事实源。②`_classify_knowledge_intent_by_rule`：知识库关键词规则（带业务动作屏蔽词，防"退款规则"误入退款流程）。③LLM JSON 分类（`prompts/router.py`，temperature=0.1），解析失败/异常均兜底 GENERAL。**意图枚举 9 个**：refund / logistics_query / order_query / product_query / knowledge_query / coupon_query / ticket / human_transfer / general。
- **`router/agent_router.py` + `registry.py`**：`route()` 按 IntentType 查 flow_registry；置信度 < CONFIDENCE_HIGH 降级 GeneralFlow（记 downgraded）；启动时 `init_routes()` 注册 9 个 Flow。
- **`agents/coordinator.py`**：多意图检测（6 个领域正则）；`GATED_WRITE_DOMAINS = {refund, complaint}` 的隐含依赖剔除逻辑保证"退款+订单"不进协作而进单意图闸门；协作时无依赖域并行、有依赖域串行；**退款/投诉域绝不静默写库**（只读播报已有记录，或引导走确认流程）；最后 LLM 综合一次回答（含前端页面快照段）。
- **`agents/enhanced_flow.py`**：工具执行增强——重试（MAX_RETRY=2）、降级映射（物流失败→查订单）、**完整性契约** `TOOL_RESULT_CONTRACTS`（查订单须有物流键、查物流须有订单状态键，缺则自动 enrich 关联工具）、补全失败不再静默（注入 `[补全失败提示]`）、来源标签（`[实时查询]/[补全查询]/[页面快照补充]`）、信息整合守则进 LLM prompt。
- **`agents/context_facts.py`**：从 `[系统补充上下文]` 段按行前缀解析前端事实（订单/商品/物流/轨迹/退款/投诉），仅进 LLM 上下文，不落日志（PII 红线）。
- **`agents/complaint_intent.py`**：确认/否认/显式创建/跟进请求判定 + 投诉编号提取；是投诉闸门与 TicketFlow 只读跟进的判定基础。

### 6.2 多轮对话基座（`app/agent/`）

- **`memory/session.py`**：内存 dict 存储（`SESSION_TTL=1800s`）。Session 含 current_flow/current_state/waiting_for/slots/history(≤40条)/suspended_flows 栈/retry_count/**pending_complaint / pending_refund（确认闸门草稿）**。代码注释明示 Phase 5 应换 Redis，未做。
- **`state_machine/`**：`BaseFSM`（纯逻辑、无 LLM、无副作用）+ `RefundFSM`/`LogisticsFSM`（槽位：order_id 等；`get_initial_result` 首轮尽量提取，`process` 等待态宽松提取）+ `fsm_registry`（`init_fsm()` 启动注册）。
- **`slots/slot_manager.py`**：协调 FSM 与 Session，产出 `SlotFillingResult(ready/prompt/waiting_for/slots)`。
- **`interrupt/interrupt_manager.py`**：FSM 等待态时检测意图抢占（高优先级意图集合），支持挂起当前 Flow / 恢复挂起 Flow（`RESUME_KEYWORDS`）。
- **`recovery/recovery_manager.py`**：连续无效输入（MAX_RETRY_COUNT=3）→ clarify 或退出 Flow。

### 6.3 写操作确认闸门（安全核心，实现于 `agent.py`）

- **投诉闸门 `_handle_complaint_gate`**：创建类意图 → 未给原因则暂存草稿并追问；给了原因（剥离填充词判定 `_has_complaint_reason`）→ 关键词推断投诉类型（物流/质量/服务态度/售后）→ 返回 `pending_complaint` 元数据供前端渲染确认卡片；用户确认 → 三重查重（草稿收集后/首轮/建单前安全网）→ 调 `complaint_create`；失败保留草稿可重试；"确认"不明确 → 再问。
- **退款闸门 `_handle_refund_gate`**：对称结构（`_has_refund_reason`、`_extract_refund_reason` 汇集近 4 轮、`pending_refund` 卡片、`refund_apply`、已有退款则播报不重复创建）。
- 铁律（代码注释多处强调）：**AI 绝不静默建单/建退款**；TicketFlow 本身是只读 Flow（跟进真实投诉记录 + 创建指引），无任何写库路径。

### 6.4 工具层（`app/tools/`）

- **`tool_registry.py`**：11 个工具实例注册 + intent→tool 映射 + `AGENT_TOOL_PERMISSIONS`（Agent→Tool 权限表，SupervisorAgent 全量）。注册表：`logistics_query`、`refund_apply`、`product_query`、`complaint_create`、`knowledge_search`、`query_order`、`create_ticket`、`transfer_human`、`query_inventory`、`query_coupons`、`recommend_products`。
- **`tool_router.py`**：`select_tool()` 按意图决策；参数提取正则（订单号优先级：系统上下文"本轮优先处理订单号"→ 显式"订单号:"→ 紧邻/裸 ORD 前缀，不把裸数字当订单号）；`_detect_human_transfer` 仅基于用户可见输入（剥离 `[系统补充上下文`，防止指令文本劫持转人工，已随回归测试提交）；`select_tools_for_workflow()` 双工具编排（物流+退款）。
- **`executors/tool_executor.py`**：统一执行入口——input_schema 校验 → `asyncio.wait_for` 超时（默认 10s）→ 异常捕获 → `ToolExecutionResult`（含 latency/timed_out/to_trace_dict/to_context_string）。
- **各工具实现**：全部查/写真实 MySQL；写操作（refund_apply/complaint_create/create_ticket/transfer_human）成功后经 `services/proactive.py` 的 `emit_proactive_event` 安全落主动事件（吞异常不拖累主流程）；查询工具写 `agent_audit_logs` 审计。

### 6.5 RAG / 知识子系统（`app/knowledge_agent/` + `app/rag/`）

- **入库管道**：上传/同步 → loader → **ParentChildChunker**（父块 800/150 返回用，子块 250/50 检索用；父块 `chunk_type=parent` 不参与检索命中）→ embedding_provider → qdrant upsert（uuid5 确定性映射保证幂等）。`rebuild_rag_index.py --force` 全量重建（当前索引 ~70 文件 → 86 父块 / 297 子块）。
- **检索**：`retrieval_service.query_knowledge_fused()`——路 1 语义向量（上下文消解后的自然语言 query，min_score=0.35 校准值）；路 2 关键词 payload 包含匹配（英文型号词 + 查询理解正式术语 + 类别词）；**RRF(k=60) 融合**；`vector/keyword` 路由标注写入 chunks。
- **查询理解**（`knowledge_agent/query_understanding.py`）：规则快路径（口语词典 COLLOQUIAL_LEXICON + 商品型号别名 → 正式术语 + 分类推断）→ 置信度 ≥0.6 跳过 LLM；否则 LLM 改写（口语→正式检索 query + 分类）。指代消解由 `rag/services/context_builder.build_retrieval_query` 用历史完成。
- **`knowledge_search` 工具**（613 行）：消解 → 理解 → 融合检索 → 类别过滤（显式/LLM/关键词三路并集，防硬过滤误删）→ **两道校验**（语义无命中→expanded_query 重检一次；top-5 无关键实体→窄查询重检一次，补检结果过实体护栏）→ 同源扩展 → 规则重排（原子知识卡/商品型号加权）→ 父块组装（`parent_content`）→ 引用与约束构建 → 审计落库。debug_info 含 revalidation/routes/query_understanding（前端 DebugPanel 展示）。
- **`KnowledgeAgent`/`KnowledgeWorkflow`**：不访问业务数据库（护栏声明）；受限生成（只基于检索上下文，温度 0.2）；每步写 decision_tracer 事件；返回 Message.metadata 携带 knowledge_documents/chunks/citations/answer_source/trace。
- **`knowledge_agent/management.py`**：文档列表/统计/分类（供管理台 API）。

### 6.6 前端核心（`frontend/`）

- **`components/chat/FloatingAIAssistant.tsx`（~1540 行）**：全局悬浮 AI 助手。发送前 `buildContextPrompt` 组装：`[用户请求]`前缀（知识类）+ `[系统补充上下文 - 不要把本段当成用户原话]`（可信指令：本轮任务/优先订单号/登录用户/页面快照/订单-退款-投诉列表 + 防编造守则）。`detectCapability` 前端侧意图预判（knowledge 优先级最高）；`chooseTargetOrder` 按能力域智能选单；支持 SSE 流式渲染、pending 投诉/退款确认卡片、主动事件提醒条、演示脚本一键场景（8 大场景）、Trace 面板。
- **`services/chat.ts`**：`/api/v1/chat`（非流式）+ `sendChatMessageStream`（SSE 逐帧解析 start/delta/done/error）。
- **`components/debug/DebugPanel.tsx`**：Trace 可视化（意图/置信度/Flow/工具调用/RAG 多路检索分数与补检信息）。
- **13 条路由** 已统一 Dark Premium（P1–P5 视觉重塑完成，Design Token + accent 唯一主色 + lucide 图标 + reduced-motion 降级）。

## 7. 核心业务流程（端到端）

### 7.1 聊天主流程
1. 前端构造消息（用户输入 + 系统上下文）→ POST `/api/v1/chat/stream`。
2. `agent.run()`：Session 检查 → 草稿短路 → 恢复/中断/协调分支 → 分类。
3. 写操作意图进确认闸门；`logistics_query`/`refund` 进 FSM 收集 order_id（不足则 LLM 人格化追问，含情绪安抚；支持"转去别的事再回来"挂起恢复、3 次失败退出）。
4. Flow 执行：`tool_router` 提参 → `tool_executor`（10s 超时）→ `enhanced_flow`（重试/契约补全/快照兜底）→ 工具真实数据注入 prompt → `call_llm` 综合回答（SSE 下逐 token 推送）。
5. 全程构建 AgentTrace（steps/工具调用/reasoning/会话状态），`log_trace` 落盘；metadata 携带 pending 卡片、RAG 来源等；前端渲染回复 + 卡片 + Trace。

### 7.2 知识问答流程
分类 knowledge_query（规则层即命中）→ KnowledgeFlow 提取真实问题（剥离上下文，取 `[用户请求]` 后首行）→ 指代消解 → 查询理解（口语改写+分类）→ 融合检索 → 类别过滤 → 校验与补检 → 父块组装 → 受限生成（无命中则如实说"知识库中没有足够信息"，不编造）→ 返回引用。

### 7.3 主动服务流程
写操作成功 → 工具内 `emit_proactive_event` 落事件；前端轮询 `/agent/events` → 后端扫描订单/退款/投诉状态生成**去重**洞察事件（dedup_key=insight_id，已读不再推）→ 用户点"立即处理"把 action_prompt 直接发给 AI → 走正常聊天链路。

### 7.4 多意图协作流程
`should_coordinate`（≥2 域，写域依赖剔除）→ 并行无依赖域（订单/物流走 enhanced、商品按关键词）→ 串行有依赖域（退款/投诉只读播报或引导确认）→ LLM 综合回答；若明确要创建投诉且内容充分，落 pending 草稿让下一轮"确认"直达闸门。

## 8. 数据库与数据资产

- **MySQL `ai_agent_commerce_demo`**（`backend/database/schema.sql`）：users、user_addresses、brands、categories、product_collections(+items)、products、product_images、inventory(+history)、orders、order_items、carriers、logistics_shipments、logistics_tracking_events、refunds、complaints(+process_records/escalations)、supervisor_escalations、human_agent_status、**human_transfer_requests**（转人工真实排队写库）、**proactive_events**（dedup_key 唯一 + unread/read）、**agent_audit_logs**（agent_name/tool_name/结果 JSON/success/workflow_id/session_id）、workflow_runtime_records。注意：schema 中部分默认值为英文（'active'），repositories 与演示数据用中文状态（'正常'/'已通过'等），metrics.py 里靠硬编码集合映射两套状态值。
- **向量库**：`backend/vector_store/qdrant/`（collection `knowledge`，cosine，512 维）。
- **知识库文档**：`backend/knowledge_base/`，原子知识卡风格（标准答案/适用条件/不适用场景/回答要求），按 refund/logistics/coupon/membership/complaint/sop/operation/faq/product 组织；另有 `Enterprise_Knowledge_Base_V1_Report.txt`。
- **workflow_repository/**：workflow 引擎的 agent/agent_capability/business_domain_* JSON 定义 + decision_tracer 落盘的 trace JSON（均 gitignore）。

## 9. 测试与评测体系

- **单测**：`backend/tests/` 22 个测试文件 + `conftest.py`（强制 `EMBEDDING_WARMUP=false`、`HF_HUB_OFFLINE=1`，测试不真实加载模型）。覆盖：聊天流式、分类器上下文安全、投诉跟进路由/意图/待确认流程、协调器安全、优惠券运行时/路由、embedding 预热、转人工入队、知识分类过滤、两个 FSM 的 order_id、多来源整合、订单号提取、订单查询路由、个性化推荐、主动事件、RAG 评测集与向量库、路由上下文、tool_router 上下文安全。最近全绿 **130 passed**（须用 `backend/.venv` 跑，系统 Anaconda 缺依赖）。测试依赖本机 MySQL。
- **评测**：`evaluation/run_eval.py`（路由层评测：离线模式禁用 LLM 逼规则层独立作答，可入 CI；`--live` 在线全量）+ `evaluation/run_rag_eval.py`（30 条标注用例，10 类 × ≥2 条含口语变体 + 3 条无答案；指标 top1/top3 命中率、无答案过滤率，`--fail-under` 可设阈值非零退出）。黄金问题校准（`RETRIEVAL_MIN_SCORE=0.35`）有脚本与报告支撑。
- **GitHub Actions CI（2026-09-30 起）**：`.github/workflows/ci.yml`，main push/PR 触发，backend（MySQL8 服务容器 + 三段 SQL 灌库 → pytest 130 → rebuild 索引 → RAG 评测 `--fail-under 0.8` → 路由评测）+ frontend（npm ci + build）两 job 并行，README 有徽章。**关键坑（已固化注释）**：torch 必须从 CPU 索引装（PyPI 默认 CUDA 构建的 embedding 数值有漂移，曾致无答案用例「怎么申请营业执照」top1=0.4653 未过滤、无答案过滤率 66.67% 失败；换 CPU 构建后 100% 恢复）；pytest 步骤 HF_HUB_OFFLINE=1，rebuild 步骤不设（要联网下模型）。
- **脚本**：`scripts/smoke_test.py`、`smoke_multisource.py`（端到端冒烟）、`golden_question_validation.py`、`diagnose_knowledge_runtime_consistency.py`、`reset_business_data.py`。

## 10. 已实现功能清单（截至 2026-09-23）

- [x] 意图分类（规则两层 + LLM JSON，容错兜底）
- [x] 9 个业务 Flow + 置信度降级路由
- [x] 11 个真实数据库工具 + 统一执行器（校验/超时/Trace/审计）
- [x] 多轮对话：Session/FSM/Slot Filling/中断挂起恢复/重试退出/人格化追问
- [x] 投诉与退款确认闸门（三重查重、草稿可重试、卡片确认、绝不静默写库）
- [x] 多 Agent 跨域协作（并行工具 + 写域安全 + LLM 综合）
- [x] RAG：真实 BGE embedding + qdrant 本地库、父子块、口语查询理解、多路融合检索（RRF）、二次补检、受限生成与引用
- [x] 知识库管理台（上传/同步/列表/统计/分类）
- [x] 主动服务事件（业务扫描 + 去重落库 + 未读推送 + 一键处理）
- [x] SSE 真流式（ContextVar 方案，Flow 零改动）
- [x] 完整 Agent Trace + 前端 Debug 面板（含 RAG 检索透明化）
- [x] 多来源信息整合（完整性契约、页面快照兜底、来源标签、信息整合守则）
- [x] 电商基础：登录注册（演示级）、商品/订单/物流/退款/投诉管理、下单
- [x] 实时指标看板（100% SQL 聚合）
- [x] 评测集（路由 + RAG 30 条）与冒烟脚本
- [x] 前端 Dark Premium 视觉体系（P1–P5 全部完成）
- [x] 转人工真实排队（human_transfer_requests 落库）
- [x] Docker 一键部署（compose 三服务，首启自动初始化，Embedding 双变体，见 §4.1）

## 11. 当前工作区状态（已全部提交，2026-09-23）

- 分支 `main`，无未提交改动，未 push。
- 根目录文档体系：`README.md`（重写版，含实测指标）+ `docs/ARCHITECTURE.md` + `docs/screenshots/` 占位；旧开发文档与交付报告已清理出库。
- Docker 化产物已提交（compose/Dockerfile×2/dockerignore×2/docker_init.py/docker_seed_users.sql）。
- `.gitignore` 已补全：`.codebuddy/`、`*.tsbuildinfo`、`backend/demo_cleanup_backup_*.json`。
- 运行时产物（vector_store/workflow_repository/uploads/评测报告 JSON）均已 gitignore，仓库不跟踪。
- git 作者身份已统一为 chlniubi23 <192792980+chlniubi23@users.noreply.github.com>（2026-09-30 用户侧重写完成）；已打 tag `v1.0`（含 MIT LICENSE 定稿，61f853d），待用户侧用 gh CLI 创建仓库并 push（含 tag）。

## 12. 关键配置（backend/.env.example 摘录）

`OPENAI_BASE_URL/MODEL`（DeepSeek 兼容）、`OPENAI_TIMEOUT=60`/`OPENAI_MAX_RETRIES=2`、`MYSQL_*`（ai_agent_commerce_demo）、`EMBEDDING_PROVIDER=local`/`EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5`/`EMBEDDING_DIM=512`/`EMBEDDING_WARMUP=true`（测试必须 false）、`QDRANT_PERSIST_DIR/COLLECTION`、`CHUNK_SIZE=500`/`CHUNK_OVERLAP=100`（upload/rebuild 统一入口用；父子块切分器内部为 800/150+250/50）、`RETRIEVAL_MIN_SCORE=0.35`。前端 `NEXT_PUBLIC_API_BASE_URL`（默认 http://localhost:8000）。

## 13. 关键约定与红线（代码中明确声明）

1. **AI 绝不静默建单**：投诉/退款必须用户确认后才写库；TicketFlow 只读。
2. **意图判定只用用户可见输入**（`split("[系统补充上下文")` 前段）；系统上下文只作可信指令与 LLM 事实来源。
3. **PII 边界**：前端注入的个人事实仅进本轮 LLM 上下文，不新增日志/不持久化。
4. **信息整合守则**：交叉核对多来源；单一来源缺失先查其他来源；严禁把"单一来源没有"说成"系统没有"；严禁编造单号/金额/日期。
5. **测试环境**禁止真实加载 embedding 模型（conftest 强制）。
6. Windows 部署约束：torch 锁 2.6.0 CPU 版（2.14 c10.dll 崩溃）；向量库必须用 qdrant 本地模式（ChromaDB 崩溃）。

## 14. 已知问题、技术债务与风险（按影响排序）

1. **`app/workflow/` 平行引擎未接线**：~25 个文件（SupervisorAgent/AgentGraph/Checkpoint/Branch/Governance/Handoff/Recovery/Resume 等）+ `workflow_repository/` 全套 JSON 定义，启动时初始化但聊天主链路不执行；仅 `decision_tracer` 被知识链路借用落 trace JSON。维护面大、极易误导（改"工作流"容易改到不在跑的代码）。择机清理或真正接线是需要决策的架构事项。
2. **会话状态纯内存**：Session（含 pending 投诉/退款草稿、挂起栈）存进程 dict；重启丢失、多 worker 不共享、无持久化。
3. **`agents/agent.py` 体量与重复**：~1900 行；投诉类型关键词推断在 3 处重复（闸门两分支 + 协调器落草稿）；`_finish`/Trace/metadata 构造大量复制。主链路改动漏改分支的风险高。
4. **前后端魔法文本协议**：`"[系统补充上下文"`、`"[用户请求]"`、`"本轮任务：xx"`、`"当前登录用户：USRxxx"` 等字符串贯穿前端拼接与后端多处解析（classifier/tool_router/context_facts/knowledge flow/转人工/推荐），措辞改动会静默破坏路由与闸门；历史上已多次因此修复。
5. **安全为演示级**：SHA-256 无盐密码；token=user_id 明文；commerce API 无鉴权中间件（凭 user_id 可查任意用户数据，IDOR）；个人数据整段进 LLM 上下文（边界靠 §13.3 约定）。
6. **规则关键词多层分布**：classifier / tool_router / query_understanding / 前端 detectCapability 各自维护关键词表（部分已做单一事实源复用），漂移风险仍在。
7. **状态值中英文混用**：schema 默认英文（'active'）vs 运行数据中文（'正常'）；metrics.py 硬编码集合映射，脆弱。
8. **命名/遗留包袱**：`chroma_store.py` 实为 qdrant 实现；legacy RAGFlow 死分支靠硬编码开关关闭（`LEGACY_RAG_DEPRECATION` 标注 removal_candidate）；`coupon.py` 注释称"有 user_coupons 表后换 SQL"（优惠券数据当前来源见该 Flow 实现）。
9. **巨型前端组件**：`FloatingAIAssistant.tsx` ~1540 行，上下文注入/会话/渲染/演示逻辑集中。
10. **工程杂项**：测试依赖本机 MySQL，CI 化需先解耦；多轮 LLM 调用（分类/改写/追问/综合）对无结构化缓存的依赖使延迟与成本集中在 DeepSeek API；`demo_cleanup_backup_*.json`、`.codebuddy/`、`*.tsbuildinfo` 已于 2026-09-23 补全 gitignore 并移出跟踪（磁盘保留）。

## 15. 生成开发 Prompt 时必须知道的约束

- 改聊天链路 = 改 `agents/agent.py` + 对应 flow/tool；**不要**把需求映射到 `app/workflow/`（未接线）。
- 任何触碰前端上下文注入或后端解析的改动，必须同步核对 §13.2 的所有解析点（前后端魔法文本是隐式契约）。
- 写操作相关改动必须保持确认闸门语义与三重查重；相关安全测试：`test_coordinator_safety`、`test_pending_complaint_confirmation`、`test_complaint_followup_routing`、`test_tool_router_context_safety` 等。
- 检索相关改动跑 `python -m evaluation.run_rag_eval`（基线报告在 gitignore 的 rag_baseline_report.json）与路由评测 `run_eval`；`RETRIEVAL_MIN_SCORE=0.35` 不得随意回退。
- 完成标准参照既有交付报告惯例：`pytest tests/ -q` 全绿 + `npm run build` 通过 + 端到端冒烟（scripts/smoke_*.py）+ 交付报告。
