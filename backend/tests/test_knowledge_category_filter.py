import unittest

from app.tools.knowledge_search_tool import (
    _resolve_allowed_categories,
    _chunk_matches_any_category,
    _normalize_category,
)


def _chunk(cat, file_name):
    return {"metadata": {"knowledge_category": cat, "file_name": file_name}}


class KnowledgeCategoryFilterTest(unittest.TestCase):
    def test_union_keeps_keyword_category_when_llm_mislabels(self):
        # LLM said policy, keyword says refund -> both allowed
        allowed = _resolve_allowed_categories("", "policy", "refund")
        self.assertEqual(allowed, ["policy", "refund"])
        refund_chunk = _chunk("refund", "seven_day_return_atomic.md")
        self.assertTrue(_chunk_matches_any_category(refund_chunk, allowed))

    def test_explicit_category_first_and_deduped(self):
        allowed = _resolve_allowed_categories("refund", "refund", "refund")
        self.assertEqual(allowed, ["refund"])

    def test_empty_categories_dropped(self):
        self.assertEqual(_resolve_allowed_categories("", "", "refund"), ["refund"])
        self.assertEqual(_resolve_allowed_categories("", "", ""), [])

    def test_keyword_category_for_seven_day_return_is_refund(self):
        self.assertEqual(_normalize_category("", "七天无理由退货的规则是什么？"), "refund")

    def test_policy_only_chunk_excluded_when_refund_query(self):
        allowed = _resolve_allowed_categories("", "policy", "refund")
        # a refund chunk is kept; a pure unrelated-category chunk (operation) is not
        self.assertTrue(_chunk_matches_any_category(_chunk("refund", "refund_policy_v1.md"), allowed))
        self.assertFalse(_chunk_matches_any_category(_chunk("operation", "pricing_strategy.md"), allowed))
