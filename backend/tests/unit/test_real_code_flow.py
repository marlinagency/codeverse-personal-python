import contextlib
import io

from codeverse_core.cvl.pipeline import CompilationPipeline
from codeverse_core.cvl.translation_trace import build_translation_trace
from tests.golden.util import SPACE_DICTIONARY


def test_personal_program_crosses_core_families_and_runs_as_python():
    source = """@theme: space
@language: python
@version: 1
---
singularity collect(values):
    kept = []
    probe:
        orbit value around values:
            event_horizon value > 0:
                kept.accrete(value)
        radiate(mass(kept))
    hawking_catch Exception:
        radiate("error")
    collapse:
        radiate("done")
    emit kept

radiate(collect([-1, 2, 3]))
"""

    compiled = CompilationPipeline().compile(source, SPACE_DICTIONARY)
    trace = build_translation_trace(source, SPACE_DICTIONARY)
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exec(compiled.codegen.source_code, {})  # noqa: S102 - generated code is the test subject

    assert stdout.getvalue() == "2\ndone\n[2, 3]\n"
    assert "def collect(values):" in compiled.codegen.source_code
    assert "try:" in compiled.codegen.source_code
    assert "except" in compiled.codegen.source_code
    assert "Exception" in compiled.codegen.source_code
    assert "finally:" in compiled.codegen.source_code
    assert "for value in values:" in compiled.codegen.source_code
    assert any(item.python_source.strip() == "def collect(values):" for item in trace)
    assert any("kept.append(value)" in item.python_source for item in trace)
