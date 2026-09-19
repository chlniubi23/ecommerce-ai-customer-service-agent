"""黄金问题验收脚本（任务 7.3 / 7.4）

对真实索引逐条运行黄金问题，记录 top3 的分数与来源，用于：
- 校准 RETRIEVAL_MIN_SCORE（预期 0.3~0.45 区间）
- 生成交付报告中的"黄金问题实测分数表"

用法（在 backend/ 下，走离线规则查询理解，不调用 LLM）：
    .\\.venv\\Scripts\\python.exe scripts\\golden_question_validation.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.tools.tool_registry import init_tools, tool_registry

GOLDEN_QUESTIONS = [
    # (问题, 期望命中的类别 / 说明)
    ("七天无理由退货的规则是什么", "refund/policy"),
    ("退款多久到账", "refund"),
    ("优惠券怎么领取、怎么使用", "coupon"),
    ("MacBook Air 的内存支持扩展吗", "product"),
    ("投诉了没人处理怎么办，会不会升级到主管", "complaint"),
    ("怎么申请营业执照", "无答案：应无相关结果/兜底不编造"),
]


async def run_question(query: str, top_k: int = 3) -> dict:
    tool = tool_registry.get("knowledge_search")
    started = time.perf_counter()
    result = await tool.execute(
        query=query,
        top_k=top_k,
        workflow_id="golden_validation",
        session_id="golden_validation",
        allow_llm=False,  # 校准检索层本身，不依赖 LLM
    )
    duration_ms = (time.perf_counter() - started) * 1000
    data = result.data or {}
    chunks = []
    for rank, chunk in enumerate(data.get("chunks", [])[:top_k], 1):
        metadata = chunk.get("metadata", {}) or {}
        chunks.append({
            "rank": rank,
            "file_name": metadata.get("file_name", ""),
            "knowledge_category": metadata.get("knowledge_category", ""),
            "relevance_score": chunk.get("relevance_score"),
            "preview": (chunk.get("content", "") or "")[:80],
        })
    raw_scores = [
        {"file_name": s.get("source", ""), "score": s.get("relevance_score")}
        for s in (data.get("debug_info", {}) or {}).get("scores", [])[:5]
    ]
    return {
        "query": query,
        "success": result.success,
        "inferred_category": data.get("inferred_category", ""),
        "retrieval_query": data.get("retrieval_query", ""),
        "store_count": (data.get("debug_info", {}) or {}).get("total_in_store"),
        "top_chunks": chunks,
        "raw_top_scores": raw_scores,
        "duration_ms": round(duration_ms, 1),
    }


async def main() -> None:
    init_tools()
    settings = get_settings()
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "retrieval_min_score": settings.retrieval_min_score,
        "results": [],
    }
    for question, expectation in GOLDEN_QUESTIONS:
        result = await run_question(question)
        result["expectation"] = expectation
        report["results"].append(result)
        print(f"\n=== {question}（期望: {expectation}）===")
        print(f"  success={result['success']} category={result['inferred_category']} {result['duration_ms']}ms")
        for chunk in result["top_chunks"]:
            print(
                f"  #{chunk['rank']} [{chunk['relevance_score']}] "
                f"{chunk['file_name']} ({chunk['knowledge_category']})"
            )

    out = Path(__file__).resolve().parents[1] / "golden_question_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入: {out}")


if __name__ == "__main__":
    asyncio.run(main())
