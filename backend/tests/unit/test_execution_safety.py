"""Phase 1a security: fail-closed sandbox fallback + production config guards.

The Docker sandbox is the only isolated way to run user code. When it is
unreachable the app must NOT silently execute untrusted code on the host in
production or on the public-demo site — it must fail closed with a 503. It
stays available only on a developer's own machine.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from codeverse_api.config import Settings
from codeverse_api.routers.execute import guard_unsandboxed_execution


def test_default_dev_settings_permit_host_fallback():
    settings = Settings()  # environment=development, public_demo=False
    assert settings.is_production is False
    assert settings.unsandboxed_execution_permitted is True
    # Should not raise: dev machines may use the unsandboxed host fallback.
    guard_unsandboxed_execution(settings)


def test_production_forbids_host_fallback():
    settings = Settings(environment="production", jwt_secret="a-real-secret")
    assert settings.is_production is True
    assert settings.unsandboxed_execution_permitted is False
    with pytest.raises(HTTPException) as raised:
        guard_unsandboxed_execution(settings)
    assert raised.value.status_code == 503


def test_public_demo_forbids_host_fallback():
    # The deployed public site sets CODEVERSE_PUBLIC_DEMO=1 — anonymous
    # visitors must never reach unsandboxed host execution.
    settings = Settings(public_demo=True)
    assert settings.unsandboxed_execution_permitted is False
    with pytest.raises(HTTPException) as raised:
        guard_unsandboxed_execution(settings)
    assert raised.value.status_code == 503


def test_production_rejects_default_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(environment="production")  # keeps the insecure default secret


def test_production_accepts_strong_jwt_secret():
    settings = Settings(environment="production", jwt_secret="0123456789abcdef")
    assert settings.is_production is True


def test_environment_value_is_case_insensitive():
    assert Settings(environment="PRODUCTION", jwt_secret="x").is_production is True
    assert Settings(environment="Development").is_production is False
