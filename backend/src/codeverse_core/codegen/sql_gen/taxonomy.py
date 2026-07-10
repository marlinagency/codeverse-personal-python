"""Taxonomy-scale SQL lowering tables for Adim 11.

The parser still produces a small UASL, so SQL taxonomy concepts enter codegen
as ordinary calls (``lower(x)``, ``concat(a, b)``) or method calls
(``name.upper()``, ``items.extend(xs)``). This module keeps those mappings
data-driven: one registry plus a small renderer, not hundreds of bespoke
branches in ``emitters.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

TEXT = "text"
NUMERIC = "numeric"
BOOL = "boolean"
JSONB = "jsonb"
INTEGER = "integer"
UNKNOWN = "unknown"

Renderer = Callable[[list[str]], str]


@dataclass(frozen=True)
class SqlCallSpec:
    min_args: int
    max_args: int | None
    return_type: str
    arg_types: tuple[str, ...] = ()
    variadic_type: str | None = None
    sql_name: str | None = None
    renderer: Renderer | None = None

    def arg_type(self, index: int) -> str:
        if index < len(self.arg_types):
            return self.arg_types[index]
        if self.variadic_type is not None:
            return self.variadic_type
        if self.arg_types:
            return self.arg_types[-1]
        return UNKNOWN

    def render(self, name: str, args: list[str]) -> str:
        if self.renderer is not None:
            return self.renderer(args)
        sql_name = self.sql_name or name
        return f"{sql_name}({', '.join(args)})"


@dataclass(frozen=True)
class SqlMethodSpec:
    min_args: int
    max_args: int | None
    return_type: str
    target_type: str
    arg_types: tuple[str, ...] = ()
    variadic_type: str | None = None
    renderer: Callable[[str, list[str]], str] | None = None

    def arg_type(self, index: int) -> str:
        if index < len(self.arg_types):
            return self.arg_types[index]
        if self.variadic_type is not None:
            return self.variadic_type
        if self.arg_types:
            return self.arg_types[-1]
        return UNKNOWN

    def render(self, target: str, args: list[str]) -> str:
        if self.renderer is None:
            raise ValueError("method spec has no renderer")
        return self.renderer(target, args)


def _direct(sql_name: str, return_type: str, *arg_types: str) -> SqlCallSpec:
    return SqlCallSpec(
        min_args=len(arg_types),
        max_args=len(arg_types),
        return_type=return_type,
        arg_types=arg_types,
        sql_name=sql_name,
    )


def _variadic(
    sql_name: str,
    return_type: str,
    min_args: int,
    variadic_type: str,
    first_types: tuple[str, ...] = (),
) -> SqlCallSpec:
    return SqlCallSpec(
        min_args=min_args,
        max_args=None,
        return_type=return_type,
        arg_types=first_types,
        variadic_type=variadic_type,
        sql_name=sql_name,
    )


def _substring(args: list[str]) -> str:
    if len(args) == 2:
        return f"substr({args[0]}, ({args[1]})::int)"
    return f"substr({args[0]}, ({args[1]})::int, ({args[2]})::int)"


def _position(args: list[str]) -> str:
    return f"strpos({args[1]}, {args[0]})"


def _case_when(args: list[str]) -> str:
    return f"(CASE WHEN {args[0]} THEN {args[1]} ELSE {args[2]} END)"


def _current(sql: str) -> Renderer:
    return lambda _args: sql


SQL_FUNCTIONS: dict[str, SqlCallSpec] = {
    # string functions, including common MySQL/SQL Server aliases lowered to
    # PostgreSQL equivalents
    "ascii": _direct("ascii", INTEGER, TEXT),
    "char_length": _direct("char_length", INTEGER, TEXT),
    "character_length": _direct("char_length", INTEGER, TEXT),
    "concat": _variadic("concat", TEXT, 1, TEXT),
    "concat_ws": _variadic("concat_ws", TEXT, 2, TEXT, (TEXT,)),
    "lcase": _direct("lower", TEXT, TEXT),
    "left": _direct("left", TEXT, TEXT, INTEGER),
    "length": _direct("char_length", INTEGER, TEXT),
    "len": _direct("char_length", INTEGER, TEXT),
    "locate": SqlCallSpec(2, 2, INTEGER, (TEXT, TEXT), renderer=_position),
    "lower": _direct("lower", TEXT, TEXT),
    "lpad": _direct("lpad", TEXT, TEXT, INTEGER, TEXT),
    "ltrim": _direct("ltrim", TEXT, TEXT),
    "mid": SqlCallSpec(2, 3, TEXT, (TEXT, INTEGER, INTEGER), renderer=_substring),
    "position": SqlCallSpec(2, 2, INTEGER, (TEXT, TEXT), renderer=_position),
    "repeat": _direct("repeat", TEXT, TEXT, INTEGER),
    "replace": _direct("replace", TEXT, TEXT, TEXT, TEXT),
    "reverse": _direct("reverse", TEXT, TEXT),
    "right": _direct("right", TEXT, TEXT, INTEGER),
    "rpad": _direct("rpad", TEXT, TEXT, INTEGER, TEXT),
    "rtrim": _direct("rtrim", TEXT, TEXT),
    "space": SqlCallSpec(1, 1, TEXT, (INTEGER,), renderer=lambda a: f"repeat(' ', {a[0]})"),
    "substr": SqlCallSpec(2, 3, TEXT, (TEXT, INTEGER, INTEGER), renderer=_substring),
    "substring": SqlCallSpec(2, 3, TEXT, (TEXT, INTEGER, INTEGER), renderer=_substring),
    "trim": _direct("btrim", TEXT, TEXT),
    "ucase": _direct("upper", TEXT, TEXT),
    "upper": _direct("upper", TEXT, TEXT),
    # numeric functions
    "abs": _direct("abs", NUMERIC, NUMERIC),
    "acos": _direct("acos", NUMERIC, NUMERIC),
    "asin": _direct("asin", NUMERIC, NUMERIC),
    "atan": _direct("atan", NUMERIC, NUMERIC),
    "atan2": _direct("atan2", NUMERIC, NUMERIC, NUMERIC),
    "ceil": _direct("ceil", NUMERIC, NUMERIC),
    "ceiling": _direct("ceil", NUMERIC, NUMERIC),
    "cos": _direct("cos", NUMERIC, NUMERIC),
    "cot": _direct("cot", NUMERIC, NUMERIC),
    "degrees": _direct("degrees", NUMERIC, NUMERIC),
    "div": SqlCallSpec(2, 2, NUMERIC, (NUMERIC, NUMERIC), renderer=lambda a: f"trunc({a[0]} / {a[1]})"),
    "exp": _direct("exp", NUMERIC, NUMERIC),
    "floor": _direct("floor", NUMERIC, NUMERIC),
    "greatest": _variadic("greatest", NUMERIC, 1, NUMERIC),
    "least": _variadic("least", NUMERIC, 1, NUMERIC),
    "ln": _direct("ln", NUMERIC, NUMERIC),
    "log": _direct("ln", NUMERIC, NUMERIC),
    "log10": _direct("log", NUMERIC, NUMERIC),
    "mod": _direct("mod", NUMERIC, NUMERIC, NUMERIC),
    "pi": SqlCallSpec(0, 0, NUMERIC, renderer=_current("pi()")),
    "pow": _direct("power", NUMERIC, NUMERIC, NUMERIC),
    "power": _direct("power", NUMERIC, NUMERIC, NUMERIC),
    "radians": _direct("radians", NUMERIC, NUMERIC),
    "rand": SqlCallSpec(0, 0, NUMERIC, renderer=_current("random()")),
    "round": SqlCallSpec(1, 2, NUMERIC, (NUMERIC, INTEGER), sql_name="round"),
    "sgn": _direct("sign", NUMERIC, NUMERIC),
    "sign": _direct("sign", NUMERIC, NUMERIC),
    "sin": _direct("sin", NUMERIC, NUMERIC),
    "sqrt": _direct("sqrt", NUMERIC, NUMERIC),
    "square": SqlCallSpec(1, 1, NUMERIC, (NUMERIC,), renderer=lambda a: f"({a[0]} * {a[0]})"),
    "tan": _direct("tan", NUMERIC, NUMERIC),
    # nulls / conditionals
    "coalesce": _variadic("coalesce", UNKNOWN, 1, UNKNOWN),
    "ifnull": _direct("coalesce", UNKNOWN, UNKNOWN, UNKNOWN),
    "iif": SqlCallSpec(3, 3, UNKNOWN, (BOOL, UNKNOWN, UNKNOWN), renderer=_case_when),
    "nullif": _direct("nullif", UNKNOWN, UNKNOWN, UNKNOWN),
    # date/time zero-arg functions that map cleanly to PostgreSQL
    "current_date": SqlCallSpec(0, 0, TEXT, renderer=_current("CURRENT_DATE")),
    "current_time": SqlCallSpec(0, 0, TEXT, renderer=_current("CURRENT_TIME")),
    "current_timestamp": SqlCallSpec(0, 0, TEXT, renderer=_current("CURRENT_TIMESTAMP")),
    "localtime": SqlCallSpec(0, 0, TEXT, renderer=_current("LOCALTIME")),
    "localtimestamp": SqlCallSpec(0, 0, TEXT, renderer=_current("LOCALTIMESTAMP")),
    "now": SqlCallSpec(0, 0, TEXT, renderer=_current("now()")),
    # aggregates are real SQL functions; they only make semantic sense when a
    # future query AST supplies a table scope, but codegen can lower the call.
    "avg": _direct("avg", NUMERIC, NUMERIC),
    "count": SqlCallSpec(1, 1, INTEGER, (UNKNOWN,), sql_name="count"),
    "max": _direct("max", NUMERIC, NUMERIC),
    "min": _direct("min", NUMERIC, NUMERIC),
    "sum": _direct("sum", NUMERIC, NUMERIC),
}


TEXT_METHODS: dict[str, SqlMethodSpec] = {
    "capitalize": SqlMethodSpec(0, 0, TEXT, TEXT, renderer=lambda t, _a: f"(upper(substr({t}, 1, 1)) || lower(substr({t}, 2)))"),
    "casefold": SqlMethodSpec(0, 0, TEXT, TEXT, renderer=lambda t, _a: f"lower({t})"),
    "count": SqlMethodSpec(1, 1, INTEGER, TEXT, (TEXT,), renderer=lambda t, a: f"_cv_str_count({t}, {a[0]})"),
    "endswith": SqlMethodSpec(1, 1, BOOL, TEXT, (TEXT,), renderer=lambda t, a: f"(right({t}, char_length({a[0]})) = {a[0]})"),
    "find": SqlMethodSpec(1, 1, INTEGER, TEXT, (TEXT,), renderer=lambda t, a: f"(strpos({t}, {a[0]}) - 1)"),
    "isalnum": SqlMethodSpec(0, 0, BOOL, TEXT, renderer=lambda t, _a: f"({t} ~ '^[[:alnum:]]+$')"),
    "isalpha": SqlMethodSpec(0, 0, BOOL, TEXT, renderer=lambda t, _a: f"({t} ~ '^[[:alpha:]]+$')"),
    "isdigit": SqlMethodSpec(0, 0, BOOL, TEXT, renderer=lambda t, _a: f"({t} ~ '^[[:digit:]]+$')"),
    "islower": SqlMethodSpec(0, 0, BOOL, TEXT, renderer=lambda t, _a: f"({t} = lower({t}) AND {t} <> upper({t}))"),
    "isspace": SqlMethodSpec(0, 0, BOOL, TEXT, renderer=lambda t, _a: f"({t} ~ '^\\s+$')"),
    "istitle": SqlMethodSpec(0, 0, BOOL, TEXT, renderer=lambda t, _a: f"({t} = initcap({t}))"),
    "isupper": SqlMethodSpec(0, 0, BOOL, TEXT, renderer=lambda t, _a: f"({t} = upper({t}) AND {t} <> lower({t}))"),
    "join": SqlMethodSpec(1, 1, TEXT, TEXT, (JSONB,), renderer=lambda t, a: f"_cv_str_join({t}, {a[0]})"),
    "lower": SqlMethodSpec(0, 0, TEXT, TEXT, renderer=lambda t, _a: f"lower({t})"),
    "lstrip": SqlMethodSpec(0, 0, TEXT, TEXT, renderer=lambda t, _a: f"ltrim({t})"),
    "replace": SqlMethodSpec(2, 2, TEXT, TEXT, (TEXT, TEXT), renderer=lambda t, a: f"replace({t}, {a[0]}, {a[1]})"),
    "rfind": SqlMethodSpec(1, 1, INTEGER, TEXT, (TEXT,), renderer=lambda t, a: f"_cv_str_rfind({t}, {a[0]})"),
    "rstrip": SqlMethodSpec(0, 0, TEXT, TEXT, renderer=lambda t, _a: f"rtrim({t})"),
    "split": SqlMethodSpec(1, 1, JSONB, TEXT, (TEXT,), renderer=lambda t, a: f"to_jsonb(string_to_array({t}, {a[0]}))"),
    "startswith": SqlMethodSpec(1, 1, BOOL, TEXT, (TEXT,), renderer=lambda t, a: f"(left({t}, char_length({a[0]})) = {a[0]})"),
    "strip": SqlMethodSpec(0, 0, TEXT, TEXT, renderer=lambda t, _a: f"btrim({t})"),
    "title": SqlMethodSpec(0, 0, TEXT, TEXT, renderer=lambda t, _a: f"initcap({t})"),
    "upper": SqlMethodSpec(0, 0, TEXT, TEXT, renderer=lambda t, _a: f"upper({t})"),
}


JSONB_EXPR_METHODS: dict[str, SqlMethodSpec] = {
    "copy": SqlMethodSpec(0, 0, JSONB, JSONB, renderer=lambda t, _a: t),
    "items": SqlMethodSpec(0, 0, JSONB, JSONB, renderer=lambda t, _a: f"_cv_items({t})"),
}


JSONB_STATEMENT_METHODS: dict[str, SqlMethodSpec] = {
    "clear": SqlMethodSpec(0, 0, JSONB, JSONB, renderer=lambda t, _a: f"_cv_clear({t})"),
    "extend": SqlMethodSpec(1, 1, JSONB, JSONB, (JSONB,), renderer=lambda t, a: f"_cv_extend({t}, {a[0]})"),
    "insert": SqlMethodSpec(2, 2, JSONB, JSONB, (INTEGER, JSONB), renderer=lambda t, a: f"_cv_insert({t}, {a[0]}, {a[1]})"),
    "reverse": SqlMethodSpec(0, 0, JSONB, JSONB, renderer=lambda t, _a: f"_cv_reverse({t})"),
    "sort": SqlMethodSpec(0, 0, JSONB, JSONB, renderer=lambda t, _a: f"_cv_sort({t})"),
    "update": SqlMethodSpec(1, 1, JSONB, JSONB, (JSONB,), renderer=lambda t, a: f"_cv_update({t}, {a[0]})"),
}

