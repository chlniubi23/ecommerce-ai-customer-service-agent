# 交付报告：知识库 RAG 真实落地改造

> 依据《开发Prompt-RAG真实落地改造.md》执行。日期：2026-09-19

## 一、交付范围与结果总览

| 项目 | 结果 |
| --- | --- |
| 入库链路 | Loader → RecursiveChunker（统一 500/100）→ 真实 Embedding（BGE 本地）→ qdrant 本地模式持久化，重启后数据仍在 ✅ |
| 检索链路 | 查询理解（保留）→ 语义向量检索 → 类别过滤 → 同源扩展 → 规则重排 → 阈值过滤 → 受约束 LLM 回答，无 N-gram/JSON 残留 ✅ |
| 对外契约 | `chroma_store` 4 个方法签名与返回结构不变；新增 `get_by_file_name`、`clear`（见"偏差说明"） ✅ |
| 单元测试 | `pytest tests/ -q`：**94 passed**（原 82 + 新增 12），完全离线（FakeEmbeddingProvider + 临时持久化目录） ✅ |
| 黄金问题验收 | 6/6 通过，`RETRIEVAL_MIN_SCORE=0.35` 校准通过 ✅ |
| 端到端冒烟 | `/health` + `/api/v1/chat`（黄金问题与无答案问题）全部 PASS ✅ |
| 文档同步 | README、项目开发文档（含第 10 节）、两份 `.env.example` 已更新 ✅ |

## 二、实际锁定的依赖版本（backend/requirements.txt）

```
sentence-transformers==6.1.0
torch==2.6.0            # CPU 版（Windows PyPI 默认即 CPU 构建）
qdrant-client==1.19.1   # 向量库（见回退决策）
```

配套环境：Python 3.12.4（`backend/.venv` 虚拟环境）；模型 `BAAI/bge-small-zh-v1.5`（512 维），下载使用 `HF_ENDPOINT=https://hf-mirror.com`。

### torch 版本决策（Windows）

`torch 2.14.0`（PyPI 当前默认）在本机导入即失败：`OSError: [WinError 1114] 动态链接库(DLL)初始化例程失败 (c10.dll)`，全新虚拟环境复现相同错误。降级 `torch==2.6.0+cpu` 后验证通过。requirements.txt 已注释说明。

## 三、回退决策（重要，方案授权的回退路径）

**首选 ChromaDB 不可用，回退 qdrant-client 本地模式。** 本机验证记录：

| 版本 | 现象 |
| --- | --- |
| chromadb 1.5.9 | `PersistentClient` 创建/查询可用，但 `collection.upsert()` 触发 `Windows fatal exception: access violation`（Rust 绑定 `chromadb/api/rust.py::_upsert`），进程静默崩溃 |
| chromadb 1.0.15 | 启动即 `pyo3_runtime.PanicException: range start index 10 out of range for slice of length 9` |
| chromadb 0.5.23 | 依赖 chroma-hnswlib，Python 3.12 无预编译轮子，源码编译需要本机不存在的 C++ 构建工具 |

按方案第四节"回退方案"改用 `qdrant-client` 本地模式（纯 Python），**`VectorStore` 对外接口、返回结构、metadata 键名全部保持不变**。实现要点：

- 文件名保留 `chroma_store.py`、单例名 `chroma_store`、类名 `VectorStore`，最小化 import 改动；
- qdrant 点 ID 只接受 uint/UUID：chunk_id 经 `uuid5` 确定性映射，保证 upsert 幂等；
- 真实 chunk_id 与 content 存 payload；`relevance_score = max(0, 1 - distance)` 语义与原实现一致；
- `where` 参数沿用 "key=value 精确匹配" 语义，映射为 qdrant Filter；
- 配置键命名为 `QDRANT_PERSIST_DIR` / `QDRANT_COLLECTION`（默认 `vector_store/qdrant`）。

## 四、偏差说明（方案之外的必要新增）

1. **`VectorStore.clear()` 公共方法**：方案完成标准写"唯一新增 get_by_file_name"，但 `rebuild_rag_index.py --force` 与诊断脚本的"清空 collection"需要一个不破坏存储目录的清空入口（chroma 1.x 崩溃路径已验证），故新增 `clear()`。纯新增，不影响任何现有消费方。
2. **`pytest.ini`（`--basetemp=.pytest_tmp`）**：本机 `C:\Users\17383\AppData\Local\Temp\pytest-of-17383` 目录 ACL 损坏（WinError 5 拒绝访问且无法删除），导致 pytest 默认 tmp_path fixture 全部失败。将 pytest 临时目录固定到工作区内，`pytest tests/ -q` 可直接运行。
3. **`min_score` 透传**：`KnowledgeWorkflow.run` / `KnowledgeSearchRequest` 的 `min_score` 默认值由 `0.01` 改为 `None`（未显式指定时由工具读取 `RETRIEVAL_MIN_SCORE` 配置），否则配置阈值永远不会生效。显式传值的调用方（legacy rag、诊断脚本）行为不变。

## 五、索引构建统计（任务 7.2）

```
命令: python rebuild_rag_index.py --force
收集范围: backend/knowledge_base/knowledge/（.txt + .md）
结果: 70 个文件全部入库 | 157 chunks | 向量维度 512 | 耗时 24.7s
增量验证: 再次运行（不带 --force）70/70 全部 SKIP（按 source_path + source_hash）
旧数据: vectors.json 已备份为 vector_store/vectors.json.bak，新实现不再读取
```

持久化目录 `backend/vector_store/qdrant/` 在 `.gitignore` 中（`backend/vector_store/` 整体忽略），重启后端向量数据仍在（qdrant 本地模式落盘）。

## 六、黄金问题实测分数表（任务 7.3/7.4）

检索入口：真实 `knowledge_search` 工具（规则查询理解、不调 LLM），top3：

| # | 黄金问题 | 期望 | 实测 top1 | 分数 | top3 分数区间 | 类别 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 七天无理由退货的规则是什么 | refund/policy | seven_day_return_atomic.txt | 0.750 | 0.512~0.750 | refund | ✅ |
| 2 | 退款多久到账 | refund | refund_timeline_atomic.txt | 0.732 | 0.665~0.732 | refund | ✅ |
| 3 | 优惠券怎么领取、怎么使用 | coupon | coupon_receive_atomic.txt | 0.744 | 0.676~0.744 | coupon | ✅ |
| 4 | MacBook Air 的内存支持扩展吗 | product | macbook_air_m4_specs_atomic.txt | 0.641 | 0.576~0.641 | product | ✅ |
| 5 | 投诉了没人处理怎么办，会不会升级到主管 | complaint | complaint_escalation_atomic.txt | 0.671 | 0.617~0.671 | complaint | ✅ |
| 6 | 怎么申请营业执照 | 无答案 | 无结果（success=False，兜底不编造） | — | — | — | ✅ |

**`RETRIEVAL_MIN_SCORE` 校准**：正确问题 top3 分数全部 ≥ 0.512，无关问题无结果。当前值 `0.35`（默认）满足"正确问题有结果、无关问题被过滤"，落在方案预期 0.3~0.45 区间，无需调整。

原始数据见 `backend/golden_question_report.json`（gitignore，本地留存）；验收脚本：`backend/scripts/golden_question_validation.py`。

## 七、端到端验证（任务 7.5）

```
启动: .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
启动日志: [EMBEDDING] provider 初始化: LocalBGEProvider(model='BAAI/bge-small-zh-v1.5')
          模型懒加载 11.9s（首次查询时）
smoke: python scripts/smoke_test.py --message "七天无理由退货的规则是什么"
  [PASS] health: healthy
  [PASS] chat: "七天无理由退货是签收次日起7天内可以申请……不能影响二次销售……"（正确引用知识）
smoke: python scripts/smoke_test.py --message "怎么申请营业执照"
  [PASS] chat: 不编造平台规则，引导用户（兜底行为正确）
```

## 八、改动清单

**新增**
- `backend/app/rag/vectorstore/embedding_provider.py`：Embedding Provider 抽象层（LocalBGE 懒加载 / OpenAI 兼容 API / 工厂 + 测试注入）
- `backend/tests/test_rag_vectorstore.py`：12 个离线测试（FakeEmbeddingProvider 32 维）
- `backend/scripts/golden_question_validation.py`：黄金问题验收脚本
- `backend/pytest.ini`

**重写/修改**
- `backend/app/rag/vectorstore/chroma_store.py`：VectorStore 底座（接口不变）
- `backend/app/tools/knowledge_search_tool.py`：同源扩展改用 `get_by_file_name`；向量检索只用消解后自然语言 query，词表仅作重排加分；min_score 读配置
- `backend/app/rag/services/retrieval_service.py`：`MIN_RELEVANCE_SCORE` 读 `RETRIEVAL_MIN_SCORE`
- `backend/app/rag/constants/config.py` + `knowledge_pipeline.py`：切片配置统一读 Settings（500/100）
- `backend/app/core/config.py`：新增 Embedding/向量库/切片/检索配置
- `backend/rebuild_rag_index.py`：`--force` 全量 + 增量（source+hash）+ TXT/MD + 统计输出
- `backend/scripts/diagnose_knowledge_runtime_consistency.py`：适配新存储（清空 collection 语义 + 备份警示）
- `backend/app/knowledge_agent/{models,services}.py`：min_score None 透传
- `backend/app/architecture/production.py`：向量库描述更新
- `README.md`、`项目开发文档.md`（第 10 节及关联描述）、`.env.example`（根目录 + backend/）、`.gitignore`

**未触碰（按方案边界）**：`agents/agent.py` 主链路、分类器、路由、FSM、确认闸门、`flows/`、`database/`、`api/chat.py`、前端代码、legacy `rag_pipeline.py`。

## 九、运行环境备注

- 后端依赖安装在 `backend/.venv`（不入库）；运行命令统一用 `.venv\Scripts\python.exe`
- 首次构建索引/启动需要本地 Embedding 模型（约 100MB），建议设置 `HF_ENDPOINT=https://hf-mirror.com`
- 切换 OpenAI 兼容 Embedding：`.env` 中设 `EMBEDDING_PROVIDER=openai` + `EMBEDDING_API_KEY` + `EMBEDDING_BASE_URL`，并重新执行 `rebuild_rag_index.py --force`（两套 provider 不可混用）
