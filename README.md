# 小易 AI 电商助手（E-commerce Customer Service Agent）

任务执行型电商客服 Agent（全栈）：用户用自然语言提出需求，Agent 结合页面/用户上下文完成意图识别 → 业务路由 → 工具调用 → 真实 MySQL 读写，并对退款、投诉等高风险写操作执行"收集原因 → 确认卡片 → 查重 → 落库"的确认闸门。**本地演示原型，未做生产化鉴权，请勿直接暴露公网。**

## 核心能力

- **确定性优先的路由**：规则强信号短路 + LLM JSON 分类兜底 + 置信度降级；路由层评测集 71 条用例，离线规则层 / 在线全量均 100%（`backend/evaluation/`）
- **高风险写操作安全设计**：退款/投诉必须经确认卡片；三层幂等查重；确认词收紧为明确指令（弱肯定词不触发建单）；FSM/中断/多域协调全路径覆盖闸门，AI 绝不静默写库
- **多轮任务状态管理**：FSM + 槽位填充 + 中断挂起/恢复 + 会话级确认草稿（失败可重试）
- **SSE 真流式**：`POST /api/v1/chat/stream`（start → delta* → done），所有 Flow 共用 `call_llm` 通道零改造获得流式；前端流式失败自动回退整包接口
- **写路径原子性**：下单（4 连插）、退款（插单+订单状态同步）、投诉（2 连插）单连接事务，失败整体回滚
- **主动服务**：业务状态扫描 → 去重落库 → 未读事件推送，已读落库不重复打扰
- **双数据通道**：实时业务事实走 MySQL；平台规则/SOP/商品知识走 KnowledgeAgent + 本地向量库（真实语义 Embedding：默认本地 BGE `BAAI/bge-small-zh-v1.5`，可切 OpenAI 兼容 API；qdrant-client 本地模式持久化）

## 技术栈

Next.js 15（App Router，React 19，TS strict）· FastAPI · MySQL（pymysql）· OpenAI 兼容 API（DeepSeek 等，60s 超时 + 重试）· RAG：sentence-transformers（本地 BGE）+ qdrant-client 本地模式

> 向量库选型说明：首选 ChromaDB 在本项目 Windows 环境不可用（Rust 绑定 upsert 崩溃），按开发方案回退 qdrant-client 本地模式（纯 Python），`VectorStore` 对外接口不变。Windows 下 torch 锁定 2.6.0 CPU 版（2.14 存在 c10.dll 初始化失败问题）。

## 快速启动

```powershell
# 1. 数据库（MySQL 8.x）
cmd.exe /c "mysql -u root -p < backend\database\schema.sql"
# 启动前后端后在 /register 注册用户，再导入演示数据
cmd.exe /c "mysql -u root -p ai_agent_commerce_demo < backend\database\demo_minimal_cn.sql"

# 2. 后端（复制 backend/.env.example 为 backend/.env 并填入 LLM Key 与 MySQL 密码）
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 3. 前端（复制 frontend/.env.local.example 为 frontend/.env.local）
cd frontend
npm install
npm run dev   # http://localhost:3000
```

知识问答需先构建索引（首次会自动下载本地 Embedding 模型约 100MB，可设 `HF_ENDPOINT=https://hf-mirror.com` 加速）：

```powershell
cd backend
python rebuild_rag_index.py            # 增量：按文件内容 hash 跳过未变化文件
python rebuild_rag_index.py --force    # 全量：清空 collection 后重建（收集 TXT/MD）
```

## 测试与评测

```powershell
cd backend
python -m pytest tests/ -q              # 94 个单测（mock LLM/DB/Embedding，可离线运行）
python -m evaluation.run_eval           # 路由层评测（离线：规则层 63/63）
python -m evaluation.run_eval --live    # 在线：含 LLM 层，全量 71/71
cd ../frontend && npm run build         # 生产构建
```

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [项目开发文档.md](项目开发文档.md) | 架构、目录地图、API、Agent 运行机制、启动与排查 Runbook |
| [产品开发文档.md](产品开发文档.md) | 产品定义、用户旅程、核心流程规范、质量与风险 |
| [痛点.md](痛点.md) | 传统电商客服痛点分析（立项依据） |

## 已知限制（演示定位）

会话与确认草稿为进程内存态（生产应换 Redis）；无服务端鉴权体系；RAG 已升级为真实 Embedding + qdrant 本地向量库，但尚无 hybrid/rerank 与索引版本化。详见项目开发文档第 15 节。
