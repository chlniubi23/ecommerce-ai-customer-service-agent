# 开发 Prompt：多来源信息整合与检索增强（回答准确性与完整性优化）

> 交付方式：将本文档整体交给一个新的开发对话执行。
> 执行前先读"二、根因诊断"（已代码实证），再按"四、任务分解"顺序开发。
> 项目根目录：`E-commerce Customer Service Agent/`；后端 `backend/`。
> 前置状态：RAG 已落地（BGE 512 维 + qdrant 本地模式 + 检索链路），本次在其上增强。

---

## 一、目标

解决"信息在某个来源里存在、但助手只依赖单一来源而答不出来"的问题。典型案例（已复现）：
用户在订单详情页问"帮我看看这个订单现在什么状态"，订单详情页有完整物流（顺丰
SFDEMO2026061601 / 广州转运中心 / 完整轨迹），助手却回答"物流单号这边暂时没同步出来"。

改造目标：
1. **业务事实类回答**（订单/物流/退款/投诉/人工）：多来源编排——工具实时查询、关联工具补全、
   前端页面上下文三级来源互为备份，缺失自动补全，不因单来源缺失而答"系统没有"；
2. **知识问答类回答**（RAG）：优化切分粒度与检索策略，多路检索 + 结果校验 + 二次补检，
   单次检索不达标不直接放弃；
3. **回复生成层**：统一"信息整合守则"，禁止把"单一来源缺失"表述为"系统没有数据"；
4. 覆盖助手全部回答场景（订单、物流、退款、投诉、商品、优惠券、知识问答、多域协调、闲聊兜底）。

## 二、根因诊断（已代码实证，开发时直接对照修复）

| # | 缺陷 | 位置 | 证据 |
| --- | --- | --- | --- |
| D1 | 协调器组装 LLM 输入用 `visible_input`（剥离系统上下文后），前端注入的物流/退款/投诉事实全部丢失 | `agents/coordinator.py:302` | `user_message = f"用户原始请求：{visible_input}..."` |
| D2 | 协调器域执行是裸单工具，无 enrich；`DOMAIN_DEPENDENCIES` 只用于排序，无数据传递 | `coordinator.py:331-339`、`180-181` | `_execute_domain_tool` 单工具执行；对比 `agents/enhanced_flow.py:29-34` 的 `TOOL_ENRICHMENT_MAP` 仅在 `enhanced_tool_execute` 生效 |
| D3 | enrich 结果失败时静默跳过，LLM 不知道失败、也不知道有替代来源 | `enhanced_flow.py:74-77` | `if enrich_result.success:` 才 append |
| D4 | enrich 触发条件依赖 `params.get("order_id")`，无"结果完整性"判断——主工具成功但结果缺关键字段时不补 | `enhanced_flow.py:67-69` | 仅判断主工具 success + order_id 非空 |
| D5 | 回复提示词（ANALYSIS_PROMPT / SYNTHESIZE_PROMPT）无多来源整合与缺失声明规范 | `enhanced_flow.py:114-123`、`coordinator.py:84-92` | 无任何交叉核对/补全指令 |
| D6 | RAG 单轮检索失败即放弃：top 分数低于阈值时直接返回无结果（仅在类别过滤后有降级半阈值重查，无改写重检） | `tools/knowledge_search_tool.py`、`rag/services/retrieval_service.py` | 检索窗口 top_k*8，无第二路检索 |
| D7 | 切分粒度单一（500 字符块既做检索单元又做返回单元），长规则被切断时返回的上下文不完整 | `rag/chunkers/recursive_chunker.py`、`pipelines/knowledge_pipeline.py` | 无父子块结构 |

## 三、方案总览（三层）

```
层A 业务事实层：多来源编排补全（修 D1-D5，覆盖订单/物流/退款/投诉/商品/多域协调）
层B RAG检索层：切分粒度 + 多路检索 + 结果校验与二次补检（修 D6-D7，覆盖知识问答）
层C 回复生成层：统一信息整合守则（覆盖所有场景的最终表述）
```

信息来源优先级约定（层 A 核心原则）：
`工具实时查询 > 前端注入快照（[系统补充上下文] 中的结构化事实）> 明确告知缺失并给替代方案`

## 四、任务分解（按顺序执行）

### 任务 A1：协调器多来源修复（修 D1、D2）— 优先级最高

文件：`backend/app/agents/coordinator.py`

1. **保留前端事实上下文**：`coordinate()` 组装 LLM 输入（现第 302 行）改为同时携带
   完整系统上下文中的结构化事实。具体：在 `user_message` 中新增一段
   `[页面实时快照（前端注入，可信）]`，内容取自完整 `user_input` 中
   `[系统补充上下文` 标记之后的"当前订单/物流/退款/投诉/商品"各结构化行
   （保留 `buildContextPrompt` 的既有行格式，不要重新发明解析——按行截取
   `当前订单：`、`物流：`、`物流轨迹：`、`退款：`、`当前投诉：` 前缀的行即可）。
   注意：`detect_multi_intent` / 闸门判断仍必须用 `visible_input`（防误触发写操作），
   本条只改 **LLM 综合输入** 的组装，不得改动任何意图判定路径。
2. **域执行接入增强编排**：`_execute_domain_tool` 对 `order`/`logistics` 域改用
   `enhanced_flow.py::enhanced_tool_execute`（带 enrich），退款/投诉域的特殊分支保持不动
   （闸门语义不许变）。协调器最终 `all_tool_calls` 需合并 enrich 产生的多次工具调用。

### 任务 A2：完整性契约与自动补全（修 D3、D4）

文件：`backend/app/agents/enhanced_flow.py`

1. 新增 `TOOL_RESULT_CONTRACTS`：定义主工具"回答完整性所需字段"，例如：
   - `query_order` → 期望结果含物流信息（`logistics` 或 shipment 相关键）；
   - `logistics_query` → 期望结果含订单状态（或由 enrich 补充）；
   - `refund_apply` → 期望含订单状态与物流摘要。
2. `enhanced_tool_execute` 逻辑升级：
   - enrich 触发条件从 `params.get("order_id")` 非空升级为
     **"order_id 非空 或 主工具结果不满足契约"**；
   - 主工具成功但缺契约字段 → 执行关联工具补全；
   - **enrich/关联工具失败不再静默**：向 context_parts 追加
     `[补全失败提示] logistics_query 查询失败({error})；若页面上下文/历史记录中有物流信息请据此回答，并如实告知用户当前查询不到`；
3. 所有上下文片段标注来源标签（`[实时查询]` / `[补全查询]`），供层 C 使用。

### 任务 A3：前端快照作为兜底来源

文件：`backend/app/agents/enhanced_flow.py`（或新建 `agents/context_facts.py`）

1. 新增纯函数 `extract_context_facts(full_message: str) -> dict`：从完整消息的
   `[系统补充上下文` 段解析结构化事实行（物流单号/承运商/当前位置/轨迹、退款状态、
   投诉状态、订单状态），返回 dict；解析不到返回空 dict，**任何异常不得中断主流程**。
2. 在 `enhanced_tool_execute` 与 `coordinate()` 的最终上下文中：当某类事实
   （如物流）实时查询缺失/失败而前端快照中存在时，追加
   `[页面快照补充] 物流：顺丰速运 / SFDEMOxxx / 运输中 / 广州转运中心（来源：用户当前页面）`。
   这是"物流单号未同步但详情页可见"场景的直接兜底。

### 任务 A4：统一信息整合守则（层 C，修 D5）

文件：`enhanced_flow.py::ANALYSIS_PROMPT`、`coordinator.py::SYNTHESIZE_PROMPT`

两处提示词统一追加"信息整合守则"段（措辞可微调，语义不得删减）：
```
信息整合守则：
- 交叉核对所有来源（实时查询、补全查询、页面快照）后再回答；同一事实以实时查询为准，快照为辅。
- 某个信息在单一来源缺失时，先检查其他来源；都缺失才如实说"当前查询不到"，并给出替代方案。
- 严禁把"单一来源没有"说成"系统没有/未同步"；严禁编造单号、金额、日期。
```

### 任务 B1：父子块切分（parent-child chunking，修 D7）

文件：`rag/chunks` 相关（`chunkers/recursive_chunker.py`、`pipelines/knowledge_pipeline.py`、
`vectorstore/chroma_store.py`、`rebuild_rag_index.py`）

1. 切分策略：父块 = 自然段落级（800 字符 / 150 重叠，承载完整上下文，用于**返回**）；
   子块 = 250 字符 / 50 重叠（**用于检索**，小粒度提高命中率）。
2. 实现要求：
   - `RecursiveChunker` 增加 parent 模式或新增 `ParentChildChunker`：每个子块 metadata 记录
     `parent_id`，父块全量入库（`chunk_type: parent|child`）；
   - 向量库对子块建向量索引；父块可选不入向量（仅 payload 存档）或同库不同字段标记；
   - `add_chunks` / `query` / `get_by_file_name` 契约不变，检索结果组装时按
     `parent_id` 回取父块内容（新增 `get_by_ids(ids)` 公共方法，同源扩展逻辑复用）；
   - `rebuild_rag_index.py --force` 全量重建后，日志输出父/子块数量。
3. 兼容：`knowledge_search` 工具输出结构（documents/chunks/citations）不变；
   chunks 列表中每个元素新增 `parent_content` 字段（返回给 LLM 的最终上下文用父块，
   分数与引用仍用命中子块）。前端类型不强制变更（新增字段向后兼容）。

### 任务 B2：多路检索与融合（修 D6 前半）

文件：`backend/app/tools/knowledge_search_tool.py`、`rag/services/retrieval_service.py`

1. 双路检索：路 1 = 现有语义向量检索（BGE embed_query）；路 2 = 轻量关键词检索
   （对 query 分词/取 2-gram，在向量库 payload 上做包含匹配；数据量 10^2 量级，无需引入 BM25 依赖）；
2. 融合：两路结果用 RRF（Reciprocal Rank Fusion，k=60）合并排序，替代单一分数序；
3. 多查询合并：原问题 + 查询理解 `expanded_query` **分别**检索后合并去重
   （现实现只检索 expanded_query 一次；改为两查询各检索一路，按 chunk_id 去重取最高 rank）；
4. 每路检索的分数仍写入 debug_info，供 Trace 展示。

### 任务 B3：结果校验与二次补检（修 D6 后半）

文件：`tools/knowledge_search_tool.py`

在融合排序后、返回前增加两道校验，任一不通过触发一次补检（最多一次，防延迟恶化）：
1. **相关性校验**：融合后 top1 的向量分 < `RETRIEVAL_MIN_SCORE` → 用查询理解的
   `expanded_query`（改写/扩展词）重检一次，取两次最优；
2. **覆盖度校验**：提取问题中的关键实体（商品型号/数字/规则名词，复用
   `query_understanding` 的 product_target 与 `_query_tokens`），
   若 top-5 中无任何块包含任一实体 → 用"实体 + 类别词"组成的窄查询重检一次；
3. 补检仍无结果才走现有无结果分支（success=False，兜底不编造语义不变）。
校验触发与补检结果写入 `debug_info.revalidation`。

### 任务 B4：检索结果组装的来源标注

文件：`knowledge_agent/context.py`（`knowledge_context_builder.build`）

最终 `final_context` 中每个片段前标注来源与粒度：
`[来源: refund/seven_day_return_atomic.txt | 命中: 子块#12 | 父块完整内容]`，
让 LLM 能区分"命中片段"与"完整上下文"，引用时指向正确文档。

## 五、注意事项与红线

1. **写操作安全红线不许动**：协调器中 refund/complaint 的闸门分支、确认词判定、
   `visible_input` 在**意图判定**中的使用一律不改；A1 只改 LLM 综合输入的组装。
2. **PII 边界**：`extract_context_facts` 解析的事实仅进入本轮 LLM 上下文，
   不得新增日志打印或持久化；Trace 中工具参数摘要沿用现有脱敏口径。
3. **性能预算**：补检最多 1 次、enrich 链路最多 2 个额外工具；整轮 P50 增幅 ≤ 800ms
   （qdrant 本地检索 <10ms/次，主要开销在 LLM）。
4. **契约稳定**：`chroma_store` 4 方法 + `get_by_file_name` 签名不变（可新增
   `get_by_ids`）；`knowledge_search` ToolResult.data 既有字段不删不改，只增；
   `RetrievalResult` 结构只增不改。
5. **测试离线**：所有新测试用 FakeEmbeddingProvider + 临时持久化目录，
   不依赖真实模型与网络；`pytest tests/ -q` 全绿（当前基线 94 passed）。
6. **RAG 索引变更需重建**：B1 改变切分结构，完成后必须 `rebuild_rag_index.py --force`
   重建，并重跑 6 条黄金问题（七天无理由/退款到账/优惠券/MacBook/投诉升级/无答案），
   分数不得低于改造前基线（0.64/0.73/0.74/0.64/0.67/无结果）。
7. **不动**：`agents/agent.py` 主链路、classifier、FSM、确认闸门、`api/chat.py`、前端代码；
   现有 94 个测试除因契约**新增字段**需要补断言外，不改既有断言语义。

## 六、测试要求

新增测试（全部离线）：
1. **截图场景回归（必测）**：构造含 `[系统补充上下文]`（含物流：顺丰/SFDEMOxxx/运输中）
   的消息 + mock `query_order` 成功、`logistics_query` 失败 → 断言最终 LLM 输入上下文
   包含 `[页面快照补充]` 物流事实，且整合守则在 system prompt 中；
2. 协调器双域（订单+物流）→ `all_tool_calls` 同时含 `query_order` 与 `logistics_query`，
   且 order 域结果触发了 enrich；
3. enrich 失败路径 → context 含 `[补全失败提示]` 而非静默；
4. 完整性契约：`query_order` 成功但结果无物流键 → 自动触发 `logistics_query`；
5. 父子块：入库后子块命中、返回含 `parent_content` 且父块完整；
6. 多路融合：构造语义路低分、关键词路命中的用例，断言 RRF 合并后命中；
7. 二次补检：首路 top1 低于阈值 → 触发 expanded_query 重检并取最优；
   覆盖度校验同理；两次都失败 → 保持无结果语义；
8. 既有黄金问题回归（真实索引，人工/脚本执行）：6 条全过且分数不低于基线。

## 七、完成标准

1. 复现场景修复：在订单详情页（有物流数据）问"帮我看看这个订单现在什么状态"，
   回复包含物流单号/当前位置，不再出现"物流单号没同步"；
2. 协调器多域请求每个域都有完整结果，退款/投诉闸门语义与改造前完全一致
   （现有 `test_coordinator_safety` 等测试不改语义全过）；
3. 知识问答：混合问法（口语/同义/仅含实体关键词）均可命中；单路失败有补检；
   `RETRIEVAL_MIN_SCORE` 基线不回退；
4. `pytest tests/ -q` 全绿（94 + 新增）；`npm run build` 不受影响（前端无改动即通过）；
5. Trace 中可看到来源标签（实时查询/补全查询/页面快照）与 `debug_info.revalidation`；
6. 交付报告：改动清单、截图场景前后对比（trace 摘录）、黄金问题分数对比表、
   性能耗时对比（P50）。
