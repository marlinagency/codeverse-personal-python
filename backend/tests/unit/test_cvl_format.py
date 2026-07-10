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
    with pytest.raises(CvlFormatError, match="bilinmeyen"):
        parse_cvl("@theme: a\n@mode: x\n@language: python\n@version: 1\n---\n")


def test_duplicate_header_key():
    with pytest.raises(CvlFormatError, match="iki kez"):
        parse_cvl("@theme: a\n@theme: b\n@language: python\n@version: 1\n---\n")


def test_bad_version():
    with pytest.raises(CvlFormatError, match="tamsayı"):
        parse_cvl("@theme: a\n@language: python\n@version: bir\n---\n")


def test_unsupported_version():
    with pytest.raises(CvlFormatError, match="sürüm"):
        parse_cvl("@theme: a\n@language: python\n@version: 99\n---\n")
