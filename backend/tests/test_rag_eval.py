"""RAG 评测集与知识补齐的离线测试（任务 G1/G2）。

覆盖：
1. 数据集结构合法性（条数/字段/类别覆盖/口语变体/无答案条目）；
2. 评测指标计算对 mock 检索结果的正确性；
3. 新增知识文件格式校验（目录=类别、非空、命名风格、知识分类一致）。
"""

import unittest
from pathlib import Path

from evaluation.rag_dataset import NO_ANSWER_COUNT, RAG_EVAL_CASES

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[1] / "knowledge_base" / "knowledge"


class TestRagDatasetStructure(unittest.TestCase):
    """G1：数据集结构合法性。"""

    def test_case_count_within_required_range(self):
        # 方案要求 25~30 条（G2 修订后仍保持 30）
        self.assertGreaterEqual(len(RAG_EVAL_CASES), 25)
        self.assertLessEqual(len(RAG_EVAL_CASES), 30)

    def test_required_fields_present(self):
        for case in RAG_EVAL_CASES:
            self.assertIn("question", case)
            self.assertIn("expected_category", case)
            self.assertIn("expected_source_hint", case)
            self.assertIn("expect_answer", case)
            self.assertIn("is_colloquial", case)
            self.assertIsInstance(case["question"], str)
            self.assertTrue(case["question"].strip())

    def test_questions_unique(self):
        questions = [case["question"] for case in RAG_EVAL_CASES]
        self.assertEqual(len(questions), len(set(questions)))

    def test_every_category_covered_at_least_twice(self):
        answerable_categories: dict[str, int] = {}
        for case in RAG_EVAL_CASES:
            if case["expect_answer"]:
                key = case["expected_category"]
                answerable_categories[key] = answerable_categories.get(key, 0) + 1
        for category in (
            "refund", "coupon", "membership", "logistics", "complaint",
            "product", "policy", "sop", "operation", "faq",
        ):
            self.assertGreaterEqual(
                answerable_categories.get(category, 0), 2,
                f"类别 {category} 覆盖不足 2 条",
            )

    def test_every_category_has_colloquial_variant(self):
        colloquial_categories = {
            case["expected_category"]
            for case in RAG_EVAL_CASES
            if case["expect_answer"] and case["is_colloquial"]
        }
        for category in (
            "refund", "coupon", "membership", "logistics", "complaint",
            "product", "policy", "sop", "operation", "faq",
        ):
            self.assertIn(category, colloquial_categories, f"类别 {category} 缺口语变体")

    def test_no_answer_cases_exist_and_hint_empty(self):
        no_answer = [case for case in RAG_EVAL_CASES if not case["expect_answer"]]
        self.assertEqual(len(no_answer), NO_ANSWER_COUNT)
        self.assertEqual(len(no_answer), 3)
        for case in no_answer:
            self.assertEqual(case["expected_source_hint"], "")
            self.assertEqual(case["expected_category"], "other")

    def test_answerable_cases_have_hint(self):
        for case in RAG_EVAL_CASES:
            if case["expect_answer"]:
                self.assertTrue(case["expected_source_hint"].strip())


class TestEvalMetrics(unittest.TestCase):
    """G1：指标计算对 mock 检索结果的正确性（纯函数，无 IO）。"""

    @staticmethod
    def _row(question="q", expect_answer=True, top1_hit=False, top3_hit=False,
             top1_score=0.0, passed=False):
        return {
            "question": question,
            "expected_category": "refund",
            "expected_source_hint": "demo",
            "expect_answer": expect_answer,
            "is_colloquial": False,
            "success": True,
            "top1_hit": top1_hit,
            "top3_hit": top3_hit,
            "top1_score": top1_score,
            "top1_file": "demo.txt" if top1_hit else "",
            "top3_files": [],
            "revalidation_triggered": False,
            "revalidation_reason": "",
            "routes": {},
            "duration_ms": 1.0,
            "passed": passed,
        }

    def test_metrics_on_mock_results(self):
        from evaluation.run_rag_eval import compute_metrics

        rows = [
            self._row("a", True, top1_hit=True, top3_hit=True, top1_score=0.8, passed=True),
            self._row("b", True, top1_hit=False, top3_hit=True, top1_score=0.6, passed=True),
            self._row("c", True, top1_hit=False, top3_hit=False, top1_score=0.3, passed=False),
            self._row("d", False, passed=True),   # 无答案被过滤
            self._row("e", False, passed=False),  # 无答案未被过滤
        ]
        metrics = compute_metrics(rows)

        self.assertEqual(metrics["total_count"], 5)
        self.assertEqual(metrics["answerable_count"], 3)
        self.assertEqual(metrics["no_answer_count"], 2)
        self.assertEqual(metrics["top1_hit_rate"], round(1 / 3, 4))
        self.assertEqual(metrics["top3_hit_rate"], round(2 / 3, 4))
        self.assertEqual(metrics["avg_top1_score"], round((0.8 + 0.6 + 0.3) / 3, 4))
        self.assertEqual(metrics["no_answer_filter_rate"], 0.5)

    def test_metrics_on_empty_rows(self):
        from evaluation.run_rag_eval import compute_metrics

        metrics = compute_metrics([])
        self.assertEqual(metrics["top1_hit_rate"], 0.0)
        self.assertEqual(metrics["no_answer_filter_rate"], 0.0)


class TestNewKnowledgeFiles(unittest.TestCase):
    """G2：新增知识文件格式校验（目录=类别、非空、atomic 命名、分类一致）。"""

    NEW_FILES = [
        ("refund", "no_reason_return_guide_atomic.txt", "refund"),
        ("membership", "points_usage_atomic.txt", "membership"),
        ("logistics", "late_delivery_atomic.txt", "logistics"),
        ("complaint", "complaint_channel_atomic.txt", "complaint"),
        ("sop", "refund_sop_atomic.txt", "sop"),
        ("sop", "escalation_sop_atomic.txt", "sop"),
        ("operation", "promotion_overview_atomic.txt", "operation"),
        ("faq", "payment_methods_atomic.txt", "faq"),
        ("faq", "service_boundary_atomic.txt", "faq"),
    ]

    def test_new_files_exist_in_correct_category_dir(self):
        for category, file_name, _expected_category in self.NEW_FILES:
            path = KNOWLEDGE_ROOT / category / file_name
            self.assertTrue(path.exists(), f"缺少知识文件: {path}")
            self.assertTrue(path.stat().st_size > 0, f"知识文件为空: {path}")

    def test_new_files_follow_atomic_naming_and_format(self):
        for category, file_name, expected_category in self.NEW_FILES:
            path = KNOWLEDGE_ROOT / category / file_name
            content = path.read_text(encoding="utf-8")
            # atomic 卡命名规范
            if file_name.endswith("_atomic.txt"):
                self.assertIn("原子知识卡", content, f"{file_name} 缺少原子知识卡标题")
                self.assertIn("标准答案", content, f"{file_name} 缺少标准答案小节")
            # 知识分类与目录一致
            self.assertIn(
                f"知识分类：{expected_category}", content,
                f"{file_name} 的知识分类应与目录 {category} 一致",
            )
            # 检索关键词必须存在（口语命中的关键杠杆）
            self.assertIn("检索关键词", content, f"{file_name} 缺少检索关键词")

    def test_no_filename_conflicts_with_existing(self):
        existing = {path.name for path in KNOWLEDGE_ROOT.rglob("*.txt")}
        for category, file_name, _expected_category in self.NEW_FILES:
            # 同名文件应只存在于当前目录（无跨类别重名）
            owners = [
                path.parent.name
                for path in KNOWLEDGE_ROOT.rglob(file_name)
            ]
            self.assertEqual(owners, [category], f"{file_name} 存在跨类别重名冲突")


if __name__ == "__main__":
    unittest.main()
