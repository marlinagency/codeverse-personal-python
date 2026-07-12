from __future__ import annotations

import pytest

from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from tests.golden.util import SPACE_DICTIONARY


def compile_sql(body: str) -> str:
    source = f"""@theme: uzayda karadelikleri seven biri
@language: sql
@version: 1
---
{body}
"""
    return CompilationPipeline().compile(source, SPACE_DICTIONARY).codegen.source_code


def test_sql_rejects_too_many_function_arguments():
    with pytest.raises(CompilationError) as raised:
        compile_sql(
            "singularity f(a):\n"
            "    emit a\n"
            "radiate(f(1, 2))\n"
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.stage == "codegen"
    assert "1 arguments" in diagnostic.message
    assert "2 given" in diagnostic.message


def test_sql_allows_omitted_default_arguments():
    generated = compile_sql(
        "singularity f(a, b = 2):\n"
        "    emit a + b\n"
        "radiate(f(1))\n"
    )

    assert "f(1)" in generated


def test_sql_rejects_wrong_collection_mutation_arity():
    with pytest.raises(CompilationError) as raised:
        compile_sql("xs = []\nxs.accrete()\n")

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.stage == "codegen"
    assert "'accrete' takes 1 arguments, 0 given" in diagnostic.message


def test_sql_rejects_wrong_class_method_arguments():
    with pytest.raises(CompilationError) as raised:
        compile_sql(
            "constellation Oyuncu:\n"
            "    puan = 0\n"
            "    singularity ekle(x):\n"
            "        emit self.puan + x\n"
            "o = Oyuncu(1)\n"
            "radiate(o.ekle())\n"
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.stage == "codegen"
    assert "'Oyuncu.ekle' takes 1 arguments, 0 given" in diagnostic.message


def test_sql_mutating_class_method_updates_statement_target():
    generated = compile_sql(
        "constellation Oyuncu:\n"
        "    puan = 0\n"
        "    singularity ekle(x):\n"
        "        self.puan = self.puan + x\n"
        "        emit self.puan\n"
        "o = Oyuncu(1)\n"
        "o.ekle(2)\n"
        "radiate(o.puan)\n"
    )

    assert "RETURNS Oyuncu" in generated
    assert "RETURN self;" in generated
    assert "o := Oyuncu_ekle(o, 2);" in generated


def test_compile_sql_helper_surfaces_codegen_errors_directly():
    with pytest.raises(CompilationError):
        compile_sql("radiate(unknown_function(1))\n")
