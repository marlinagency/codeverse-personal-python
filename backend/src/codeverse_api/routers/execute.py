from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from codeverse_api.dependencies import get_compilation_pipeline, get_db, get_sandbox_runner
from codeverse_api.repositories.execution_repository import ExecutionRepository
from codeverse_api.routers.compile import resolve_source_and_dictionary
from codeverse_api.schemas.execution import ExecutionRunOut, ExecuteRequest
from codeverse_api.security.auth import get_current_user_id
from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from codeverse_sandbox.docker_runner import (
    DockerSandboxImageMissing,
    DockerSandboxRunner,
    DockerSandboxUnavailable,
)
from codeverse_sandbox.limits import SandboxLimits

router = APIRouter(tags=["execute"])


@router.post("/execute", response_model=ExecutionRunOut)
def execute_source(
    body: ExecuteRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    pipeline: CompilationPipeline = Depends(get_compilation_pipeline),
    sandbox: DockerSandboxRunner | None = Depends(get_sandbox_runner),
) -> ExecutionRunOut:
    source, dictionary = resolve_source_and_dictionary(db, user_id, body)
    started_at = datetime.now(timezone.utc)

    try:
        compiled = pipeline.compile(source, dictionary)
    except CompilationError as exc:
        first = exc.diagnostics[0]
        return _persist_or_synthesize(
            db,
            body.project_file_id,
            user_id,
            generated_code="",
            status_="codegen_error" if first.stage == "codegen" else "parse_error",
            stdout=None,
            stderr_raw=first.message,
            error_message_themed=first.themed_message,
            duration_ms=0,
            started_at=started_at,
        )

    limits = SandboxLimits()
    if sandbox is None:
        local = run_local_python_demo(
            compiled.codegen.target_language,
            compiled.codegen.source_code,
            limits,
        )
        return _persist_or_synthesize(
            db,
            body.project_file_id,
            user_id,
            generated_code=compiled.codegen.source_code,
            status_=local["status"],
            stdout=local["stdout"],
            stderr_raw=local["stderr_raw"],
            error_message_themed=None,
            duration_ms=local["duration_ms"],
            started_at=started_at,
        )

    t0 = time.monotonic()
    try:
        result = sandbox.run(
            language=compiled.codegen.target_language,
            source_code=compiled.codegen.source_code,
            limits=limits,
        )
    except DockerSandboxImageMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"sandbox runtime image missing: {exc}",
        ) from exc
    except DockerSandboxUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker is unavailable",
        ) from exc

    duration_ms = int((time.monotonic() - t0) * 1000)
    return _persist_or_synthesize(
        db,
        body.project_file_id,
        user_id,
        generated_code=compiled.codegen.source_code,
        status_=result.status,
        stdout=result.stdout,
        stderr_raw=result.stderr or None,
        error_message_themed=None,
        duration_ms=duration_ms,
        started_at=started_at,
    )


def run_local_python_demo(
    target_language: str,
    source_code: str,
    limits: SandboxLimits,
) -> dict[str, str | int | None]:
    """Subprocess-based Python runner used when Docker is unavailable.

    Public because the learning router's /practice/run reuses the same
    compile-then-run fallback for code exercises."""
    if target_language != "python":
        return {
            "status": "sandbox_error",
            "stdout": None,
            "stderr_raw": "Docker sandbox is unavailable for this target language.",
            "duration_ms": 0,
        }

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="codeverse-local-demo-") as tmp:
        script_path = Path(tmp) / "main.py"
        script_path.write_text(source_code, encoding="utf-8", newline="\n")
        try:
            completed = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=limits.timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "status": "timeout",
                "stdout": exc.stdout or None,
                "stderr_raw": exc.stderr or "Local demo runner timed out.",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

    return {
        "status": "success" if completed.returncode == 0 else "runtime_error",
        "stdout": completed.stdout or None,
        "stderr_raw": completed.stderr or None,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def _persist_or_synthesize(
    db: Session,
    project_file_id: uuid.UUID | None,
    user_id: uuid.UUID,
    *,
    generated_code: str,
    status_: str,
    stdout: str | None,
    stderr_raw: str | None,
    error_message_themed: str | None,
    duration_ms: int,
    started_at: datetime,
) -> ExecutionRunOut:
    if project_file_id is None:
        return ExecutionRunOut(
            id=uuid.uuid4(),
            status=status_,
            stdout=stdout,
            stderr_raw=stderr_raw,
            error_message_themed=error_message_themed,
            duration_ms=duration_ms,
            created_at=datetime.now(timezone.utc),
        )

    run = ExecutionRepository(db).create(
        project_file_id=project_file_id,
        user_id=user_id,
        generated_code=generated_code,
        status=status_,
        stdout=stdout,
        stderr_raw=stderr_raw,
        error_message_themed=error_message_themed,
        duration_ms=duration_ms,
        started_at=started_at,
    )
    db.commit()
    return ExecutionRunOut.model_validate(run)
