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
    .\\.venv\\Scripts\\python.exe -m evaluation.run_rag_eval --fail-under 0.8 --borderline-cases 28

说明：
- --baseline：把本次结果写入 evaluation/rag_baseline_report.json（知识补齐前的基线）；
- --fail-under <rate>：top1 命中率低于阈值或无答案过滤率不足 100% 时非零退出（供 CI 用）；
- --borderline-cases <ids>：临界用例白名单（逗号分隔用例编号，默认空 = 本地严格模式，
  行为与历史版本完全一致）。白名单内**无答案用例**的失败降级为 [BORDERLINE] WARN，
  不计入失败、不触发非零退出；答案类用例不受白名单影响。
  适用场景：跨 CPU（oneDNN/MKL 内核与硬件代际）的 embedding 浮点数值漂移会使临界
  用例的 top1 分数在不同机器间翻转。典型个案 #28「怎么申请营业执照」（无答案类）：
  其与 payment_faq.txt 的语义相似度恰在 0.35 阈值临界，Windows 本机（MKL）正确拒答
  （top1=0.0），GitHub 异构 runner 上在 0.34~0.47 间漂移，越阈值即误判为有答案。
  OMP 单线程 + ONEDNN AVX2 钉死已收窄漂移但无法根除，故 CI 对该用例白名单容忍，
  本地严格模式仍按失败计。
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


def _parse_borderline(raw: str) -> set[int]:
    """解析 --borderline-cases（逗号分隔用例编号）为集合；默认空 = 本地严格模式。"""
    return {int(item.strip()) for item in (raw or "").split(",") if item.strip()}


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


def _print_report(rows: list[dict], metrics: dict, borderline: set[int] | None = None) -> None:
    borderline = borderline or set()
    print("\n===== RAG 检索评测明细 =====")
    for index, row in enumerate(rows, 1):
        tolerated = (
            index in borderline and not row["passed"] and not row["expect_answer"]
        )
        status = "BORDERLINE" if tolerated else ("PASS" if row["passed"] else "FAIL")
        flag = " [口语]" if row["is_colloquial"] else ""
        no_answer = " [无答案]" if not row["expect_answer"] else ""
        print(
            f"{index:>2}. [{status}] {row['question']}{flag}{no_answer} | "
            f"top1={row['top1_score']} {row['top1_file'] or '-'}"
        )
        if row["revalidation_triggered"]:
            print(f"     ↳ 二次补检: {row['revalidation_reason']} → 命中 {len(row['top3_files'])} 条")
        if tolerated:
            print(f"     ↳ #{index} 跨CPU数值漂移，CI白名单容忍，本地严格模式仍计失败")
        elif not row["passed"]:
            print(f"     ↳ 期望 {row['expected_category']}/{row['expected_source_hint'] or '无结果'}，"
                  f"实际 top3: {row['top3_files']}")

    print("\n===== 汇总 =====")
    print(f"总条数          : {metrics['total_count']}（答案类 {metrics['answerable_count']} / 无答案 {metrics['no_answer_count']}）")
    print(f"top1 命中率     : {metrics['top1_hit_rate']:.2%}")
    print(f"top3 命中率     : {metrics['top3_hit_rate']:.2%}")
    print(f"平均 top1 分数  : {metrics['avg_top1_score']}")
    print(f"无答案过滤率    : {metrics['no_answer_filter_rate']:.2%}")
    print(f"通过条数        : {metrics['passed_count']}/{metrics['total_count']}")
    if borderline:
        tolerated_count = sum(
            1
            for index, row in enumerate(rows, 1)
            if index in borderline and not row["passed"] and not row["expect_answer"]
        )
        print(f"临界容忍      : {tolerated_count} 条（仅白名单生效）")


async def async_main(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    borderline = _parse_borderline(args.borderline_cases)
    rows = await run_eval(top_k=args.top_k)
    metrics = compute_metrics(rows)
    metrics["wall_time_s"] = round(time.perf_counter() - started, 1)
    metrics["mode"] = "baseline" if args.baseline else "eval"
    if borderline:
        metrics["borderline_tolerated"] = sum(
            1
            for index, row in enumerate(rows, 1)
            if index in borderline and not row["passed"] and not row["expect_answer"]
        )
    _print_report(rows, metrics, borderline=borderline)

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
        # 无答案门槛：白名单内的无答案失败被容忍（跨CPU数值漂移），其余仍严格要求
        unfiltered = [
            index
            for index, row in enumerate(rows, 1)
            if not row["expect_answer"] and not row["passed"] and index not in borderline
        ]
        if unfiltered:
            detail = f"，用例: {unfiltered}" if borderline else ""
            print(f"\nFAIL: 存在无答案问题未被过滤（编造风险）{detail}")
            return 1
        tolerated = metrics.get("borderline_tolerated", 0)
        suffix = f"，白名单容忍 {tolerated} 条（本地严格模式仍计失败）" if tolerated else ""
        print(
            f"\nPASS: top1 命中率 {metrics['top1_hit_rate']} ≥ 阈值 {args.fail_under}，"
            f"无答案过滤率 100%{suffix}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 检索层评测（黄金问题集）")
    parser.add_argument("--baseline", action="store_true", help="写入基线报告 rag_baseline_report.json")
    parser.add_argument("--fail-under", type=float, default=None, help="top1 命中率阈值，低于则非零退出（无答案过滤率必须 100%）")
    parser.add_argument("--top-k", type=int, default=3, help="评测检索窗口（默认 3）")
    parser.add_argument(
        "--borderline-cases",
        type=str,
        default="",
        help="临界用例白名单（逗号分隔编号，如 28）：无答案用例失败降级为 WARN 不触发退出；默认空 = 本地严格模式",
    )
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    sys.exit(main())
