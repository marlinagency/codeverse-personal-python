from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_sql_runtime_assets_exist_and_match_registry():
    dockerfile = ROOT / "docker" / "runtimes" / "sql" / "Dockerfile"
    entrypoint = ROOT / "docker" / "runtimes" / "sql" / "run-codeverse-sql"

    assert dockerfile.exists()
    assert entrypoint.exists()

    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    entrypoint_text = entrypoint.read_text(encoding="utf-8")

    assert "FROM postgres:16-alpine" in dockerfile_text
    assert "run-codeverse-sql" in dockerfile_text
    assert "initdb" in entrypoint_text
    assert "psql" in entrypoint_text
    assert "ON_ERROR_STOP=1" in entrypoint_text


def test_sql_concept_mapping_doc_covers_core_decisions():
    doc = (ROOT / "docs" / "sql-concept-mapping.md").read_text(encoding="utf-8")

    assert "PostgreSQL 16" in doc
    assert "jsonb" in doc
    assert "Composite type" in doc or "composite type" in doc
    assert "Inheritance is intentionally unsupported" in doc
    assert "RAISE NOTICE" in doc


def test_docker_sandbox_doc_covers_operational_path():
    doc = (ROOT / "docs" / "docker-sandbox.md").read_text(encoding="utf-8")

    assert "build-sandbox-runtimes.ps1" in doc
    assert "network_disabled=True" in doc
    assert "VirtualMachinePlatform" in doc
    assert "tests\\sandbox -m docker" in doc
