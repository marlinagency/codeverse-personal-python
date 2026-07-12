from __future__ import annotations

import pytest

from codeverse_core.lexer.errors import LexError
from codeverse_core.lexer.lexer import Lexer
from codeverse_core.lexer.tokens import TokenType
from codeverse_core.theme_mapping.dictionary import CANONICAL_DICTIONARY


def _types(source, dictionary=CANONICAL_DICTIONARY):
    return [t.type for t in Lexer(source, dictionary).tokenize()]


def test_simple_assignment():
    types = _types("x = 5")
    assert types == [
        TokenType.NAME,
        TokenType.ASSIGN,
        TokenType.NUMBER,
        TokenType.NEWLINE,
        TokenType.EOF,
    ]


def test_themed_keyword_resolution(space_dictionary):
    tokens = Lexer("event_horizon x > 1:\n    radiate(x)", space_dictionary).tokenize()
    assert tokens[0].type is TokenType.KW_IF
    assert tokens[0].themed_text == "event_horizon"
    assert tokens[0].resolved_text == "if"
    # builtin 'radiate' -> canonical 'print', stays a NAME
    radiate = next(t for t in tokens if t.themed_text == "radiate")
    assert radiate.type is TokenType.NAME
    assert radiate.resolved_text == "print"


def test_indent_dedent():
    source = "if x:\n    y = 1\n    z = 2\nw = 3"
    types = _types(source)
    assert TokenType.INDENT in types
    assert TokenType.DEDENT in types
    # INDENT comes right after the block-opening NEWLINE
    i = types.index(TokenType.INDENT)
    assert types[i - 1] is TokenType.NEWLINE


def test_nested_dedents_emitted():
    source = "if a:\n    if b:\n        x = 1\ny = 2"
    types = _types(source)
    assert types.count(TokenType.INDENT) == 2
    assert types.count(TokenType.DEDENT) == 2


def test_string_escapes():
    tokens = Lexer('s = "a\\nb\\"c"', CANONICAL_DICTIONARY).tokenize()
    s = tokens[2]
    assert s.type is TokenType.STRING
    assert s.resolved_text == 'a\nb"c'


def test_comments_and_blank_lines_ignored():
    source = "# yorum\n\nx = 1  # satır sonu yorumu\n"
    types = _types(source)
    assert types == [
        TokenType.NAME,
        TokenType.ASSIGN,
        TokenType.NUMBER,
        TokenType.NEWLINE,
        TokenType.EOF,
    ]


def test_implicit_line_joining_in_brackets():
    source = "xs = [1,\n      2,\n      3]"
    types = _types(source)
    assert TokenType.INDENT not in types
    assert types.count(TokenType.NEWLINE) == 1


def test_unicode_identifiers():
    tokens = Lexer("sonuçlar = 5", CANONICAL_DICTIONARY).tokenize()
    assert tokens[0].themed_text == "sonuçlar"


def test_tab_indent_rejected():
    with pytest.raises(LexError, match="tab"):
        Lexer("if x:\n\ty = 1", CANONICAL_DICTIONARY).tokenize()


def test_unterminated_string_rejected():
    with pytest.raises(LexError, match="string"):
        Lexer('s = "acik', CANONICAL_DICTIONARY).tokenize()


def test_misaligned_indent_rejected():
    with pytest.raises(LexError, match="indentation"):
        Lexer("if x:\n    y = 1\n  z = 2", CANONICAL_DICTIONARY).tokenize()


def test_positions_are_one_based():
    tokens = Lexer("x = 1", CANONICAL_DICTIONARY).tokenize()
    assert (tokens[0].line, tokens[0].col) == (1, 1)
    assert (tokens[1].line, tokens[1].col) == (1, 3)
