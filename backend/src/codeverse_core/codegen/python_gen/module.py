from __future__ import annotations

from codeverse_core.codegen.base import CodegenModule, CodegenResult
from codeverse_core.codegen.capabilities import ConceptSupport
from codeverse_core.codegen.python_gen.emitters import PythonEmitter
from codeverse_core.concepts import UniversalConcept
from codeverse_core.uasl import nodes


class PythonCodegenModule(CodegenModule):
    @property
    def target_language(self) -> str:
        return "python"

    def concept_support(self) -> dict[UniversalConcept, ConceptSupport]:
        return {c: ConceptSupport.FULL for c in UniversalConcept}

    def generate(self, program: nodes.Program) -> CodegenResult:
        source = PythonEmitter().emit_program(program)
        return CodegenResult(
            source_code=source,
            target_language="python",
            entrypoint_hint=None,
        )
