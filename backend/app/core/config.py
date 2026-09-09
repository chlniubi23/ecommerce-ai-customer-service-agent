"""
核心配置模块

职责：
- 集中管理所有环境变量
- 提供类型安全的配置访问
- 支持多环境切换（development / production）

扩展规划：
- Phase 2: 增加 Tool Calling 相关配置
- Phase 3: 增加向量数据库连接配置
- Phase 4: 增加 Redis、数据库连接配置
"""

from pathlib import Path

from pydantic_settings import BaseSettings
from functools import lru_cache


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    应用配置类

    使用 pydantic-settings 自动从 .env 文件加载环境变量，
    提供类型验证和默认值支持。
    """

    # ========== 应用基础配置 ==========
    app_env: str = "development"
    app_debug: bool = False
    app_name: str = "E-commerce Customer Service Agent"
    app_version: str = "0.1.0"

    # ========== OpenAI API 配置 ==========
    # 兼容 OpenAI / DeepSeek / 其他 OpenAI 兼容 API
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-3.5-turbo"
    # 请求超时（秒）与 SDK 级自动重试次数。
    # 不显式设置时 SDK 默认超时约 600s，LLM 故障时用户会长时间挂起。
    openai_timeout: float = 60.0
    openai_max_retries: int = 2

    # ========== CORS 配置 ==========
    frontend_url: str = "http://localhost:3000"

    # ========== MySQL Business Database ==========
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "ai_agent_commerce_demo"
    mysql_charset: str = "utf8mb4"

    class Config:
        # 指定 .env 文件路径
        env_file = str(BACKEND_ROOT / ".env")
        # 环境变量名大小写不敏感
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    获取应用配置单例

    使用 lru_cache 确保配置只加载一次，
    避免重复读取 .env 文件。

    Returns:
        Settings: 应用配置实例
    """
    return Settings()
