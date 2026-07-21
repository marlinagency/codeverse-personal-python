"""WebSocket execution endpoint.

Protocol: client sends one JSON message shaped like ``ExecuteRequest``
(``project_file_id`` OR ``source_content`` + ``theme_dictionary_id``). The
server replies with one or more JSON frames:

  {"type": "diagnostic", ...}   - compile-time error (no sandbox run happened)
  {"type": "result", ...}       - final execution result (ExecutionRunOut shape)
  {"type": "error", "detail": "..."} - infrastructure error (e.g. no sandbox)

Note: DockerSandboxRunner currently waits for the container to finish before
returning output (no incremental log streaming), so this endpoint sends the
full result in one frame rather than a token-by-token stream. Incremental
``docker logs --follow`` streaming is a natural follow-up once this shape is
validated end-to-end.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from codeverse_api.dependencies import get_compilation_pipeline, get_db, get_sandbox_runner
from codeverse_api.repositories.execution_repository import ExecutionRepository
from codeverse_api.routers.compile import resolve_source_and_dictionary
from codeverse_api.schemas.execution import ExecuteRequest
from codeverse_api.security.auth import decode_access_token
from codeverse_api.config import get_settings
from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from codeverse_sandbox.docker_runner import DockerSandboxError, DockerSandboxRunner
from codeverse_sandbox.limits import SandboxLimits

router = APIRouter(tags=["ws"])


@router.websocket("/ws/execute")
async def ws_execute(
    websocket: WebSocket,
    db: Session = Depends(get_db),
    pipeline: CompilationPipeline = Depends(get_compilation_pipeline),
    sandbox: DockerSandboxRunner | None = Depends(get_sandbox_runner),
) -> None:
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.send_json({"type": "error", "detail": "missing token query param"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        user_id = decode_access_token(token, get_settings())
    except Exception:  # noqa: BLE001 - any auth failure closes the socket
        await websocket.send_json({"type": "error", "detail": "invalid token"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = await websocket.receive_json()
        body = ExecuteRequest.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        await websocket.send_json({"type": "error", "detail": f"invalid request: {exc}"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except WebSocketDisconnect:
        return

    if sandbox is None:
        await websocket.send_json(
            {"type": "error", "detail": "sandbox unavailable (Docker Desktop required)"}
        )
        await websocket.close()
        return

    try:
        source, dictionary, default_language = resolve_source_and_dictionary(db, user_id, body)
    except Exception as exc:  # noqa: BLE001 - surface as a ws error frame
        await websocket.send_json({"type": "error", "detail": str(exc)})
        await websocket.close()
        return

    started_at = datetime.now(timezone.utc)
    try:
        compiled = pipeline.compile(source, dictionary, default_language=default_language)
    except CompilationError as exc:
        first = exc.diagnostics[0]
        await websocket.send_json(
            {
                "type": "diagnostic",
                "message": first.message,
                "themed_message": first.themed_message,
                "line": first.line,
                "col": first.col,
                "stage": first.stage,
            }
        )
        await websocket.close()
        return

    t0 = time.monotonic()
    try:
        result = sandbox.run(
            language=compiled.codegen.target_language,
            source_code=compiled.codegen.source_code,
            limits=SandboxLimits(),
        )
    except DockerSandboxError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        await websocket.close()
        return

    duration_ms = int((time.monotonic() - t0) * 1000)

    run_id = uuid.uuid4()
    if body.project_file_id is not None:
        run = ExecutionRepository(db).create(
            project_file_id=body.project_file_id,
            user_id=user_id,
            generated_code=compiled.codegen.source_code,
            status=result.status,
            stdout=result.stdout,
            stderr_raw=result.stderr or None,
            duration_ms=duration_ms,
            started_at=started_at,
        )
        db.commit()
        run_id = run.id

    await websocket.send_json(
        {
            "type": "result",
            "id": str(run_id),
            "status": result.status,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": duration_ms,
        }
    )
    await websocket.close()
