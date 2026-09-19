# 开发 Prompt：知识库 RAG 真实落地改造（N-gram 演示版 → 真实 Embedding + 向量数据库）

> 交付方式：将本文档整体交给一个新的开发对话执行。
> 执行前请先完整阅读"背景与现状"与"注意事项"，再按任务顺序开发。
> 项目根目录：`E-commerce Customer Service Agent/`（后端 `backend/`）

---

## 一、目标

把当前"演示级 RAG"（纯 Python N-gram Hash Embedding + JSON 文件向量库）替换为真实生产级 RAG 链路：

```
知识文件 → 文本切分 Chunking → 真实 Embedding 向量化 → 向量数据库持久化
→ 用户提问 → 语义检索（含元数据过滤）→ 检索结果注入 Prompt → LLM 受约束回答
```

**改造边界（重要）**：
- 只替换 RAG 的存储与向量化底座（`app/rag/vectorstore/`）及必要的适配点；
- **不改** Agent 主链路（`agents/agent.py`）、分类器、路由、FSM、确认闸门；
- **不改** KnowledgeFlow → KnowledgeWorkflow → KnowledgeAgent → knowledge_search 的调用拓扑；
- **不改** 业务 MySQL 层；
- 保持 82 个现有单测离线（不依赖网络、不依赖真实模型下载）全部通过。

## 二、背景与现状（已核实，可直接信任）

当前实现（`backend/app/rag/vectorstore/chroma_store.py`）：
- `embed_text()`：384 维 N-gram Hash Embedding，纯 Python；
- `VectorStore` 类：内存 list + JSON 文件持久化（`backend/vector_store/vectors.json`），线程锁；
- 全局单例 `chroma_store`（文件名有误导，实际与 ChromaDB 无关）。

`chroma_store` 的全部消费方（改造时逐一核对）：

| 文件 | 使用的方法 | 特殊情况 |
| --- | --- | --- |
| `app/rag/services/retrieval_service.py` | `count()`、`query()` | 返回结构 `[{chunk_id, content, metadata, distance, relevance_score}]`，消费方依赖此结构 |
| `app/rag/pipelines/knowledge_pipeline.py` | `add_chunks(chunks)` | 返回成功入库数量 |
| `app/tools/knowledge_search_tool.py` | `query()`、`count()`、**`_data` 私有字段** | `_expand_same_source_chunks()`（约 350 行）直接遍历 `chroma_store._data` 实现同源扩展，**必须重构** |
| `app/api/rag.py` | `count()` 等 | sync/upload 端点 |
| `rebuild_rag_index.py` | `KnowledgePipeline` + `count()` | 切片配置 600/80，与其他入口不一致 |

关键契约（必须原样保留）：
1. `chroma_store` 单例的 4 个公开方法签名与返回结构不变；
2. `Chunk` 对象（`app/rag/schemas/document.py`）的 `chunk_id / content / metadata` 结构不变；
3. metadata 中 `file_name`、`file_id`、`knowledge_category`/`category`、`source` 等键名不变（检索过滤依赖它们）；
4. `RetrievalService.query_knowledge()` 的返回（`RetrievalResult`）结构不变；
5. `knowledge_search` 工具的输入输出（ToolResult.data 各字段：query/retrieval_query/documents/chunks/citations/final_context/debug_info 等）不变，前端 Trace 与确认卡依赖它们；
6. 查询理解层（`knowledge_agent/query_understanding.py` 的指代消解与口语改写）**保留不动**，它仍然有价值。

## 三、技术选型（已定，不要更改方向；如遇阻按第四节回退方案处理）

| 组件 | 选型 | 理由 |
| --- | --- | --- |
| Embedding（默认） | `sentence-transformers` + `BAAI/bge-small-zh-v1.5`（512 维，本地推理） | 中文优化、免费离线、无需新增 API Key；CPU 推理单条查询 <100ms 可接受 |
| Embedding（备选） | OpenAI 兼容 Embedding API（`openai` SDK，独立 base_url/key 配置） | 供应商/部署环境不支持本地模型时的切换通道；通过配置项选择，不做运行时混用 |
| 向量数据库 | ChromaDB `PersistentClient`，`cosine` 空间，持久化目录 `backend/vector_store/chroma/` | 本地持久化、原生 metadata 过滤；项目注释中原有规划即此 |
| Chunking | 保留现有 `RecursiveChunker`，统一配置为 `CHUNK_SIZE=500`、`CHUNK_OVERLAP=100` | 现有切分器已是递归按段落/句子切分，够用；只收敛三处不一致的配置 |

**新增依赖（`backend/requirements.txt`，追加并固定版本）**：
```
sentence-transformers
chromadb
```
版本由开发对话安装时锁定（pin 到实际安装版本）。注意：`sentence-transformers` 会引入 torch（Windows CPU 版即可）；如磁盘紧张可安装 `torch --index-url https://download.pytorch.org/whl/cpu`。

**新增配置（`app/core/config.py` 的 Settings + `backend/.env.example`，同步更新根目录 `.env.example`）**：
```env
# Embedding
EMBEDDING_PROVIDER=local          # local | openai
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_API_KEY=                # 仅 provider=openai 时使用
EMBEDDING_BASE_URL=               # 仅 provider=openai 时使用
EMBEDDING_DIM=512
# 向量库
CHROMA_PERSIST_DIR=vector_store/chroma   # 相对 backend/ 
CHROMA_COLLECTION=knowledge
# 切片（统一三处入口）
CHUNK_SIZE=500
CHUNK_OVERLAP=100
# 检索
RETRIEVAL_MIN_SCORE=0.35          # 真实 Embedding 的相关性下限，第五步用黄金问题校准后回填
```

## 四、任务分解（按顺序执行，每步有验证点）

### 任务 0：依赖环境验证（先做，避免后半程返工）

在 `backend/` 下创建/激活虚拟环境后验证：
```powershell
pip install sentence-transformers chromadb
python -c "from sentence_transformers import SentenceTransformer; m=SentenceTransformer('BAAI/bge-small-zh-v1.5'); print(m.encode(['测试']).shape)"
python -c "import chromadb; c=chromadb.PersistentClient(path='./_probe'); col=c.get_or_create_collection('t'); print('chroma ok')"
```
- 若 `chromadb` 因 onnxruntime 在 Windows 报 DLL 加载错误：执行回退方案——改用 `qdrant-client`（本地模式，纯 Python 实现，`pip install qdrant-client`），其余任务不变（实现同一接口即可）。**此决策点写入提交说明。**
- 若 `bge-small-zh-v1.5` 模型下载失败（网络），先配置 HuggingFace 镜像（`HF_ENDPOINT=https://hf-mirror.com`）重试；仍失败则改用 openai provider 完成开发，本地 provider 保留代码但标注未验证。

### 任务 1：Embedding Provider 抽象层

新建 `app/rag/vectorstore/embedding_provider.py`：
- 定义协议 `EmbeddingProvider.embed(texts: list[str]) -> list[list[float]]` 与 `dimension` 属性；
- `LocalBGEProvider`：懒加载 `SentenceTransformer`（模块级单例，避免每次 import 加载模型）；查询与入库统一走它；
- `OpenAICompatProvider`：用 `openai` SDK 的 `embeddings.create`，独立 base_url/key，批量请求 + 失败重试；
- 工厂 `get_embedding_provider()` 按 `settings.embedding_provider` 返回单例；
- bge 查询侧使用官方推荐的 query instruction 前缀（`为这个句子生成表示以用于检索相关文章：`），入库侧不加——在 Provider 内以 `embed_query()` / `embed_documents()` 两个方法区分。

### 任务 2：VectorStore 实现替换（保持接口不变）

改造 `app/rag/vectorstore/chroma_store.py`（保留文件名与单例名 `chroma_store`，最小化 import 改动）：
- `VectorStore` 内部改为 ChromaDB `PersistentClient` + cosine collection；
- `add_chunks(chunks)`：批量 `provider.embed_documents(...)`，`collection.upsert(ids=chunk_id, embeddings, documents=content, metadatas=metadata)`——用 upsert 修复旧实现"重复运行 rebuild 脚本会因 id 去重而静默跳过、但内容更新不生效"的问题；
- `query(query_text, top_k, where)`：`provider.embed_query()` → `collection.query(query_embeddings, n_results, where)`；where 参数沿用现有"key=value 精确匹配"语义映射到 Chroma 的 where 条件；
- 返回结构保持 `[{chunk_id, content, metadata, distance, relevance_score}]`，其中 `relevance_score = max(0, 1 - distance)`（cosine 距离）；
- `count()` → `collection.count()`；`delete_by_file_id(file_id)` → `collection.delete(where={"file_id": file_id})`；
- **新增公共方法 `get_by_file_name(file_name) -> list[dict]`**（返回同源 chunks 的 id/content/metadata，无需向量），供任务 5 重构 `_expand_same_source_chunks` 使用；
- 删除 `embed_text()` N-gram 实现与 `_data`/`_load`/`_save` JSON 逻辑（旧 `vectors.json` 文件保留在磁盘上作为备份，不再读取）；
- 首次初始化若 collection 不存在则自动创建（cosine space）。

### 任务 3：切片配置统一

- 新建 `app/rag/constants/config.py` 中已有常量的统一来源（或直接读 Settings 的 `CHUNK_SIZE/CHUNK_OVERLAP`）；
- `KnowledgePipeline.__init__` 默认值改为读配置；
- `rebuild_rag_index.py` 的 `600/80` 硬编码改为同一配置；
- 确认 `api/rag.py` 的 upload 入口同样走配置。

### 任务 4：知识检索工具适配（`app/tools/knowledge_search_tool.py`）

1. `_expand_same_source_chunks()` 重构：删除对 `chroma_store._data` 的直接访问，改调任务 2 新增的 `get_by_file_name()`；行为保持"同源兄弟块并入候选池"不变；
2. **检索 query 调整**：`expanded_query` 不再把 `_expand_query_terms()` 的词表拼接进向量检索输入（语义 Embedding 下稀释查询向量）——向量检索只用"上下文消解后的自然语言 query"；`_expand_query_terms` 保留，但仅用于 `_rank_chunks_for_query` 的规则重排加分项；
3. `MIN_RELEVANCE_SCORE`（`retrieval_service.py`）从 0.01 改为读 `RETRIEVAL_MIN_SCORE` 配置；
4. 其余逻辑（类别过滤、同源扩展、规则重排、审计）保持不变。

### 任务 5：重建脚本与诊断脚本

- `rebuild_rag_index.py` 重写为"全量重建"：支持 `--force` 清空 collection 后从 `knowledge_base/knowledge/` 全量入库（默认增量时按 metadata 中记录的 `source` + 内容 hash 跳过未变化文件）；收集范围从"仅 .txt"扩展为 `.txt/.md`；结束时输出 chunk 总数、向量维度、耗时；
- `backend/scripts/diagnose_knowledge_runtime_consistency.py` 同步适配新存储（删除/重建语义改为清空 collection）；**运行前必须提示备份**，此为破坏性脚本，保持原有警示；
- 更新 `README.md` 与 `项目开发文档.md` 第 10 节中关于向量库的描述（JSON → ChromaDB、维度 384 → 实际值、重建命令行为）。

### 任务 6：测试适配与新增

- 现有 `tests/test_knowledge_category_filter.py` 等涉及 `chroma_store` 的测试：通过 fixture 注入临时持久化目录的 store 实例（或内存式测试替身），**不得依赖真实模型下载**——为测试提供 `FakeEmbeddingProvider`（确定性哈希向量，维度 32），工厂函数支持注入覆盖；
- 保证原有 82 个单测全部离线通过（`pytest tests/ -q`）；
- 新增测试：
  1. Provider 工厂按配置返回正确实例；
  2. VectorStore 增删查、upsert 幂等（同 id 重复入库不产生重复记录、内容更新生效）；
  3. `delete_by_file_id` / `get_by_file_name` 正确性；
  4. `_expand_same_source_chunks` 重构后行为回归（用 FakeEmbedding 构造同源数据）；
  5. where 过滤（knowledge_category）与 Chroma 条件兼容。

### 任务 7：真实索引构建与黄金问题验收（人工验证步骤，写入交付报告）

1. 备份并删除旧 `backend/vector_store/vectors.json`（或改名 `.bak`）；
2. 运行 `python rebuild_rag_index.py --force`，确认全量入库成功；
3. 启动后端，用以下黄金问题逐条验证（走 `/api/v1/chat` 或直接调 knowledge_search 工具），要求 top3 命中正确类别且答案引用正确来源：
   - "七天无理由退货的规则是什么"（refund/policy）
   - "退款多久到账"（refund）
   - "优惠券怎么领取、怎么使用"（coupon）
   - "MacBook Air 的内存支持扩展吗"（product）
   - "投诉了没人处理怎么办，会不会升级到主管"（complaint）
   - 一个无答案问题（如"怎么申请营业执照"）→ 验证"无依据直说"兜底不编造；
4. 根据 3 的实际分数分布回填 `RETRIEVAL_MIN_SCORE`（预期 0.3~0.45 区间），保证：正确问题有结果、无关问题被过滤；
5. 运行 `python backend/scripts/smoke_test.py --message "七天无理由退货的规则是什么"` 验证端到端。

## 五、注意事项与已知风险（务必阅读）

1. **Windows 依赖风险**：chromadb → onnxruntime DLL 问题已在本项目历史中出现过（见 `chroma_store.py` 原注释）。任务 0 的探针必须最先执行；回退 qdrant-client 时保持 `VectorStore` 对外接口不变，回退决策写入提交信息与 README。
2. **不要全局 import 模型**：`LocalBGEProvider` 必须懒加载。`app/rag/vectorstore/__init__.py` 导出 `chroma_store` 单例，模块导入发生在多个测试与 API 启动路径上——若在模块级加载 torch 模型，82 个单测会全部变慢或失败。单测环境下 Provider 由 fixture 替换，不得真实加载模型。
3. **API 响应兼容**：`knowledge_search` 的 ToolResult.data 字段、`RetrievalResult` 结构、metadata 键名均被前端 Trace（`AgentTimeline`、引用展示）与确认卡消费；字段增删需同步 `frontend/types/`，但本次目标是不增删。
4. **upsert 语义变化**：旧 `add_chunks` 按 chunk_id 去重（重复运行跳过），新实现 upsert（重复运行覆盖）。确认 `/api/rag/sync` 的 checksum 增量逻辑（`api/rag.py`）不受影响——它按文件级 checksum 跳过，与 chunk 级 upsert 不冲突。
5. **legacy RAG 分支**：`agents/agent.py` 中 `production_disable_legacy_rag = True` 硬开关及 `rag_pipeline.py` 保持现状不动（死代码不启用也不删除，另行技术债处理）。
6. **vectors.json 是派生数据**：不手编、改造后不读取；提交代码时确认它仍在 `.gitignore`（新增的 `vector_store/chroma/` 目录也要加入 `.gitignore`）。
7. **禁止越界改动**：不改 `agents/`、`flows/`（knowledge.py 除外——若 `_extract_user_request` 逻辑无需变更则连它也不改）、`database/`、`api/chat.py`、前端代码。
8. 每完成一个任务提交一次 git commit，commit message 注明任务编号；不要把依赖安装产物（`.venv/`、模型缓存）提交入库。

## 六、测试要求（完成前必须全部执行并留输出）

```powershell
cd backend
python -m pytest tests/ -q                 # 全部通过（含新增测试），离线
python rebuild_rag_index.py --force        # 真实索引构建成功，日志含 chunk 总数
python -m uvicorn app.main:app --port 8000 # 启动无报错，日志显示 Embedding provider 与向量库 count
# 黄金问题 6 条（任务 7.3）逐条截图/记录分数与来源
cd ../frontend && npm run build            # 前端构建通过（理论上不受影响，属回归确认）
```

## 七、完成标准（全部满足才算完成）

1. 知识入库链路为：Loader → RecursiveChunker（统一 500/100）→ 真实 Embedding（BGE 本地或配置的 API）→ ChromaDB 持久化，重启后端后向量数据仍在；
2. 检索链路为：查询理解（保留）→ 语义向量检索 → 类别过滤 → 同源扩展 → 规则重排 → 受约束 LLM 回答，全链路无 N-gram/JSON 残留代码；
3. `chroma_store` 对外 4 个方法签名与返回结构不变，唯一新增公共方法 `get_by_file_name`；
4. `pytest tests/ -q` 全绿（原 82 项 + 新增项），且不依赖网络与真实模型；
5. 黄金问题验收 6 条全部符合预期，`RETRIEVAL_MIN_SCORE` 已按实测校准并回填配置；
6. `.env.example`（根目录与 backend/）含全部新配置项及注释；README 与项目开发文档第 10 节已同步更新；
7. 交付报告包含：实际锁定的依赖版本、回退决策（如发生）、黄金问题实测分数表、索引构建统计。
