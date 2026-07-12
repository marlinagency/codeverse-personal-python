"""Line-level evidence showing how Personal Python resolves to canonical Python."""

from __future__ import annotations

from dataclasses import dataclass

from codeverse_core.cvl.format import CvlFormatError, parse_cvl
from codeverse_core.lexer.errors import LexError
from codeverse_core.lexer.lexer import Lexer
from codeverse_core.lexer.tokens import Token, TokenType
from codeverse_core.theme_mapping.dictionary import ThemeDictionary


@dataclass(frozen=True)
class TokenReplacement:
    personal_token: str
    python_token: str
    col: int


@dataclass(frozen=True)
class TranslationTraceLine:
    line: int
    personal_source: str
    python_source: str
    replacements: tuple[TokenReplacement, ...]


_PYTHON_KEYWORDS = {
    TokenType.KW_FUNC: "def",
    TokenType.KW_CLASS: "class",
    TokenType.KW_TRUE: "True",
    TokenType.KW_FALSE: "False",
    TokenType.KW_NONE: "None",
}


def _python_token(token: Token) -> str | None:
    if token.type is TokenType.NAME:
        return token.resolved_text
    if token.type.name.startswith("KW_"):
        return _PYTHON_KEYWORDS.get(
            token.type,
            token.type.name.removeprefix("KW_").lower(),
        )
    return None


def build_translation_trace(
    cvl_content: str,
    dictionary: ThemeDictionary,
) -> tuple[TranslationTraceLine, ...]:
    """Resolve only lexer-recognized tokens, preserving strings and comments."""
    try:
        document = parse_cvl(cvl_content)
        tokens = Lexer(document.body, dictionary).tokenize()
    except (CvlFormatError, LexError):
        return ()

    source_lines = document.body.split("\n")
    replacements_by_line: dict[int, list[TokenReplacement]] = {}
    for token in tokens:
        python_token = _python_token(token)
        if not python_token or not token.themed_text or token.themed_text == python_token:
            continue
        replacements_by_line.setdefault(token.line, []).append(
            TokenReplacement(
                personal_token=token.themed_text,
                python_token=python_token,
                col=token.col,
            )
        )

    trace: list[TranslationTraceLine] = []
    for body_line, replacements in sorted(replacements_by_line.items()):
        if body_line < 1 or body_line > len(source_lines):
            continue
        personal_source = source_lines[body_line - 1]
        python_source = personal_source
        for replacement in sorted(replacements, key=lambda item: item.col, reverse=True):
            start = replacement.col - 1
            end = start + len(replacement.personal_token)
            python_source = (
                python_source[:start]
                + replacement.python_token
                + python_source[end:]
            )
        trace.append(
            TranslationTraceLine(
                line=body_line + document.body_line_offset,
                personal_source=personal_source,
                python_source=python_source,
                replacements=tuple(replacements),
            )
        )
    return tuple(trace)
