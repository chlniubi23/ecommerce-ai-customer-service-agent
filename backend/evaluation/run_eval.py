"""路由层评测运行器。

评测对象是"路由决策层"（分类器 + 确认闸门 + 多域协调），不涉及真实工具
执行与写库，全部用例可离线运行。两种模式：

- 离线（默认）：把分类器的 LLM 客户端替换为必抛异常的桩，逼规则层独立作答。
  可重复、零成本，适合放进 CI 做回归。layer=llm 的用例会被跳过并单独统计。
- 在线（--live）：layer=llm 的用例用真实 LLM 分类，得到含 LLM 层的全量准确率。

用法（在 backend/ 目录下）：
    python -m evaluation.run_eval
    python -m evaluation.run_eval --live
    python -m evaluation.run_eval --json     # 表格后追加机器可读 JSON
    python -m evaluation.run_eval --strict   # 有失败时以非零退出码结束（CI 用）
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from app.agents import classifier
from app.agents.complaint_intent import (
    is_confirmation,
    is_denial,
    is_explicit_create_request,
    is_followup_request,
    resolve_complaint_gate,
)
from app.agents.coordinator import should_coordinate
from evaluation.dataset import EVAL_CASES


class _DisabledCompletions:
    async def create(self, *args, **kwargs):
        raise RuntimeError("evaluation: LLM disabled (offline rule-layer mode)")


def _disable_llm():
    """把分类器的 LLM 客户端替换为必抛异常的桩。

    classify_intent 对 LLM 异常的兜底是返回 GENERAL/0.0，因此规则层用例
    一旦失手立即暴露为失败，不会被 LLM"救回来"。
    """
    stub = SimpleNamespace(chat=SimpleNamespace(completions=_DisabledCompletions()))
    return patch.object(classifier, "client", stub)


async def _eval_case(case: dict, live: bool) -> tuple[str, object]:
    """返回 (status, got)。status ∈ pass/fail/skipped。"""
    kind = case["kind"]
    layer = case.get("layer", "rule")
    if layer == "llm" and not live:
        return "skipped", None

    with ExitStack() as stack:
        if layer == "rule":
            stack.enter_context(_disable_llm())

        if kind == "intent":
            got = (await classifier.classify_intent(case["text"])).intent.value
            ok = got == case["expected"]
        elif kind == "gate":
            got = resolve_complaint_gate(True, case["text"])
            ok = got == case["expected"]
        elif kind == "confirm":
            got = is_confirmation(case["text"])
            ok = got is case["expected"]
        elif kind == "deny":
            got = is_denial(case["text"])
            ok = got is case["expected"]
        elif kind == "create":
            got = is_explicit_create_request(case["text"])
            ok = got is case["expected"]
        elif kind == "followup":
            got = is_followup_request(case["text"])
            ok = got is case["expected"]
        elif kind == "coordinate":
            got = should_coordinate(case["text"])
            ok = got is case["expected"]
        else:
            raise ValueError(f"未知评测类型: {kind}")

    return ("pass" if ok else "fail"), got


async def _run_all(live: bool) -> list[tuple[dict, str, object]]:
    out = []
    for case in EVAL_CASES:
        status, got = await _eval_case(case, live)
        out.append((case, status, got))
    return out


def _bucket(case: dict) -> str:
    layer = case.get("layer", "rule")
    return f"{case['kind']}[{layer}]" if case["kind"] == "intent" else case["kind"]


def _print_report(results, live: bool, as_json: bool) -> int:
    stats: dict[str, defaultdict] = defaultdict(lambda: {"pass": 0, "fail": 0, "skipped": 0})
    failures = []
    for case, status, got in results:
        stats[_bucket(case)][status] += 1
        if status == "fail":
            failures.append({
                "kind": _bucket(case),
                "text": case["text"],
                "expected": case["expected"],
                "got": got,
                "note": case.get("note", ""),
            })

    mode = "在线（含 LLM 层）" if live else "离线（LLM 已屏蔽，仅规则层）"
    total = len(results)
    skipped = sum(s["skipped"] for s in stats.values())
    rule_pass = sum(s["pass"] for k, s in stats.items() if not k.endswith("[llm]"))
    rule_valid = sum(s["pass"] + s["fail"] for k, s in stats.items() if not k.endswith("[llm]"))

    print("=" * 56)
    print(f"路由层评测  模式: {mode}  用例总数: {total}")
    print("=" * 56)
    print(f"{'分类':<24}{'通过/有效':<12}{'准确率':<10}{'跳过'}")
    for bucket in stats:
        s = stats[bucket]
        valid = s["pass"] + s["fail"]
        acc = f"{s['pass'] / valid * 100:.1f}%" if valid else "-"
        print(f"{bucket:<24}{s['pass']}/{valid:<10}{acc:<10}{s['skipped']}")
    print("-" * 56)
    rule_acc = f"{rule_pass / rule_valid * 100:.1f}%" if rule_valid else "-"
    print(f"规则层合计（不含 LLM 层）: {rule_pass}/{rule_valid} = {rule_acc}")
    if failures:
        print(f"\n失败用例 ({len(failures)}):")
        for f in failures:
            note = f"  # {f['note']}" if f["note"] else ""
            print(f"  [{f['kind']}] {f['text']!r}  期望={f['expected']}  实际={f['got']}{note}")
    else:
        print("\n全部通过 ✓")

    if as_json:
        print(json.dumps({
            "mode": "live" if live else "offline",
            "total": total,
            "skipped": skipped,
            "rule_layer": {"pass": rule_pass, "valid": rule_valid, "accuracy": rule_acc},
            "per_bucket": {k: dict(v) for k, v in stats.items()},
            "failures": failures,
        }, ensure_ascii=False, indent=2))
    return len(failures)


def main() -> None:
    parser = argparse.ArgumentParser(description="路由层评测：意图分类 / 确认闸门 / 多域协调")
    parser.add_argument("--live", action="store_true", help="用真实 LLM 跑 llm 层用例（需配置 API Key，产生少量调用费用）")
    parser.add_argument("--strict", action="store_true", help="有失败用例时以非零退出码结束（CI 用）")
    parser.add_argument("--json", action="store_true", help="表格后追加机器可读 JSON")
    args = parser.parse_args()

    results = asyncio.run(_run_all(args.live))
    failures = _print_report(results, args.live, args.json)
    if args.strict and failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
