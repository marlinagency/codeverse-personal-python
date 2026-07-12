"""End-to-end compilation pipeline.

.cvl content + ThemeDictionary
    -> header parse -> lex (theme resolution) -> parse -> UASL
    -> semantic validation -> codegen
    -> CompilationResult

All diagnostics carry positions in FILE coordinates (header offset applied),
so editors can underline the exact line the user sees.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codeverse_core.codegen import get_codegen_module
from codeverse_core.codegen.base import CodegenError, CodegenResult
from codeverse_core.cvl.format import CvlDocument, CvlFormatError, parse_cvl
from codeverse_core.error_translation import ErrorContext, ErrorTranslator
from codeverse_core.lexer.errors import LexError
from codeverse_core.lexer.lexer import Lexer
from codeverse_core.parser.errors import ParseError
from codeverse_core.parser.parser import Parser
from codeverse_core.theme_mapping.dictionary import ThemeDictionary
from codeverse_core.uasl import nodes
from codeverse_core.uasl.validation import known_globals_for_language, validate_program


@dataclass(frozen=True)
class Diagnostic:
    message: str
    line: int  #: 1-based, in FILE coordinates
    col: int
    severity: str = "error"  # error | warning
    stage: str = "parse"  # format | lex | parse | semantic | codegen
    themed_message: str | None = None
    translation_provider: str | None = None


class CompilationError(Exception):
    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics = diagnostics
        first = diagnostics[0]
        super().__init__(f"{first.message} (line {first.line})")


@dataclass(frozen=True)
class CompilationResult:
    document: CvlDocument
    program: nodes.Program
    codegen: CodegenResult
    warnings: list[Diagnostic] = field(default_factory=list)


class CompilationPipeline:
    def __init__(self, error_translator: ErrorTranslator | None = None) -> None:
        self._error_translator = error_translator

    def compile(self, cvl_content: str, dictionary: ThemeDictionary) -> CompilationResult:
        try:
            document = parse_cvl(cvl_content)
        except CvlFormatError as exc:
            raise CompilationError(
                [self._diagnostic(exc.message, exc.line, 1, "format", dictionary)]
            ) from exc

        offset = document.body_line_offset

        try:
            tokens = Lexer(document.body, dictionary).tokenize()
        except LexError as exc:
            raise CompilationError(
                [self._diagnostic(exc.message, exc.line + offset, exc.col, "lex", dictionary)]
            ) from exc

        try:
            program = Parser(tokens, dictionary).parse_program()
        except ParseError as exc:
            raise CompilationError(
                [self._diagnostic(exc.message, exc.line + offset, exc.col, "parse", dictionary)]
            ) from exc

        if not program.body:
            raise CompilationError(
                [
                    self._diagnostic(
                        "source is empty — write at least one statement "
                        "after the '---' separator (comments and blank lines do not count)",
                        offset + 1,
                        1,
                        "parse",
                        dictionary,
                    )
                ]
            )

        semantic_errors = validate_program(
            program, known_globals_for_language(document.language)
        )
        if semantic_errors:
            raise CompilationError(
                [
                    self._diagnostic(e.message, e.line + offset, e.col, "semantic", dictionary)
                    for e in semantic_errors
                ]
            )

        module = get_codegen_module(document.language)
        try:
            result = module.generate(program)
        except CodegenError as exc:
            raise CompilationError(
                [self._diagnostic(exc.message, exc.line + offset, exc.col, "codegen", dictionary)]
            ) from exc

        warnings = [
            self._diagnostic(
                w.message,
                w.line + offset,
                w.col,
                "codegen",
                dictionary,
                severity="warning",
            )
            for w in result.warnings
        ]
        return CompilationResult(
            document=document, program=program, codegen=result, warnings=warnings
        )

    def _diagnostic(
        self,
        message: str,
        line: int,
        col: int,
        stage: str,
        dictionary: ThemeDictionary,
        severity: str = "error",
    ) -> Diagnostic:
        if self._error_translator is None:
            return Diagnostic(message, line, col, severity=severity, stage=stage)

        translated = self._error_translator.translate(
            ErrorContext(
                message=message,
                line=line,
                col=col,
                stage=stage,
                severity=severity,
            ),
            dictionary,
        )
        return Diagnostic(
            message=message,
            line=line,
            col=col,
            severity=severity,
            stage=stage,
            themed_message=translated.themed_message,
            translation_provider=translated.provider_name,
        )
