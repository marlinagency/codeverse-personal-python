"""SQL codegen module (PostgreSQL / PL-pgSQL dialect).

Concept-support summary — full mapping table with rationale lives in
docs/sql-concept-mapping.md:

FULL      function_def, return, if/elif/else, for, while, break, continue,
          try/except, list ops, dict ops (all inside PL/pgSQL blocks; top-
          level statements are wrapped in one DO block automatically)
EMULATED  class_def (composite type + standalone <Class>_<method> functions;
          inheritance rejected), import (extension whitelist), finally
          (block emitted after the guarded BEGIN/EXCEPTION/END)
"""

from __future__ import annotations

from codeverse_core.codegen.base import CodegenModule, CodegenResult
from codeverse_core.codegen.capabilities import ConceptSupport
from codeverse_core.codegen.sql_gen.emitters import SqlEmitter
from codeverse_core.concepts import UniversalConcept
from codeverse_core.uasl import nodes


class SQLCodegenModule(CodegenModule):
    @property
    def target_language(self) -> str:
        return "sql"

    def concept_support(self) -> dict[UniversalConcept, ConceptSupport]:
        support = {c: ConceptSupport.FULL for c in UniversalConcept}
        support[UniversalConcept.CLASS_DEF] = ConceptSupport.EMULATED
        support[UniversalConcept.IMPORT] = ConceptSupport.EMULATED
        support[UniversalConcept.FINALLY] = ConceptSupport.EMULATED
        return support

    def generate(self, program: nodes.Program) -> CodegenResult:
        emitter = SqlEmitter()
        source = emitter.emit_program(program)
        return CodegenResult(
            source_code=source,
            target_language="sql",
            entrypoint_hint=None,
            warnings=emitter.warnings,
        )
