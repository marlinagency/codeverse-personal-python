"""The Universal Concept List.

Every supported target language shares this fixed vocabulary of programming
concepts. A theme dictionary maps each concept to a themed token; the lexer
resolves themed tokens back to these concepts; codegen modules declare their
support level per concept.

Concepts come in three kinds:

* ``KEYWORD``  — structural language keywords the parser dispatches on
  (function definition, if/else, loops, ...).
* ``BUILTIN``  — built-in callables available as plain names (print, range,
  len).
* ``METHOD``   — operations invoked with method syntax on list/dict values
  (``xs.append(v)``, ``d.get(k)``, ...).
"""

from __future__ import annotations

from enum import Enum


class ConceptKind(Enum):
    KEYWORD = "keyword"
    BUILTIN = "builtin"
    METHOD = "method"


class UniversalConcept(Enum):
    """(stable key, canonical token, kind)."""

    # --- structural keywords ---
    FUNCTION_DEF = ("function_def", "func", ConceptKind.KEYWORD)
    RETURN = ("return", "return", ConceptKind.KEYWORD)
    IF = ("if", "if", ConceptKind.KEYWORD)
    ELIF = ("elif", "elif", ConceptKind.KEYWORD)
    ELSE = ("else", "else", ConceptKind.KEYWORD)
    FOR = ("for", "for", ConceptKind.KEYWORD)
    IN = ("in", "in", ConceptKind.KEYWORD)
    WHILE = ("while", "while", ConceptKind.KEYWORD)
    BREAK = ("break", "break", ConceptKind.KEYWORD)
    CONTINUE = ("continue", "continue", ConceptKind.KEYWORD)
    CLASS_DEF = ("class_def", "class", ConceptKind.KEYWORD)
    IMPORT = ("import", "import", ConceptKind.KEYWORD)
    TRY = ("try", "try", ConceptKind.KEYWORD)
    EXCEPT = ("except", "except", ConceptKind.KEYWORD)
    FINALLY = ("finally", "finally", ConceptKind.KEYWORD)
    AND = ("and", "and", ConceptKind.KEYWORD)
    OR = ("or", "or", ConceptKind.KEYWORD)
    NOT = ("not", "not", ConceptKind.KEYWORD)
    TRUE = ("true", "true", ConceptKind.KEYWORD)
    FALSE = ("false", "false", ConceptKind.KEYWORD)
    NONE = ("none", "none", ConceptKind.KEYWORD)
    LAMBDA = ("lambda", "lambda", ConceptKind.KEYWORD)
    GLOBAL = ("global", "global", ConceptKind.KEYWORD)
    NONLOCAL = ("nonlocal", "nonlocal", ConceptKind.KEYWORD)
    DEL = ("del", "del", ConceptKind.KEYWORD)
    ASSERT = ("assert", "assert", ConceptKind.KEYWORD)
    RAISE = ("raise", "raise", ConceptKind.KEYWORD)

    # --- builtins ---
    PRINT = ("print", "print", ConceptKind.BUILTIN)
    RANGE = ("range", "range", ConceptKind.BUILTIN)
    LEN = ("len", "len", ConceptKind.BUILTIN)

    # --- list/dict method operations ---
    LIST_APPEND = ("list_append", "append", ConceptKind.METHOD)
    LIST_REMOVE = ("list_remove", "remove", ConceptKind.METHOD)
    CONTAINS = ("contains", "contains", ConceptKind.METHOD)
    DICT_GET = ("dict_get", "get", ConceptKind.METHOD)
    DICT_SET = ("dict_set", "set", ConceptKind.METHOD)
    DICT_KEYS = ("dict_keys", "keys", ConceptKind.METHOD)
    DICT_VALUES = ("dict_values", "values", ConceptKind.METHOD)
    DICT_DELETE = ("dict_delete", "delete", ConceptKind.METHOD)

    def __init__(self, key: str, canonical: str, kind: ConceptKind) -> None:
        self.key = key
        self.canonical = canonical
        self.kind = kind

    @classmethod
    def from_key(cls, key: str) -> "UniversalConcept":
        try:
            return _BY_KEY[key]
        except KeyError:
            raise ValueError(f"Unknown universal concept key: {key!r}") from None


_BY_KEY: dict[str, UniversalConcept] = {c.key: c for c in UniversalConcept}

KEYWORD_CONCEPTS: tuple[UniversalConcept, ...] = tuple(
    c for c in UniversalConcept if c.kind is ConceptKind.KEYWORD
)
BUILTIN_CONCEPTS: tuple[UniversalConcept, ...] = tuple(
    c for c in UniversalConcept if c.kind is ConceptKind.BUILTIN
)
METHOD_CONCEPTS: tuple[UniversalConcept, ...] = tuple(
    c for c in UniversalConcept if c.kind is ConceptKind.METHOD
)

#: Canonical tokens of every concept — themed tokens must never collide with
#: these, nor with real keywords of supported target languages.
RESERVED_TOKENS: frozenset[str] = frozenset(c.canonical for c in UniversalConcept) | frozenset(
    {
        # Python keywords not already covered by canonical tokens
        "def", "yield", "pass", "with", "as", "is", "from", "await", "async",
        "match", "case", "True", "False", "None",
        # SQL / PL-pgSQL reserved words that would be ambiguous in generated code
        "select", "insert", "update", "delete_", "where", "begin", "end",
        "declare", "loop", "exception", "create", "drop", "table",
    }
)

#: DSL type names are canonical (not themed) by design — see plan §3.
DSL_TYPE_NAMES: frozenset[str] = frozenset({"int", "float", "str", "bool", "list", "dict"})
