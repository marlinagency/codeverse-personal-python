"""Codegen module registry.

Adding a new target language:
1. Implement CodegenModule in ``codegen/<lang>_gen/module.py``.
2. Register it in CODEGEN_REGISTRY below.
3. Add a sandbox runtime image under ``docker/runtimes/<lang>/`` and an
   entry in ``codeverse_sandbox.runtime_registry``.
Nothing else changes — lexer, parser, UASL, and API stay untouched.
"""

from __future__ import annotations

from codeverse_core.codegen.base import (
    CodegenError,
    CodegenModule,
    CodegenResult,
    CodegenWarning,
)
from codeverse_core.codegen.capabilities import ConceptSupport
from codeverse_core.codegen.python_gen.module import PythonCodegenModule
from codeverse_core.codegen.sql_gen.module import SQLCodegenModule

CODEGEN_REGISTRY: dict[str, type[CodegenModule]] = {
    "python": PythonCodegenModule,
    "sql": SQLCodegenModule,
}


def get_codegen_module(language: str) -> CodegenModule:
    try:
        return CODEGEN_REGISTRY[language.lower()]()
    except KeyError:
        supported = ", ".join(sorted(CODEGEN_REGISTRY))
        raise ValueError(
            f"unsupported target language: {language!r} (supported: {supported})"
        ) from None


__all__ = [
    "CODEGEN_REGISTRY",
    "get_codegen_module",
    "CodegenModule",
    "CodegenResult",
    "CodegenError",
    "CodegenWarning",
    "ConceptSupport",
]
