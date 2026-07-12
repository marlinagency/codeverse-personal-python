"""Hand-written lexer for the themed DSL.

Indentation-based block structure (Python-style INDENT/DEDENT), Unicode
identifiers, and theme resolution at tokenization time: every identifier is
looked up in the active ThemeDictionary; structural keywords become keyword
tokens, builtins/methods stay NAME tokens with a canonical ``resolved_text``.
"""

from __future__ import annotations

import re

from codeverse_core.concepts import ConceptKind
from codeverse_core.lexer.errors import LexError
from codeverse_core.lexer.tokens import KEYWORD_TOKEN_TYPES, Token, TokenType
from codeverse_core.theme_mapping.dictionary import ThemeDictionary

_IDENT_RE = re.compile(r"[^\W\d]\w*", re.UNICODE)
_NUMBER_RE = re.compile(r"\d+(\.\d+)?")

_TWO_CHAR_OPS: dict[str, TokenType] = {
    "==": TokenType.EQ,
    "!=": TokenType.NE,
    "<=": TokenType.LE,
    ">=": TokenType.GE,
    "**": TokenType.DOUBLESTAR,
    ":=": TokenType.WALRUS,
}

_ONE_CHAR_OPS: dict[str, TokenType] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "=": TokenType.ASSIGN,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    ",": TokenType.COMMA,
    ":": TokenType.COLON,
    ".": TokenType.DOT,
    "@": TokenType.AT,
}

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "0": "\0"}


class Lexer:
    def __init__(self, source: str, dictionary: ThemeDictionary) -> None:
        self._source = source
        self._dictionary = dictionary

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        indent_stack = [0]
        # bracket depth > 0 suppresses NEWLINE/indent handling (implicit
        # line joining inside (), [], {})
        depth = 0

        lines = self._source.split("\n")
        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.rstrip("\r")

            if depth == 0:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue  # blank / comment-only lines are invisible

                indent = _measure_indent(line, line_no)
                if indent > indent_stack[-1]:
                    indent_stack.append(indent)
                    tokens.append(Token(TokenType.INDENT, "", "", line_no, 1))
                else:
                    while indent < indent_stack[-1]:
                        indent_stack.pop()
                        tokens.append(Token(TokenType.DEDENT, "", "", line_no, 1))
                    if indent != indent_stack[-1]:
                        raise LexError(
                            "inconsistent indentation: this line's indent matches no "
                            "enclosing block",
                            line_no,
                            indent + 1,
                        )

            depth = self._lex_line(line, line_no, tokens, depth)

            if depth == 0 and tokens and tokens[-1].type not in (
                TokenType.NEWLINE,
                TokenType.INDENT,
            ):
                tokens.append(Token(TokenType.NEWLINE, "", "", line_no, len(line) + 1))

        if depth > 0:
            raise LexError("unclosed parenthesis/bracket", len(lines), 1)

        last_line = len(lines)
        while len(indent_stack) > 1:
            indent_stack.pop()
            tokens.append(Token(TokenType.DEDENT, "", "", last_line, 1))
        tokens.append(Token(TokenType.EOF, "", "", last_line, 1))
        return tokens

    def _lex_line(self, line: str, line_no: int, out: list[Token], depth: int) -> int:
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]

            if ch in " \t":
                i += 1
                continue
            if ch == "#":
                break  # comment to end of line

            col = i + 1

            if ch in "\"'":
                text, value, i = self._lex_string(line, i, line_no)
                out.append(Token(TokenType.STRING, text, value, line_no, col))
                continue

            m = _NUMBER_RE.match(line, i)
            if m:
                text = m.group()
                out.append(Token(TokenType.NUMBER, text, text, line_no, col))
                i = m.end()
                continue

            m = _IDENT_RE.match(line, i)
            if m:
                text = m.group()
                out.append(self._make_ident_token(text, line_no, col))
                i = m.end()
                continue

            two = line[i : i + 2]
            if two in _TWO_CHAR_OPS:
                out.append(Token(_TWO_CHAR_OPS[two], two, two, line_no, col))
                i += 2
                continue

            if ch in _ONE_CHAR_OPS:
                tt = _ONE_CHAR_OPS[ch]
                out.append(Token(tt, ch, ch, line_no, col))
                if tt in (TokenType.LPAREN, TokenType.LBRACKET, TokenType.LBRACE):
                    depth += 1
                elif tt in (TokenType.RPAREN, TokenType.RBRACKET, TokenType.RBRACE):
                    if depth == 0:
                        raise LexError(f"unmatched {ch!r}", line_no, col)
                    depth -= 1
                i += 1
                continue

            raise LexError(f"unrecognized character: {ch!r}", line_no, col)

        return depth

    def _make_ident_token(self, text: str, line: int, col: int) -> Token:
        concept = self._dictionary.resolve(text)
        if concept is None:
            return Token(TokenType.NAME, text, text, line, col)
        kind = getattr(concept, "kind", None)
        if kind is ConceptKind.KEYWORD:
            return Token(
                KEYWORD_TOKEN_TYPES[concept], text, concept.canonical, line, col, concept
            )
        canonical = getattr(concept, "canonical", None)
        if canonical is None:
            return Token(TokenType.NAME, text, text, line, col)
        if kind in (ConceptKind.BUILTIN, ConceptKind.METHOD):
            return Token(TokenType.NAME, text, canonical, line, col, concept)
        # builtins and methods resolve to canonical names but stay NAMEs
        return Token(TokenType.NAME, text, canonical, line, col)

    def _lex_string(self, line: str, start: int, line_no: int) -> tuple[str, str, int]:
        quote = line[start]
        i = start + 1
        value_chars: list[str] = []
        while i < len(line):
            ch = line[i]
            if ch == "\\":
                if i + 1 >= len(line):
                    raise LexError("incomplete escape sequence at end of line", line_no, i + 1)
                esc = line[i + 1]
                value_chars.append(_ESCAPES.get(esc, esc))
                i += 2
                continue
            if ch == quote:
                return line[start : i + 1], "".join(value_chars), i + 1
            value_chars.append(ch)
            i += 1
        raise LexError("unclosed string", line_no, start + 1)


def _measure_indent(line: str, line_no: int) -> int:
    indent = 0
    for ch in line:
        if ch == " ":
            indent += 1
        elif ch == "\t":
            raise LexError(
                "tabs cannot be used for indentation, use spaces", line_no, indent + 1
            )
        else:
            break
    return indent
