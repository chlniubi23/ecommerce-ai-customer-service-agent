"""路由层评测包：标注数据集 + 运行脚本。

用于回答"意图路由准确率多少、怎么测的"：
    python -m evaluation.run_eval          # 离线模式（屏蔽 LLM，测规则层，可重复、零成本）
    python -m evaluation.run_eval --live   # 在线模式（LLM 层用真实 API）
"""
