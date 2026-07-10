from __future__ import annotations

from dataclasses import dataclass


class SandboxRuntimeNotFoundError(ValueError):
    """Requested target language has no sandbox runtime registered."""


@dataclass(frozen=True)
class RuntimeSpec:
    language: str
    image: str
    source_filename: str
    command: tuple[str, ...]
    #: container user. Must exist in the image's /etc/passwd when the runtime
    #: needs user lookup (initdb does); always non-root.
    user: str


RUNTIME_REGISTRY: dict[str, RuntimeSpec] = {
    "python": RuntimeSpec(
        language="python",
        image="codeverse-python-runtime:3.12",
        source_filename="main.py",
        command=("python", "/workspace/main.py"),
        user="1000:1000",
    ),
    "sql": RuntimeSpec(
        language="sql",
        image="codeverse-sql-runtime:16",
        source_filename="main.sql",
        command=("/usr/local/bin/run-codeverse-sql", "/workspace/main.sql"),
        # postgres:16-alpine defines 'postgres' (uid 70); initdb refuses to
        # run under a uid missing from /etc/passwd, so "1000:1000" would fail
        user="postgres",
    ),
}


def get_runtime(language: str) -> RuntimeSpec:
    key = language.lower()
    try:
        return RUNTIME_REGISTRY[key]
    except KeyError:
        supported = ", ".join(sorted(RUNTIME_REGISTRY))
        raise SandboxRuntimeNotFoundError(
            f"unsupported sandbox language: {language!r} (supported: {supported})"
        ) from None
