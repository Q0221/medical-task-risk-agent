"""应用配置：基于 pydantic-settings 读取环境变量与 .env。"""

from functools import lru_cache
from typing import List
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "medical-task-risk-agent"
    APP_ENV: str = "dev"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "root"
    MYSQL_DB: str = "medical_agent"

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    LLM_PROVIDER: str = "dashscope"
    LLM_MODEL: str = "qwen-plus"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "medical-task-risk-agent"
    LANGSMITH_TRACING: bool = False

    RAG_BASE_URL: str = ""
    RAG_API_KEY: str = ""

    # ── Notify Agent（Phase 8）──────────────────────────────────────────
    # 默认通知渠道：im（站内消息）| wxwork | email
    DEFAULT_NOTIFY_CHANNEL: str = "im"

    # 企业微信群机器人 Webhook（留空则禁用）
    WXWORK_WEBHOOK_URL: str = ""
    # 推送时是否 @所有人
    WXWORK_MENTION_ALL: bool = False

    # SMTP 邮件（留空则禁用）
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_SSL: bool = True

    @property
    def database_url(self) -> str:
        password = quote_plus(self.MYSQL_PASSWORD) if self.MYSQL_PASSWORD else ""
        auth = f"{self.MYSQL_USER}:{password}" if password else self.MYSQL_USER
        return (
            f"mysql+asyncmy://{auth}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/"
            f"{self.MYSQL_DB}?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return (
                f"redis://:{quote_plus(self.REDIS_PASSWORD)}@"
                f"{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            )
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
