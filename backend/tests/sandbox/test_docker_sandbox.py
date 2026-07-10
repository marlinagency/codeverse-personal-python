from __future__ import annotations

from pathlib import Path

import docker
import pytest
from docker.errors import DockerException, ImageNotFound

from codeverse_sandbox import DockerSandboxRunner, SandboxLimits


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def docker_client():
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        pytest.skip(f"Docker daemon is not available: {exc}")
    return client


def ensure_image(client, tag: str, dockerfile_dir: Path) -> None:
    try:
        client.images.get(tag)
        return
    except ImageNotFound:
        pass

    client.images.build(
        path=str(dockerfile_dir),
        tag=tag,
        rm=True,
        forcerm=True,
    )


@pytest.mark.docker
def test_python_runtime_executes_generated_code(docker_client):
    ensure_image(
        docker_client,
        "codeverse-python-runtime:3.12",
        ROOT / "docker" / "runtimes" / "python",
    )

    result = DockerSandboxRunner(client=docker_client).run(
        language="python",
        source_code="print('codeverse-python-ok')\n",
        limits=SandboxLimits(timeout_seconds=3),
    )

    assert result.status == "success"
    assert result.exit_code == 0
    assert result.stdout.strip() == "codeverse-python-ok"
    assert result.stderr == ""


@pytest.mark.docker
def test_sql_runtime_executes_ephemeral_postgres(docker_client):
    ensure_image(
        docker_client,
        "codeverse-sql-runtime:16",
        ROOT / "docker" / "runtimes" / "sql",
    )

    result = DockerSandboxRunner(client=docker_client).run(
        language="sql",
        source_code="DO $$ BEGIN RAISE NOTICE 'codeverse-sql-ok'; END $$;\n",
        limits=SandboxLimits(timeout_seconds=10, memory="512m"),
    )

    combined_output = result.stdout + result.stderr
    assert result.status == "success"
    assert result.exit_code == 0
    assert "codeverse-sql-ok" in combined_output


@pytest.mark.docker
def test_python_runtime_timeout_is_reported(docker_client):
    ensure_image(
        docker_client,
        "codeverse-python-runtime:3.12",
        ROOT / "docker" / "runtimes" / "python",
    )

    result = DockerSandboxRunner(client=docker_client).run(
        language="python",
        source_code="while True:\n    pass\n",
        limits=SandboxLimits(timeout_seconds=0.5),
    )

    assert result.status == "timeout"
    assert result.timed_out is True
