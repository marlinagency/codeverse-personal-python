"""Application settings, loaded from environment (.env in dev)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODEVERSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Deployment ---
    #: comma-separated browser origins allowed by CORS (dev default: Vite)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    #: public-demo mode: every visitor gets their OWN anonymous account
    #: (tracked by an HttpOnly cookie) instead of the shared dev user, so
    #: strangers never see each other's themes on the deployed site.
    public_demo: bool = False

    # --- LLM provider selection ---
    llm_provider: str = "fake"  # fireworks | openai_compatible | anthropic | fake

    fireworks_api_key: str = ""
    fireworks_model: str = "accounts/fireworks/models/glm-5p2"

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # --- AMD student model (fine-tuned on AMD Instinct, served via vLLM/tunnel) ---
    #: when true, curated theme chips are answered by our own AMD-hosted model;
    #: free-typed themes always use the primary provider above. Any AMD failure
    #: transparently falls back to the primary provider so the app never breaks.
    amd_enabled: bool = False
    amd_base_url: str = "http://172.18.0.1:8001/v1"
    amd_model: str = "codeverse-student"

    # --- Database ---
    database_url: str = "postgresql+psycopg://codeverse:codeverse@localhost:5432/codeverse"

    # --- Auth ---
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 1440
    jwt_algorithm: str = "HS256"

    # --- Sandbox ---
    sandbox_timeout_seconds: float = 10.0
    sandbox_memory_limit: str = "256m"
    sandbox_cpu_limit: float = 1.0
    sandbox_pids_limit: int = 64


@lru_cache
def get_settings() -> Settings:
    return Settings()
