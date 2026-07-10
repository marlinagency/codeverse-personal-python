"""Token model for the themed DSL.

Every token carries BOTH its themed spelling (exactly what the user typed)
and its resolved canonical form. Error messages and the translation panel
need the themed text; the parser and codegen work with the resolved text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from codeverse_core.concepts import UniversalConcept


class TokenType(Enum):
    # structure
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()
    EOF = auto()

    # atoms
    NAME = auto()
    NUMBER = auto()
    STRING = auto()

    # keywords (resolved from themed tokens)
    KW_FUNC = auto()
    KW_RETURN = auto()
    KW_IF = auto()
    KW_ELIF = auto()
    KW_ELSE = auto()
    KW_FOR = auto()
    KW_IN = auto()
    KW_WHILE = auto()
    KW_BREAK = auto()
    KW_CONTINUE = auto()
    KW_CLASS = auto()
    KW_IMPORT = auto()
    KW_TRY = auto()
    KW_EXCEPT = auto()
    KW_FINALLY = auto()
    KW_AND = auto()
    KW_OR = auto()
    KW_NOT = auto()
    KW_TRUE = auto()
    KW_FALSE = auto()
    KW_NONE = auto()
    KW_LAMBDA = auto()
    KW_GLOBAL = auto()
    KW_NONLOCAL = auto()
    KW_DEL = auto()
    KW_ASSERT = auto()
    KW_RAISE = auto()

    # operators / punctuation
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    DOUBLESTAR = auto()  # **
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()        # ==
    NE = auto()        # !=
    LT = auto()
    LE = auto()
    GT = auto()
    GE = auto()
    ASSIGN = auto()    # =
    WALRUS = auto()    # :=
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    COLON = auto()
    DOT = auto()
    AT = auto()        # @ (decorator)

    # f-string parts, modeled after CPython 3.12's tokenizer (PEP 701 style):
    # f"a{b}c" -> FSTRING_START("f\"") FSTRING_MIDDLE("a") FSTRING_EXPR_START("{")
    #             <tokens for b> FSTRING_EXPR_END("}") FSTRING_MIDDLE("c") FSTRING_END("\"")
    FSTRING_START = auto()
    FSTRING_MIDDLE = auto()
    FSTRING_EXPR_START = auto()
    FSTRING_EXPR_END = auto()
    FSTRING_END = auto()


#: keyword concept -> token type
KEYWORD_TOKEN_TYPES: dict[UniversalConcept, TokenType] = {
    UniversalConcept.FUNCTION_DEF: TokenType.KW_FUNC,
    UniversalConcept.RETURN: TokenType.KW_RETURN,
    UniversalConcept.IF: TokenType.KW_IF,
    UniversalConcept.ELIF: TokenType.KW_ELIF,
    UniversalConcept.ELSE: TokenType.KW_ELSE,
    UniversalConcept.FOR: TokenType.KW_FOR,
    UniversalConcept.IN: TokenType.KW_IN,
    UniversalConcept.WHILE: TokenType.KW_WHILE,
    UniversalConcept.BREAK: TokenType.KW_BREAK,
    UniversalConcept.CONTINUE: TokenType.KW_CONTINUE,
    UniversalConcept.CLASS_DEF: TokenType.KW_CLASS,
    UniversalConcept.IMPORT: TokenType.KW_IMPORT,
    UniversalConcept.TRY: TokenType.KW_TRY,
    UniversalConcept.EXCEPT: TokenType.KW_EXCEPT,
    UniversalConcept.FINALLY: TokenType.KW_FINALLY,
    UniversalConcept.AND: TokenType.KW_AND,
    UniversalConcept.OR: TokenType.KW_OR,
    UniversalConcept.NOT: TokenType.KW_NOT,
    UniversalConcept.TRUE: TokenType.KW_TRUE,
    UniversalConcept.FALSE: TokenType.KW_FALSE,
    UniversalConcept.NONE: TokenType.KW_NONE,
    UniversalConcept.LAMBDA: TokenType.KW_LAMBDA,
    UniversalConcept.GLOBAL: TokenType.KW_GLOBAL,
    UniversalConcept.NONLOCAL: TokenType.KW_NONLOCAL,
    UniversalConcept.DEL: TokenType.KW_DEL,
    UniversalConcept.ASSERT: TokenType.KW_ASSERT,
    UniversalConcept.RAISE: TokenType.KW_RAISE,
}


@dataclass(frozen=True)
class Token:
    type: TokenType
    themed_text: str      #: exactly what the user typed
    resolved_text: str    #: canonical form (== themed_text for plain names)
    line: int             #: 1-based
    col: int              #: 1-based
    concept: UniversalConcept | None = None

    def __repr__(self) -> str:  # compact, useful in test failures
        if self.themed_text == self.resolved_text:
            return f"<{self.type.name} {self.themed_text!r} @{self.line}:{self.col}>"
        return (
            f"<{self.type.name} {self.themed_text!r}->{self.resolved_text!r} "
            f"@{self.line}:{self.col}>"
        )
