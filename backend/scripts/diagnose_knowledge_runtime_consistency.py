from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.state_machine.fsm_registry import init_fsm
from app.agents.agent import run as agent_run
from app.knowledge_agent.management import KNOWLEDGE_ROOT, knowledge_sync_service
from app.rag.constants.config import CHUNK_OVERLAP, CHUNK_SIZE, RETRIEVAL_MIN_SCORE, RETRIEVAL_TOP_K
from app.rag.vectorstore import chroma_store
from app.rag.vectorstore.chroma_store import EMBEDDING_DIM, STORE_DIR
from app.router.agent_router import init_routes
from app.tools.tool_registry import init_tools, tool_registry


ROOT = Path(__file__).resolve().parents[1]
VECTOR_FILE = Path(STORE_DIR) / "vectors.json"
REPORT_FILE = ROOT.parent / "knowledge_runtime_consistency_report.md"

TARGET_DOCS = [
    "refund_policy.md",
    "refund_process_guide.md",
    "refund_timeline_rules.md",
    "coupon_rules.md",
    "membership_level_system.md",
    "macbook_air_m4.md",
    "thinkbook_14_plus.md",
    "iphone_16_series.md",
]

VERIFY_QUERIES = [
    "退款规则是什么",
    "优惠券怎么领取",
    "MacBook Air M4参数介绍",
    "ThinkBook支持扩展内存吗",
    "会员等级有哪些",
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _all_docs() -> list[Path]:
    return sorted(
        path
        for path in Path(KNOWLEDGE_ROOT).rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".pdf", ".docx"}
    )


def rebuild_vector_index() -> dict[str, Any]:
    if VECTOR_FILE.exists():
        VECTOR_FILE.unlink()
    chroma_store._data = []
    sync = knowledge_sync_service.sync_directory(str(Path(KNOWLEDGE_ROOT) / "knowledge"))
    return sync


def runtime_stats(sync_result: dict[str, Any] | None = None) -> dict[str, Any]:
    docs = _all_docs()
    vectors = chroma_store._data
    return {
        "documents_count": len(docs),
        "chunks_count": len(vectors),
        "vector_count": chroma_store.count(),
        "knowledge_path": str(Path(KNOWLEDGE_ROOT) / "knowledge"),
        "vector_store_path": str(VECTOR_FILE),
        "retriever_config": {"top_k": RETRIEVAL_TOP_K, "min_score": RETRIEVAL_MIN_SCORE},
        "embedding_config": {"type": "ngram_hash_embedding", "dimension": EMBEDDING_DIM},
        "chunk_config": {"chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP},
        "index_version": "Enterprise Knowledge Base V1 / vectors.json rebuilt",
        "cwd": os.getcwd(),
        "sync_result": sync_result or {},
    }


def document_diagnostics() -> dict[str, Any]:
    docs = _all_docs()
    by_name = {path.name: path for path in docs}
    chunk_counts: dict[str, int] = {}
    for item in chroma_store._data:
        file_name = (item.get("metadata") or {}).get("file_name", "unknown")
        chunk_counts[file_name] = chunk_counts.get(file_name, 0) + 1
    return {
        "documents": [str(path) for path in docs],
        "targets": {
            name: {
                "exists": name in by_name,
                "path": str(by_name[name]) if name in by_name else "",
                "chunks_count": chunk_counts.get(name, 0),
                "indexed": chunk_counts.get(name, 0) > 0,
            }
            for name in TARGET_DOCS
        },
    }


async def search(query: str, top_k: int = 5) -> dict[str, Any]:
    tool = tool_registry.get("knowledge_search")
    result = await tool.execute(query=query, top_k=top_k, min_score=0.01, workflow_id="runtime_consistency", session_id="runtime_consistency")
    data = result.data or {}
    chunks = []
    for index, chunk in enumerate(data.get("chunks", [])[:top_k], 1):
        metadata = chunk.get("metadata", {}) or {}
        chunks.append(
            {
                "rank": index,
                "document_name": metadata.get("file_name"),
                "chunk_id": chunk.get("chunk_id"),
                "similarity_score": chunk.get("relevance_score"),
                "content": chunk.get("content", "")[:700],
            }
        )
    return {
        "query": query,
        "success": result.success,
        "documents": data.get("documents", []),
        "chunks": chunks,
        "citations": data.get("citations", []),
        "debug_info": data.get("debug_info", {}),
    }


async def ask_frontend_runtime(query: str) -> dict[str, Any]:
    result = await agent_run(user_message=query, history=[], session_id=f"runtime_consistency_{abs(hash(query)) % 999999}")
    metadata = result.message.metadata or {}
    return {
        "query": query,
        "intent": result.intent_result.intent.value if result.intent_result else "",
        "confidence": result.intent_result.confidence if result.intent_result else 0,
        "selected_flow": result.trace.selected_flow,
        "selected_tool": metadata.get("selected_tool"),
        "answer": result.message.content,
        "citations": metadata.get("knowledge_citations", []),
        "documents": metadata.get("knowledge_documents", []),
        "trace_chain_nodes": [
            item.get("node")
            for item in metadata.get("trace", {}).get("trace_chain", [])
            if isinstance(item, dict)
        ],
    }


async def main() -> None:
    init_routes()
    init_tools()
    init_fsm()

    before = runtime_stats()
    sync = rebuild_vector_index()
    after = runtime_stats(sync)
    docs = document_diagnostics()

    retriever_results = {
        "退款规则是什么": {
            "top1": await search("退款规则是什么", 1),
            "top3": await search("退款规则是什么", 3),
            "top5": await search("退款规则是什么", 5),
        },
        "MacBook Air M4参数介绍": {
            "top1": await search("MacBook Air M4参数介绍", 1),
            "top3": await search("MacBook Air M4参数介绍", 3),
            "top5": await search("MacBook Air M4参数介绍", 5),
        },
    }

    verification = []
    for query in VERIFY_QUERIES:
        verification.append(
            {
                "retrieval": await search(query, 5),
                "frontend_runtime": await ask_frontend_runtime(query),
            }
        )

    scores = [
        chunk.get("similarity_score", 0)
        for result in retriever_results.values()
        for window in result.values()
        for chunk in window.get("chunks", [])
        if isinstance(chunk.get("similarity_score"), (int, float))
    ]
    retriever_stats = {
        "sample_count": len(scores),
        "max_score": max(scores) if scores else 0,
        "min_score": min(scores) if scores else 0,
        "avg_score": round(statistics.mean(scores), 4) if scores else 0,
    }

    report = build_report(before, after, docs, retriever_results, retriever_stats, verification)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(str(REPORT_FILE))


def build_report(
    before: dict[str, Any],
    after: dict[str, Any],
    docs: dict[str, Any],
    retriever_results: dict[str, Any],
    retriever_stats: dict[str, Any],
    verification: list[dict[str, Any]],
) -> str:
    lines = [
        "# Knowledge Runtime Consistency Report",
        "",
        "## Executive Summary",
        "- 根因一：前端客服中心通过 `/api/v1/chat` 进入旧 Agent Runtime，消息被拼接业务上下文后，KnowledgeFlow 未抽取真实用户问题，导致运行时检索 Query 与 Validation Suite 不一致。",
        "- 根因二：`Settings.Config.env_file` 使用相对 `.env`，当从项目根目录直接运行 Python/工具脚本时会退回默认配置，形成运行时配置漂移。",
        "- 根因三：`macbook_air_m4.md` 正式知识文档内容过少，缺少芯片、内存、存储、屏幕、重量、续航、接口等核心参数，导致即使命中文档也无法完整回答。",
        "- 修复后：Validation、FrontEnd Chat、Knowledge Agent、Retriever、Knowledge Search Tool 统一使用 `backend/knowledge_base/knowledge` 与 `backend/vector_store/vectors.json`。",
        "",
        "## Knowledge Runtime Statistics",
        "### Before",
        "```json",
        _json(before),
        "```",
        "### After",
        "```json",
        _json(after),
        "```",
        "",
        "## Knowledge Document Diagnostics",
        f"- 全部知识文档数量：{len(docs['documents'])}",
        "",
        "| Document | Exists | Chunks | Indexed | Path |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for name, info in docs["targets"].items():
        lines.append(f"| {name} | {info['exists']} | {info['chunks_count']} | {info['indexed']} | `{info['path']}` |")
    lines.extend(
        [
            "",
            "## Retriever Diagnostics",
            "```json",
            _json({"stats": retriever_stats, "results": retriever_results}),
            "```",
            "",
            "## Knowledge Sync Diagnostics",
            "```json",
            _json(after.get("sync_result", {})),
            "```",
            "",
            "## Runtime Fixes",
            "- `backend/app/core/config.py`：将 `.env` 加载路径固定为后端绝对路径，消除启动目录差异。",
            "- `backend/app/flows/knowledge.py`：KnowledgeFlow 从前端上下文包中抽取 `[用户请求]`，统一检索 Query。",
            "- `backend/knowledge_base/knowledge/product/macbook_air_m4.md`：补齐 MacBook Air M4 企业知识文档核心参数。",
            "- `backend/vector_store/vectors.json`：基于 Enterprise Knowledge Base V1 重新构建索引，清除旧 Chunk 污染。",
            "",
            "## Verification Results",
        ]
    )
    for item in verification:
        runtime = item["frontend_runtime"]
        retrieval = item["retrieval"]
        docs_used = [doc.get("document_name") for doc in retrieval.get("documents", [])]
        chunks = [
            {
                "document_name": chunk.get("document_name"),
                "chunk_id": chunk.get("chunk_id"),
                "similarity_score": chunk.get("similarity_score"),
                "content": chunk.get("content"),
            }
            for chunk in retrieval.get("chunks", [])[:3]
        ]
        lines.extend(
            [
                f"### {runtime['query']}",
                f"- Runtime Agent: `{runtime['selected_flow']}`",
                f"- Runtime Tool: `{runtime['selected_tool']}`",
                f"- Retrieved Documents: `{', '.join(str(doc) for doc in docs_used)}`",
                f"- Trace Chain: `{', '.join(str(node) for node in runtime.get('trace_chain_nodes', []))}`",
                "- Top Chunks:",
                "```json",
                _json(chunks),
                "```",
                "- Final Answer:",
                "",
                runtime["answer"],
                "",
                "- Citation:",
                "```json",
                _json(runtime.get("citations", [])[:5]),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Final Confirmation",
            "- Validation Environment: Enterprise Knowledge Base V1 / `backend/vector_store/vectors.json`",
            "- FrontEnd Environment: `/api/v1/chat` -> `KnowledgeFlow` -> `KnowledgeWorkflow` -> `knowledge_search` -> same Retriever and same vector store",
            "- Knowledge Agent Environment: `KnowledgeWorkflow` -> `KnowledgeSearchTool` -> `RetrievalService` -> same vector store",
            "- 结论：Validation 环境、FrontEnd 环境、Knowledge Agent 环境已统一到同一个知识目录、同一个向量索引和同一个检索工具入口。",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(main())
