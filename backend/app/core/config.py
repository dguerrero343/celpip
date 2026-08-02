from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "CELPIP Writing Coach API"
    api_v1_prefix: str = ""
    root_path: str = "/api"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    demo_mode: bool = False
    admin_emails: list[str] = Field(default_factory=list)

    database_url: str = "postgresql+asyncpg://celpip_app:change-me@localhost:5432/celpip"

    jwt_secret_key: str = "development-only-secret-change-me-now"
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)

    openai_api_key: SecretStr | None = None
    openai_admin_key: SecretStr | None = None
    openai_project_id: str | None = None
    openai_model: str = "gpt-5-mini"
    openai_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "low"
    max_ai_context_tokens: int = Field(default=6000, ge=3000)
    max_history_items: int = Field(default=5, ge=0, le=50)
    max_response_tokens: int = Field(default=4000, ge=128)
    openai_timeout_seconds: float = Field(default=45.0, ge=5.0, le=300.0)
    openai_max_retries: int = Field(default=2, ge=0, le=5)
    openai_input_cost_per_million: Decimal = Field(default=Decimal("0.25"), ge=0)
    openai_cached_input_cost_per_million: Decimal = Field(default=Decimal("0.025"), ge=0)
    openai_output_cost_per_million: Decimal = Field(default=Decimal("2.00"), ge=0)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production" and len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 characters in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
