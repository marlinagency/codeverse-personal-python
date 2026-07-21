from __future__ import annotations

import pytest

from codeverse_core.cvl.format import CvlFormatError, parse_cvl


VALID = """@theme: valorant
@language: python
@version: 1
---
x = 1
"""


def test_valid_document():
    doc = parse_cvl(VALID)
    assert doc.theme == "valorant"
    assert doc.language == "python"
    assert doc.version == 1
    assert doc.body.strip() == "x = 1"
    assert doc.body_line_offset == 4


def test_free_text_theme_with_spaces():
    doc = parse_cvl(
        "@theme: uzayda karadelikleri seven ve bilen biri\n"
        "@language: sql\n@version: 1\n---\nx = 1\n"
    )
    assert doc.theme == "uzayda karadelikleri seven ve bilen biri"


def test_missing_separator():
    with pytest.raises(CvlFormatError, match="---"):
        parse_cvl("@theme: a\n@language: python\n@version: 1\nx = 1")


def test_missing_header_key():
    with pytest.raises(CvlFormatError, match="@language"):
        parse_cvl("@theme: a\n@version: 1\n---\nx = 1")


def test_unknown_header_key():
    with pytest.raises(CvlFormatError, match="unknown"):
        parse_cvl("@theme: a\n@mode: x\n@language: python\n@version: 1\n---\n")


def test_duplicate_header_key():
    with pytest.raises(CvlFormatError, match="twice"):
        parse_cvl("@theme: a\n@theme: b\n@language: python\n@version: 1\n---\n")


def test_bad_version():
    with pytest.raises(CvlFormatError, match="integer"):
        parse_cvl("@theme: a\n@language: python\n@version: bir\n---\n")


def test_unsupported_version():
    with pytest.raises(CvlFormatError, match="version"):
        parse_cvl("@theme: a\n@language: python\n@version: 99\n---\n")


def test_headerless_without_default_still_strict():
    # No default_language passed: header-less code is a hard error as before.
    with pytest.raises(CvlFormatError, match="@key: value"):
        parse_cvl("sayilar = [1, 2, 3]\n")


def test_headerless_with_default_synthesizes_header():
    doc = parse_cvl(
        "sayilar = [1, 2, 3]\nradiate(sayilar)\n",
        default_theme="valorant",
        default_language="python",
    )
    assert doc.language == "python"
    assert doc.theme == "valorant"
    assert doc.version == 1
    # whole content is the body, and line numbers are NOT shifted
    assert doc.body_line_offset == 0
    assert doc.body.splitlines()[0] == "sayilar = [1, 2, 3]"


def test_explicit_header_wins_over_default():
    # A real header is always honored even when a default is available.
    doc = parse_cvl(VALID, default_language="sql")
    assert doc.language == "python"
    assert doc.body_line_offset == 4


def test_partial_header_is_not_treated_as_headerless():
    # First real line starts with '@' -> user attempted a header -> strict error.
    with pytest.raises(CvlFormatError, match="---"):
        parse_cvl(
            "@theme: a\n@language: python\n@version: 1\nx = 1",
            default_language="python",
        )
