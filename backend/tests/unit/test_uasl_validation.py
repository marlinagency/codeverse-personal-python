from __future__ import annotations

from codeverse_core.lexer.lexer import Lexer
from codeverse_core.parser.parser import Parser
from codeverse_core.theme_mapping.dictionary import CANONICAL_DICTIONARY
from codeverse_core.uasl.validation import known_globals_for_language, validate_program


def check(source):
    tokens = Lexer(source, CANONICAL_DICTIONARY).tokenize()
    program = Parser(tokens, CANONICAL_DICTIONARY).parse_program()
    return validate_program(program)


def test_clean_program_no_errors():
    errors = check("func f(a):\n    return a + 1\nx = f(3)\nprint(x)")
    assert errors == []


def test_undefined_name_reported():
    errors = check("print(tanimsiz)")
    assert any("undefined name" in e.message and "tanimsiz" in e.message for e in errors)


def test_return_outside_function():
    errors = check("return 5")
    assert any("outside a function" in e.message for e in errors)


def test_break_outside_loop():
    errors = check("break")
    assert any("outside a loop" in e.message for e in errors)


def test_forward_function_reference_ok():
    errors = check(
        "func a():\n    return b()\nfunc b():\n    return 1\nprint(a())"
    )
    assert errors == []


def test_duplicate_function_reported():
    errors = check("func f():\n    return 1\nfunc f():\n    return 2")
    assert any("already defined" in e.message for e in errors)


def test_duplicate_function_parameter_reported():
    errors = check("func f(a, a):\n    return a")
    assert any("parameter" in e.message and "defined twice" in e.message for e in errors)


def test_required_parameter_after_default_reported():
    errors = check("func f(a = 1, b):\n    return b")
    assert any("required parameter" in e.message for e in errors)


def test_duplicate_class_field_and_method_reported():
    errors = check(
        "class Oyuncu:\n"
        "    puan = 1\n"
        "    puan = 2\n"
        "    func ekle(x):\n"
        "        return x\n"
        "    func ekle(y):\n"
        "        return y\n"
    )
    assert any("field" in e.message and "defined twice" in e.message for e in errors)
    assert any("method" in e.message and "defined twice" in e.message for e in errors)


def test_loop_variable_defined_in_body():
    errors = check("for i in range(3):\n    print(i)")
    assert errors == []


def test_except_bind_name_defined():
    errors = check("try:\n    x = 1\nexcept e:\n    print(e)")
    assert errors == []


def test_builtins_known():
    errors = check("print(len([1, 2]))\nfor i in range(2):\n    print(i)")
    assert errors == []


def test_assignment_to_python_builtin_name_is_rejected_before_runtime():
    tokens = Lexer('dict = dict({"base": 100})', CANONICAL_DICTIONARY).tokenize()
    program = Parser(tokens, CANONICAL_DICTIONARY).parse_program()

    errors = validate_program(program, known_globals_for_language("python"))

    assert any("built-in Python concept" in e.message and "dict" in e.message for e in errors)


def test_loop_variable_cannot_shadow_python_builtin_name():
    tokens = Lexer("for print in range(2):\n    x = print", CANONICAL_DICTIONARY).tokenize()
    program = Parser(tokens, CANONICAL_DICTIONARY).parse_program()

    errors = validate_program(program, known_globals_for_language("python"))

    assert any("built-in Python concept" in e.message and "print" in e.message for e in errors)
