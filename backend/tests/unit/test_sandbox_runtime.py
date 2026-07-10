from __future__ import annotations

import pytest

from codeverse_sandbox import (
    DockerSandboxRunner,
    SandboxLimits,
    SandboxRuntimeNotFoundError,
    get_runtime,
)


def test_python_runtime_registered():
    runtime = get_runtime("PYTHON")

    assert runtime.language == "python"
    assert runtime.image == "codeverse-python-runtime:3.12"
    assert runtime.source_filename == "main.py"
    assert runtime.command == ("python", "/workspace/main.py")


def test_sql_runtime_registered():
    runtime = get_runtime("sql")

    assert runtime.language == "sql"
    assert runtime.image == "codeverse-sql-runtime:16"
    assert runtime.source_filename == "main.sql"
    assert runtime.command == ("/usr/local/bin/run-codeverse-sql", "/workspace/main.sql")


def test_unknown_runtime_rejected():
    with pytest.raises(SandboxRuntimeNotFoundError, match="javascript"):
        get_runtime("javascript")


def test_limits_validate_positive_values():
    with pytest.raises(ValueError, match="timeout"):
        SandboxLimits(timeout_seconds=0)
    with pytest.raises(ValueError, match="memory"):
        SandboxLimits(memory="")
    with pytest.raises(ValueError, match="nano_cpus"):
        SandboxLimits(nano_cpus=0)
    with pytest.raises(ValueError, match="pids_limit"):
        SandboxLimits(pids_limit=0)


def test_runner_starts_locked_down_container():
    client = _FakeDockerClient()
    limits = SandboxLimits(timeout_seconds=1, memory="128m", nano_cpus=500_000_000, pids_limit=32)

    result = DockerSandboxRunner(client=client).run(
        language="python",
        source_code="print('hello')\n",
        limits=limits,
    )

    assert result.status == "success"
    assert result.exit_code == 0
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.language == "python"

    kwargs = client.containers.last_run_kwargs
    assert kwargs["image"] == "codeverse-python-runtime:3.12"
    assert kwargs["command"] == ["python", "/workspace/main.py"]
    assert kwargs["network_disabled"] is True
    assert kwargs["user"] == "1000:1000"
    assert kwargs["mem_limit"] == "128m"
    assert kwargs["nano_cpus"] == 500_000_000
    assert kwargs["pids_limit"] == 32
    assert kwargs["remove"] is False

    volume = next(iter(kwargs["volumes"].values()))
    assert volume == {"bind": "/workspace", "mode": "ro"}

    assert client.containers.container.removed is True


class _FakeDockerClient:
    def __init__(self) -> None:
        self.containers = _FakeContainers()


class _FakeContainers:
    def __init__(self) -> None:
        self.container = _FakeContainer()
        self.last_run_kwargs = {}

    def run(self, **kwargs):
        self.last_run_kwargs = kwargs
        return self.container


class _FakeContainer:
    removed = False

    def wait(self):
        return {"StatusCode": 0}

    def logs(self, *, stdout, stderr):
        if stdout:
            return b"hello\n"
        return b""

    def remove(self, *, force):
        self.removed = force
