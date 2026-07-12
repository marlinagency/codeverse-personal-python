from codeverse_core.cvl.translation_trace import build_translation_trace
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionary


def test_translation_trace_replaces_tokens_but_not_strings_or_comments():
    dictionary = TaxonomyThemeDictionary(
        theme="Dispatch",
        mappings={"py_kw_if": "ready_check", "py_fn_print": "radio_call"},
    )
    source = (
        "@theme: Dispatch\n@language: python\n@version: 1\n---\n"
        "ready_check True:\n"
        "    radio_call(\"ready_check radio_call\")  # radio_call\n"
    )

    trace = build_translation_trace(source, dictionary)

    assert trace[0].python_source == "if True:"
    assert trace[1].python_source == '    print("ready_check radio_call")  # radio_call'
    assert [item.python_token for item in trace[1].replacements] == ["print"]
