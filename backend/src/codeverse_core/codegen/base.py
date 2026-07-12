from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from codeverse_core.codegen.capabilities import ConceptSupport
from codeverse_core.concepts import UniversalConcept
from codeverse_core.uasl import nodes


@dataclass(frozen=True)
class CodegenResult:
    source_code: str
    target_language: str
    #: e.g. a function name to invoke, or None for a self-running script
    entrypoint_hint: str | None = None
    warnings: list["CodegenWarning"] = field(default_factory=list)


@dataclass(frozen=True)
class CodegenWarning:
    message: str
    line: int
    col: int


class CodegenError(Exception):
    """A UASL construct cannot be expressed in the target language."""

    def __init__(self, message: str, node: nodes.Node) -> None:
        self.message = message
        self.line = node.pos.line
        self.col = node.pos.col
        super().__init__(f"{message} (line {self.line}, col {self.col})")


class CodegenModule(ABC):
    """One target language's code generator. Stateless across calls."""

    @property
    @abstractmethod
    def target_language(self) -> str: ...

    @abstractmethod
    def concept_support(self) -> dict[UniversalConcept, ConceptSupport]: ...

    @abstractmethod
    def generate(self, program: nodes.Program) -> CodegenResult:
        """UASL -> real, runnable target-language source.

        Raises CodegenError (with the offending node's position) when the
        program uses a construct this language cannot express.
        """
