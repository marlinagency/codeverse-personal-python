from __future__ import annotations

import concurrent.futures
import os
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import docker
from docker.errors import DockerException, ImageNotFound

from codeverse_sandbox.limits import SandboxLimits
from codeverse_sandbox.runtime_registry import get_runtime


class DockerSandboxError(RuntimeError):
    """Base class for sandbox infrastructure errors."""


class DockerSandboxUnavailable(DockerSandboxError):
    """Docker is not installed, not running, or not reachable."""


class DockerSandboxImageMissing(DockerSandboxError):
    """A registered runtime image has not been built locally."""


@dataclass(frozen=True)
class SandboxRunResult:
    language: str
    status: str  # success | runtime_error | timeout
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


class DockerSandboxRunner:
    """Run generated source code inside a locked-down Docker container."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client if client is not None else docker.from_env()

    def run(
        self,
        *,
        language: str,
        source_code: str,
        limits: SandboxLimits | None = None,
    ) -> SandboxRunResult:
        runtime = get_runtime(language)
        effective_limits = limits or SandboxLimits()
        started_at = time.monotonic()
        container = None

        with _temporary_workspace() as host_workspace:
            source_path = host_workspace / runtime.source_filename
            source_path.write_text(source_code, encoding="utf-8", newline="\n")

            try:
                container = self._client.containers.run(
                    image=runtime.image,
                    command=list(runtime.command),
                    detach=True,
                    volumes={
                        str(host_workspace): {
                            "bind": "/workspace",
                            "mode": "ro",
                        }
                    },
                    working_dir="/workspace",
                    network_disabled=True,
                    user=runtime.user,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges:true"],
                    mem_limit=effective_limits.memory,
                    nano_cpus=effective_limits.nano_cpus,
                    pids_limit=effective_limits.pids_limit,
                    stdout=True,
                    stderr=True,
                    remove=False,
                )
            except ImageNotFound as exc:
                raise DockerSandboxImageMissing(
                    f"sandbox runtime image is missing: {runtime.image}"
                ) from exc
            except DockerException as exc:
                raise DockerSandboxUnavailable("Docker is not available") from exc

            try:
                wait_result, timed_out = self._wait_for_container(
                    container,
                    effective_limits.timeout_seconds,
                )
                exit_code = None if timed_out else int(wait_result.get("StatusCode", 1))
                stdout = self._read_logs(container, stdout=True)
                stderr = self._read_logs(container, stdout=False)
            finally:
                try:
                    container.remove(force=True)
                except DockerException:
                    pass

        duration_ms = int((time.monotonic() - started_at) * 1000)
        status = "success"
        if timed_out:
            status = "timeout"
        elif exit_code != 0:
            status = "runtime_error"

        return SandboxRunResult(
            language=runtime.language,
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
        )

    def _wait_for_container(self, container: Any, timeout_seconds: float) -> tuple[dict[str, Any], bool]:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(container.wait)
        try:
            return future.result(timeout=timeout_seconds), False
        except concurrent.futures.TimeoutError:
            try:
                container.kill()
            except DockerException:
                pass
            try:
                result = future.result(timeout=2)
            except concurrent.futures.TimeoutError:
                result = {"StatusCode": 124}
            return result, True
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _read_logs(self, container: Any, *, stdout: bool) -> str:
        raw = container.logs(stdout=stdout, stderr=not stdout)
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)


@contextmanager
def _temporary_workspace() -> Iterator[Path]:
    """Create a writable workspace without Windows TemporaryDirectory ACL issues.

    When the backend itself runs inside a container talking to the HOST docker
    daemon, bind-mount paths are resolved on the host — so the workspace must
    live on a directory mounted into the backend at the SAME path it has on
    the host. CODEVERSE_SANDBOX_WORKSPACE_DIR names that shared directory;
    unset (local dev on the host) falls back to the system temp dir.
    """
    base = Path(
        os.environ.get("CODEVERSE_SANDBOX_WORKSPACE_DIR") or tempfile.gettempdir()
    ).resolve()
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"codeverse-sandbox-{uuid.uuid4().hex}"
    path.mkdir(parents=False, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
