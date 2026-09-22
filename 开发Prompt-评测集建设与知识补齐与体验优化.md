# 开发 Prompt：RAG 评测集建设 + 知识补齐 + 检索体验优化（三项合并）

> 交付方式：将本文档整体交给一个新的开发对话一次性执行。
> 项目根目录：`E-commerce Customer Service Agent/`；后端 `backend/`。
> 前置状态：RAG 已落地（BGE 512 维 + qdrant 本地模式 + 父子块切分 + RRF 双路融合 + 二次补检），
> 后端单测基线 **115 passed**，检索黄金问题 6 条基线分数 0.64~0.75。
> 测试环境命令统一使用 `backend\.venv\Scripts\python.exe`。

---

## 一、三个优化目标（不可裁剪、不可合并执行顺序）

| # | 目标 | 解决的问题 |
| --- | --- | --- |
| G1 | **RAG 评测集与自动化回归**：黄金问题从 6 条扩到 25~30 条，覆盖全部知识类别，形成可重复执行的离线评测 | 当前没有度量，任何检索/知识改动都无法证明变好还是变坏 |
| G2 | **知识内容补齐**：依据 G1 的基线评测结果定位覆盖缺口，补写知识文件，提升回答覆盖率与准确性 | 准确率上限由知识源决定；检索机制已冻结，内容是最大杠杆 |
| G3 | **检索体验小修**：(a) BGE 模型启动预热，消除首次查询 11.9s 卡顿；(b) 前端 Debug Panel 展示多路检索分数与二次补检触发原因 | 首问体验差；检索决策黑盒，无法现场排障 |

**执行阶段顺序（强约束）**：G1 建基线 → G2 补知识并用 G1 验证收益 → G3 独立小改（可在 G2 重建索引等待期并行）→ 总验收。

## 二、适用范围

**允许修改/新增**：
- `backend/evaluation/`（新增 RAG 评测数据集与运行脚本，风格对齐现有 `dataset.py`/`run_eval.py`）
- `backend/knowledge_base/knowledge/`（按现有目录结构新增知识 TXT 文件）
- `backend/rebuild_rag_index.py`（只允许必要的参数复用，不改已验证的重建逻辑）
- `backend/app/main.py`（lifespan 预热）、`backend/app/core/config.py`（新增预热开关配置）
- `backend/tests/`（新增测试）
- `frontend/components/chat/` 的 Debug Panel 区域 + `frontend/types/`（仅新增可选字段）

**禁止触碰**：
- `agents/agent.py`、classifier、router、FSM、确认闸门、协调器（`coordinator.py`）——主链路一律不动
- `rag/vectorstore/chroma_store.py`、`rag/services/retrieval_service.py`、`tools/knowledge_search_tool.py`
  的**检索算法逻辑**（本次冻结检索机制，只允许为 Debug 展示读取已有 debug_info 字段）
- 现有 115 个测试的既有断言语义；前端非 Debug Panel 区域；`api/chat.py`

## 三、任务分解

### 阶段 G1：评测集与基线（先行，其他阶段依赖它的输出）

1. 新建 `backend/evaluation/rag_dataset.py`：**25~30 条**标注用例，构成要求：
   - 覆盖 `knowledge_base/knowledge/` 现有全部类别（refund/coupon/membership/logistics/complaint/product/policy/sop/faq/operation），每类至少 2 条；
   - 每类至少 1 条**口语变体**（"钱啥时候退回来"→refund、"券咋领"→coupon）；
   - **3 条无答案问题**（知识库确定不覆盖，如"怎么申请营业执照"），验证不编造兜底；
   - 每条字段：`question`、`expected_category`、`expected_source_hint`（期望命中的知识文件名关键词）、`expect_answer: bool`。
2. **防自证约束**：评测问题必须先独立撰写，再对照知识目录标注期望来源；**禁止从知识文件内容里反抄问题**（否则评测虚高、失去回归意义）。
3. 新建 `backend/evaluation/run_rag_eval.py`：
   - 直接调用 `knowledge_search` 工具链（真实索引，不 mock LLM 回答生成——只评测检索层）；
   - 指标：top1 命中率、top3 命中率、平均 top1 分数、无答案过滤率（3 条无答案必须 `success=False`）；
   - 参数：`--baseline`（输出基线报告 JSON）、`--fail-under <rate>`（低于阈值非零退出，供以后 CI 用）；
   - 输出逐条明细（命中文件/分数/是否触发二次补检）+ 汇总表。
4. 运行 `run_rag_eval.py --baseline` 产出**基线报告**，保存为 `backend/evaluation/rag_baseline_report.json`。
5. 新增离线单测：数据集结构合法性（字段完整、类别覆盖、无答案条目存在）；评测脚本对 mock 检索结果的指标计算正确性。

### 阶段 G2：知识补齐（依赖 G1 基线报告）

1. 分析基线报告：列出 top1 未命中 / 分数 < 0.5 / 类别无覆盖的问题清单。
2. 对照 `knowledge_base/knowledge/` 现有文件盘点缺口，按以下规范补写知识文件：
   - 目录 = 类别（与现有结构一致）；文件名遵循现有 `*_atomic.txt` 原子知识卡风格；
   - 内容结构对齐现有卡片（核心规则/适用范围/常见问题等小节），单文件聚焦单一主题；
   - 内容为合理自洽的平台演示规则（本项目知识库即演示性质），**不得编造与现有知识矛盾的规则**（如退款时效与既有文档冲突）；
   - 数量：按缺口补 **8~15 个**文件，优先补齐"口语变体命中失败"与"类别无覆盖"两类缺口。
3. 补齐后**一次性**重建索引：`python rebuild_rag_index.py --force`（禁止每补一个文件重建一次）。
4. 重跑评测：`run_rag_eval.py --fail-under <基线top1命中率>`，产出对比报告。
5. 新增测试：新知识文件格式校验（目录=类别、非空、无与现有文件重名冲突）。

### 阶段 G3：预热与 Debug 展示（小改，可与 G2 并行）

1. **BGE 启动预热**：
   - `config.py` 新增 `embedding_warmup: bool = True`；
   - `main.py` lifespan 中：当 provider 为 local 且开关开启时，后台任务执行一次
     `embedding_provider.embed_query("预热")`——必须 `try/except` 包裹，失败仅 warning 不阻塞启动；
   - **测试安全**：pytest 环境不得真实加载模型。在 `backend/pytest.ini` 或测试入口设置
     `EMBEDDING_WARMUP=false`（以实际配置读取方式为准），保证 115+ 测试运行时间增幅 < 10s；
2. **Debug Panel 检索透明化**（前端）：
   - `types/trace.ts` 新增可选字段：`retrieval_routes`（各路命中数与分数）、`rrf_score`、
     `revalidation`（是否触发/原因/重试查询）——均为可选，向后兼容；
   - Debug Panel（`FloatingAIAssistant.tsx` 的调试面板区域）在有数据时渲染这三个信息块，
     无数据时不渲染任何占位；不得改动非调试 UI。

## 四、执行约束（红线）

1. 检索算法、Agent 主链路、写操作闸门一律不动（见"适用范围"）；
2. 评测集先独立命题再标注，禁止从知识文件反抄问题；
3. 知识文件必须与现有目录/命名/格式规范一致，内容不得与既有知识冲突；
4. 重建索引全程只执行一次 `--force`；执行前确认无并发写入；
5. 测试环境禁止真实加载 BGE 模型（预热开关在测试中必须关闭）；
6. 每完成一个阶段 git commit 一次，message 注明阶段编号（G1/G2/G3）；
7. 模型缓存、`.venv`、索引目录、评测报告 JSON 不入库（确认 `.gitignore` 覆盖）。

## 五、输出结构（交付报告必须包含）

1. **改动清单**：按 G1/G2/G3 分组，新增/修改文件逐个列出；
2. **评测集清单**：30 条问题的完整表格（question / expected_category / expected_source_hint / expect_answer）；
3. **基线 vs 补知识对比表**：top1 命中率、top3 命中率、平均分、无答案过滤率，
   以及逐条"补知识前失败 → 补后命中"明细；
4. **新增知识文件清单**：文件名、所属类别、补齐依据（对应哪条基线失败问题）；
5. **预热验证**：预热开启时首次查询耗时（对比 11.9s 基线）、测试套件运行时间对比；
6. **前端验证**：Debug Panel 渲染截图或字段说明、`npm run build` 通过确认；
7. **遗留问题与建议**（如有）。

## 六、验证标准（全部满足才算完成）

1. `backend\.venv\Scripts\python.exe -m pytest tests/ -q` 全绿（115 + 新增），总运行时间增幅 < 10s；
2. 评测集 25~30 条可重复执行：**top3 命中率 ≥ 90%，top1 命中率 ≥ 80%，3 条无答案全部被过滤**；
   补知识后各项指标不低于基线（允许持平，不允许任何条目回退）；
3. `rebuild_rag_index.py --force` 重建成功，父子块统计正常输出，黄金问题原 6 条分数不低于 0.64~0.75 基线；
4. 预热开启时后端启动后**首次**知识查询响应中不含模型加载等待（实测首查耗时较 11.9s 显著下降）；
   预热关闭/失败时不影响服务启动；
5. `npm run build` 通过；Debug Panel 在含检索 trace 的消息上正确展示路由分数与补检信息，
   在无检索 trace 的消息（如闲聊）上不显示；
6. 交付报告结构完整（第五节逐项有内容），评测结果可由第三人对同一命令复现。
