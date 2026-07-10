"""Shared helpers for golden-file tests.

Golden flow: compile ``cases/<name>.cvl`` with the space theme dictionary,
compare generated code against ``expected/<name>.<ext>``. For Python cases
the generated code is ALSO executed with the current interpreter and its
stdout compared against ``expected_output/<name>.out`` — proving the code
not only looks right but runs right (no Docker needed; sandbox tests cover
isolation separately).

Set ``CODEVERSE_UPDATE_GOLDEN=1`` to (re)write expected files from current
generator output — then review the diff before committing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from codeverse_core.concepts import UniversalConcept
from codeverse_core.cvl.pipeline import CompilationPipeline
from codeverse_core.theme_mapping.dictionary import ThemeDictionary

SPACE_DICTIONARY = ThemeDictionary(
    theme="uzayda karadelikleri seven biri",
    mappings={
        UniversalConcept.FUNCTION_DEF: "singularity",
        UniversalConcept.RETURN: "emit",
        UniversalConcept.IF: "event_horizon",
        UniversalConcept.ELIF: "or_horizon",
        UniversalConcept.ELSE: "vacuum",
        UniversalConcept.FOR: "orbit",
        UniversalConcept.IN: "around",
        UniversalConcept.WHILE: "spin_while",
        UniversalConcept.BREAK: "escape",
        UniversalConcept.CONTINUE: "slingshot",
        UniversalConcept.CLASS_DEF: "constellation",
        UniversalConcept.IMPORT: "beam",
        UniversalConcept.TRY: "probe",
        UniversalConcept.EXCEPT: "hawking_catch",
        UniversalConcept.FINALLY: "collapse",
        UniversalConcept.AND: "gravity_and",
        UniversalConcept.OR: "photon_or",
        UniversalConcept.NOT: "antimatter",
        UniversalConcept.TRUE: "lightspeed",
        UniversalConcept.FALSE: "darkness",
        UniversalConcept.NONE: "void",
        UniversalConcept.PRINT: "radiate",
        UniversalConcept.RANGE: "lightyears",
        UniversalConcept.LEN: "mass",
        UniversalConcept.LIST_APPEND: "accrete",
        UniversalConcept.LIST_REMOVE: "eject",
        UniversalConcept.CONTAINS: "captures",
        UniversalConcept.DICT_GET: "observe",
        UniversalConcept.DICT_SET: "chart",
        UniversalConcept.DICT_KEYS: "coordinates",
        UniversalConcept.DICT_VALUES: "readings",
        UniversalConcept.DICT_DELETE: "evaporate",
    },
)


def compile_case(case_path: Path) -> str:
    pipeline = CompilationPipeline()
    result = pipeline.compile(case_path.read_text(encoding="utf-8"), SPACE_DICTIONARY)
    return result.codegen.source_code


def assert_matches_golden(generated: str, expected_path: Path) -> None:
    if os.environ.get("CODEVERSE_UPDATE_GOLDEN") == "1":
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        expected_path.write_text(generated, encoding="utf-8", newline="\n")
        return
    assert expected_path.exists(), (
        f"golden dosyası eksik: {expected_path} "
        "(CODEVERSE_UPDATE_GOLDEN=1 ile üretebilirsiniz)"
    )
    expected = expected_path.read_text(encoding="utf-8")
    assert generated == expected, (
        f"üretilen kod golden dosyadan farklı: {expected_path.name}"
    )


def run_python(code: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-"],
        input=code,
        capture_output=True,
        text=True,
        timeout=15,
        encoding="utf-8",
    )
    assert proc.returncode == 0, f"üretilen Python kodu hata verdi:\n{proc.stderr}"
    return proc.stdout.replace("\r\n", "\n")
