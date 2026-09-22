"""测试环境全局配置（在测试模块 import 前生效）。

- EMBEDDING_WARMUP=false：禁用 BGE 启动预热，保证测试不真实加载模型（红线 #5）；
- HF_HUB_OFFLINE=1：任何意外的模型访问都走离线路径，避免网络挂起。
"""

import os

os.environ.setdefault("EMBEDDING_WARMUP", "false")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
