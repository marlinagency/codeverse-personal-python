"""Application settings, loaded from environment (.env in dev)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODEVERSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Environment / runtime safety ---
    #: "development" | "production". Production refuses unsafe defaults (see
    #: the validator below) and, together with ``public_demo``, forbids the
    #: unsandboxed host-execution fallback (see ``unsandboxed_execution_permitted``).
    environment: str = "development"

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
    #: free-typed themes always use the primary provider above. AMD chip
    #: failures fall back to it and retain the primary provider provenance.
    amd_enabled: bool = False
    amd_base_url: str = "http://172.18.0.1:8001/v1"
    amd_model: str = "codeverse-student"
    amd_timeout_seconds: float = 15.0
    amd_max_tokens: int = 160

    # --- Database ---
    database_url: str = "postgresql+psycopg://codeverse:codeverse@localhost:5432/codeverse"

    # --- Auth ---
    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_expire_minutes: int = 1440
    jwt_algorithm: str = "HS256"

    # --- Sandbox ---
    sandbox_timeout_seconds: float = 10.0
    sandbox_memory_limit: str = "256m"
    sandbox_cpu_limit: float = 1.0
    sandbox_pids_limit: int = 64

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def unsandboxed_execution_permitted(self) -> bool:
        """Whether user code may run via the UNSANDBOXED host subprocess fallback.

        The host fallback (``run_local_python_demo``) has no container, network,
        filesystem, or resource isolation. It is only ever acceptable on a
        developer's own machine. It must never run in production or on the
        public-demo site, where anonymous visitors submit arbitrary code — a
        transient Docker outage there must fail closed (503), not silently
        downgrade to executing untrusted code on the host.
        """
        return not (self.is_production or self.public_demo)

    @model_validator(mode="after")
    def _enforce_runtime_safety(self) -> "Settings":
        if self.is_production and self.jwt_secret == _DEFAULT_JWT_SECRET:
            raise ValueError(
                "CODEVERSE_JWT_SECRET must be set to a strong random value in "
                "production (the built-in default is public and insecure)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
