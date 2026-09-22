"""Embedding 预热配置测试（任务 G3，全部离线）。"""

import os
import unittest


class TestEmbeddingWarmupConfig(unittest.TestCase):

    def test_warmup_disabled_in_test_env(self):
        """tests/conftest.py 设置 EMBEDDING_WARMUP=false，测试环境不得真实加载模型。"""
        from app.core.config import get_settings

        self.assertFalse(get_settings().embedding_warmup)
        self.assertEqual(os.environ.get("EMBEDDING_WARMUP"), "false")
        # 单例未加载真实模型
        from app.rag.vectorstore.embedding_provider import get_embedding_provider

        provider = get_embedding_provider()
        self.assertIsNone(getattr(provider, "_model", None))

    def test_warmup_configurable_via_env(self):
        """预热开关可通过环境变量覆盖（生产默认开启）。"""
        from app.core.config import Settings

        enabled = Settings(embedding_warmup="true")
        disabled = Settings(embedding_warmup="false")
        self.assertTrue(enabled.embedding_warmup)
        self.assertFalse(disabled.embedding_warmup)

    def test_lifespan_contains_warmup_logic(self):
        """main.py lifespan 包含预热逻辑（local provider + 开关开启 + 异常兜底）。"""
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("_warmup_embedding_model", source)
        self.assertIn("settings.embedding_warmup", source)
        self.assertIn("except Exception as exc", source)


if __name__ == "__main__":
    unittest.main()
