from __future__ import annotations

import pytest

from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline


def compile_(body: str, dictionary, language: str = "python"):
    src = f"@theme: uzay\n@language: {language}\n@version: 1\n---\n{body}"
    return CompilationPipeline().compile(src, dictionary)


def test_empty_body_rejected(space_dictionary):
    with pytest.raises(CompilationError, match="boş"):
        compile_("", space_dictionary)


def test_comment_only_body_rejected(space_dictionary):
    with pytest.raises(CompilationError, match="boş"):
        compile_("# sadece yorum\n\n", space_dictionary)


def test_diagnostic_line_offset_maps_to_file_coordinates(space_dictionary):
    # body line 1 == file line 5 (4 header lines before it)
    with pytest.raises(CompilationError) as exc_info:
        compile_("radiate(tanimsiz)", space_dictionary)
    diag = exc_info.value.diagnostics[0]
    assert diag.line == 5
    assert diag.stage == "semantic"


def test_end_to_end_python_compile(space_dictionary):
    result = compile_(
        "singularity kare(n):\n    emit n * n\nradiate(kare(4))",
        space_dictionary,
    )
    assert result.codegen.target_language == "python"
    assert "def kare(n):" in result.codegen.source_code


def test_end_to_end_sql_compile(space_dictionary):
    result = compile_(
        "singularity kare(n):\n    emit n * n\nradiate(kare(4))",
        space_dictionary,
        language="sql",
    )
    assert "CREATE OR REPLACE FUNCTION kare" in result.codegen.source_code
    assert "DO $main$" in result.codegen.source_code
