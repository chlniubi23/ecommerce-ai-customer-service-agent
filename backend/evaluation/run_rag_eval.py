"""RAG 检索层评测运行器（任务 G1）。

评测对象：knowledge_search 工具链（真实索引，只评测检索层，不评测 LLM 回答生成）。
查询理解固定走规则快路径（allow_llm=False），保证离线、零成本、可重复执行。

指标：
- top1 命中率 / top3 命中率（答案类问题：top1/top3 命中 expected_source_hint 文件）；
- 平均 top1 分数；
- 无答案过滤率（expect_answer=False 的问题必须 success=False，验证不编造兜底）。

用法（在 backend/ 目录下，使用 venv 解释器）：
    .\\.venv\\Scripts\\python.exe -m evaluation.run_rag_eval --baseline
    .\\.venv\\Scripts\\python.exe -m evaluation.run_rag_eval --fail-under 0.8
    .\\.venv\\Scripts\\python.exe -m evaluation.run_rag_eval --fail-under 0.8 --top-k 3

说明：
- --baseline：把本次结果写入 evaluation/rag_baseline_report.json（知识补齐前的基线）；
- --fail-under <rate>：top1 命中率低于阈值或无答案过滤率不足 100% 时非零退出（供 CI 用）；
- 每次运行同时输出 evaluation/rag_eval_report.json（最新一次明细，不入库）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from evaluation.rag_dataset import RAG_EVAL_CASES

BASELINE_REPORT = Path(__file__).resolve().parent / "rag_baseline_report.json"
LATEST_REPORT = Path(__file__).resolve().parent / "rag_eval_report.json"


def _hit(file_names: list[str], hint: str) -> bool:
    return bool(hint) and any(hint in str(name or "") for name in file_names)


async def _eval_one(tool, case: dict, top_k: int) -> dict:
    """评测单条用例，返回逐条明细行。"""
    started = time.perf_counter()
    result = await tool.execute(
        query=case["question"],
        top_k=top_k,
        allow_llm=False,  # 规则快路径：离线、确定性、可重复
        workflow_id="rag_eval",
        session_id="rag_eval",
    )
    duration_ms = (time.perf_counter() - started) * 1000
    data = result.data or {}
    citations = data.get("citations") or []
    debug = data.get("debug_info") or {}

    file_names = [c.get("document_name", "") for c in citations]
    hint = case["expected_source_hint"]
    top1_hit = bool(case["expect_answer"]) and bool(file_names) and _hit(file_names[:1], hint)
    top3_hit = bool(case["expect_answer"]) and _hit(file_names[:3], hint)
    top1_score = float(citations[0].get("similarity_score", 0.0) or 0.0) if citations else 0.0

    if case["expect_answer"]:
        passed = top3_hit
    else:
        # 无答案问题：必须被过滤（success=False 且无 chunks），不得编造
        passed = (not result.success) and len(data.get("chunks") or []) == 0

    return {
        "question": case["question"],
        "expected_category": case["expected_category"],
        "expected_source_hint": hint,
        "expect_answer": case["expect_answer"],
        "is_colloquial": case.get("is_colloquial", False),
        "success": bool(result.success),
        "top1_hit": top1_hit,
        "top3_hit": top3_hit,
        "top1_score": round(top1_score, 4),
        "top1_file": file_names[0] if file_names else "",
        "top3_files": file_names[:3],
        "revalidation_triggered": bool((debug.get("revalidation") or {}).get("triggered")),
        "revalidation_reason": (debug.get("revalidation") or {}).get("reason", ""),
        "routes": debug.get("routes", {}),
        "duration_ms": round(duration_ms, 1),
        "passed": passed,
    }


def compute_metrics(rows: list[dict]) -> dict:
    """由逐条明细计算汇总指标（纯函数，供离线单测复用）。"""
    answerable = [row for row in rows if row["expect_answer"]]
    no_answer = [row for row in rows if not row["expect_answer"]]

    def _rate(values: list[bool]) -> float:
        return round(sum(1 for value in values if value) / len(values), 4) if values else 0.0

    return {
        "total_count": len(rows),
        "answerable_count": len(answerable),
        "no_answer_count": len(no_answer),
        "top1_hit_rate": _rate([row["top1_hit"] for row in answerable]),
        "top3_hit_rate": _rate([row["top3_hit"] for row in answerable]),
        "avg_top1_score": (
            round(sum(row["top1_score"] for row in answerable) / len(answerable), 4)
            if answerable else 0.0
        ),
        "no_answer_filter_rate": _rate([row["passed"] for row in no_answer]),
        "passed_count": sum(1 for row in rows if row["passed"]),
    }


async def run_eval(cases: list[dict] | None = None, top_k: int = 3) -> list[dict]:
    """运行完整评测，返回逐条明细（可注入 cases 供测试使用 mock 工具）。"""
    from app.tools.tool_registry import init_tools, tool_registry

    init_tools()
    tool = tool_registry.get("knowledge_search")
    if tool is None:
        raise RuntimeError("knowledge_search tool is not registered")

    rows = []
    for case in (cases or RAG_EVAL_CASES):
        rows.append(await _eval_one(tool, case, top_k))
    return rows


def _print_report(rows: list[dict], metrics: dict) -> None:
    print("\n===== RAG 检索评测明细 =====")
    for index, row in enumerate(rows, 1):
        status = "PASS" if row["passed"] else "FAIL"
        flag = " [口语]" if row["is_colloquial"] else ""
        no_answer = " [无答案]" if not row["expect_answer"] else ""
        print(
            f"{index:>2}. [{status}] {row['question']}{flag}{no_answer} | "
            f"top1={row['top1_score']} {row['top1_file'] or '-'}"
        )
        if row["revalidation_triggered"]:
            print(f"     ↳ 二次补检: {row['revalidation_reason']} → 命中 {len(row['top3_files'])} 条")
        if not row["passed"]:
            print(f"     ↳ 期望 {row['expected_category']}/{row['expected_source_hint'] or '无结果'}，"
                  f"实际 top3: {row['top3_files']}")

    print("\n===== 汇总 =====")
    print(f"总条数          : {metrics['total_count']}（答案类 {metrics['answerable_count']} / 无答案 {metrics['no_answer_count']}）")
    print(f"top1 命中率     : {metrics['top1_hit_rate']:.2%}")
    print(f"top3 命中率     : {metrics['top3_hit_rate']:.2%}")
    print(f"平均 top1 分数  : {metrics['avg_top1_score']}")
    print(f"无答案过滤率    : {metrics['no_answer_filter_rate']:.2%}")
    print(f"通过条数        : {metrics['passed_count']}/{metrics['total_count']}")


async def async_main(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    rows = await run_eval(top_k=args.top_k)
    metrics = compute_metrics(rows)
    metrics["wall_time_s"] = round(time.perf_counter() - started, 1)
    metrics["mode"] = "baseline" if args.baseline else "eval"
    _print_report(rows, metrics)

    report = {"metrics": metrics, "rows": rows}
    LATEST_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.baseline:
        BASELINE_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n基线报告已写入: {BASELINE_REPORT}")
    print(f"最新报告已写入: {LATEST_REPORT}")

    if args.fail_under is not None:
        if metrics["top1_hit_rate"] < args.fail_under:
            print(f"\nFAIL: top1 命中率 {metrics['top1_hit_rate']} 低于阈值 {args.fail_under}")
            return 1
        if metrics["no_answer_filter_rate"] < 1.0:
            print("\nFAIL: 存在无答案问题未被过滤（编造风险）")
            return 1
        print(f"\nPASS: top1 命中率 {metrics['top1_hit_rate']} ≥ 阈值 {args.fail_under}，无答案过滤率 100%")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 检索层评测（黄金问题集）")
    parser.add_argument("--baseline", action="store_true", help="写入基线报告 rag_baseline_report.json")
    parser.add_argument("--fail-under", type=float, default=None, help="top1 命中率阈值，低于则非零退出（无答案过滤率必须 100%）")
    parser.add_argument("--top-k", type=int, default=3, help="评测检索窗口（默认 3）")
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    sys.exit(main())
