"""UASL -> PostgreSQL (PL/pgSQL) emission.

Program shape: prelude, then extensions (imports), composite types (classes),
functions, then all remaining top-level statements wrapped in one
``DO $main$ ... $main$;`` block.

A light type system drives casts between jsonb containers and scalars:
every expression is inferred to one of numeric | text | boolean | jsonb |
integer | void | <composite class name> | unknown.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codeverse_core.codegen.base import CodegenError, CodegenWarning
from codeverse_core.codegen.sql_gen import dialect
from codeverse_core.codegen.sql_gen import taxonomy
from codeverse_core.uasl import nodes

NUMERIC = "numeric"
TEXT = "text"
BOOL = "boolean"
JSONB = "jsonb"
INTEGER = "integer"
VOID = "void"
UNKNOWN = "unknown"

_SCALARS = {NUMERIC, TEXT, BOOL, INTEGER}
_TOP_LEVEL_SQL_STMTS = (
    nodes.SqlSelect,
    nodes.SqlCreateTable,
    nodes.SqlInsert,
    nodes.SqlUpdate,
    nodes.SqlDelete,
    nodes.SqlDropTable,
    nodes.SqlTruncateTable,
    nodes.SqlAlterTable,
    nodes.SqlCreateIndex,
    nodes.SqlDropIndex,
    nodes.SqlCreateView,
    nodes.SqlDropView,
    nodes.SqlCreateDatabase,
    nodes.SqlDropDatabase,
)


@dataclass
class _FunctionSig:
    param_types: list[str]
    return_type: str
    required_params: int
    mutates_self: bool = False


@dataclass
class _ClassInfo:
    name: str
    #: field name -> (sql type, default expression node or None)
    fields: dict[str, tuple[str, nodes.Node | None]] = field(default_factory=dict)
    methods: dict[str, _FunctionSig] = field(default_factory=dict)


class SqlEmitter:
    def __init__(self) -> None:
        self.warnings: list[CodegenWarning] = []
        self._functions: dict[str, _FunctionSig] = {}
        self._classes: dict[str, _ClassInfo] = {}

    # ------------------------------------------------------------ program

    def emit_program(self, program: nodes.Program) -> str:
        imports: list[nodes.Import] = []
        classes: list[nodes.ClassDef] = []
        functions: list[nodes.FunctionDef] = []
        top_level: list[nodes.Node] = []

        for stmt in program.body:
            if isinstance(stmt, nodes.Import):
                imports.append(stmt)
            elif isinstance(stmt, nodes.ClassDef):
                classes.append(stmt)
            elif isinstance(stmt, nodes.FunctionDef):
                functions.append(stmt)
            else:
                top_level.append(stmt)

        # register signatures first (two passes so forward/mutual calls and
        # recursion resolve to refined types on the second pass)
        for cls in classes:
            self._register_class(cls)
        for _ in range(2):
            for fn in functions:
                self._functions[fn.name] = self._infer_signature(fn)
            for cls in classes:
                info = self._classes[cls.name]
                for m in cls.methods:
                    info.methods[m.name] = self._infer_signature(m, self_class=cls.name)

        parts: list[str] = [dialect.PRELUDE]

        for imp in imports:
            parts.append(self._emit_import(imp))
        for cls in classes:
            parts.append(self._emit_class(cls))
        for fn in functions:
            parts.append(self._emit_function(fn))
        for cls in classes:
            for m in cls.methods:
                parts.append(self._emit_function(m, self_class=cls.name))
        if top_level:
            parts.extend(self._emit_top_level(top_level))

        return "\n".join(parts)

    # ------------------------------------------------------------ imports

    def _emit_import(self, imp: nodes.Import) -> str:
        ext = dialect.EXTENSION_WHITELIST.get(imp.module)
        if ext is None:
            allowed = ", ".join(sorted(dialect.EXTENSION_WHITELIST))
            raise CodegenError(
                f"only these modules can be imported in the SQL target: {allowed} "
                f"('{imp.module}' is not supported)",
                imp,
            )
        return f'CREATE EXTENSION IF NOT EXISTS "{ext}";\n'

    # ------------------------------------------------------------- classes

    def _register_class(self, cls: nodes.ClassDef) -> None:
        if cls.base is not None:
            raise CodegenError(
                "class inheritance is not supported in the SQL target (composite types "
                "do not inherit) — use a class without a base",
                cls,
            )
        info = _ClassInfo(name=cls.name)
        for f in cls.fields:
            if f.type_ref is not None:
                sql_type = self._sql_type(f.type_ref, f)
            elif f.default is not None:
                sql_type = self._infer(f.default, {})
                if sql_type in (UNKNOWN, VOID):
                    sql_type = JSONB
            else:
                raise CodegenError(
                    f"class field '{f.name}' requires a type or a "
                    "default value in the SQL target",
                    f,
                )
            info.fields[f.name] = (sql_type, f.default)
        self._classes[cls.name] = info

    def _emit_class(self, cls: nodes.ClassDef) -> str:
        info = self._classes[cls.name]
        lines = [f"DROP TYPE IF EXISTS {cls.name} CASCADE;"]
        cols = ",\n".join(f"  {name} {t}" for name, (t, _) in info.fields.items())
        lines.append(f"CREATE TYPE {cls.name} AS (\n{cols}\n);\n")
        return "\n".join(lines)

    # ----------------------------------------------------------- functions

    def _infer_signature(
        self, fn: nodes.FunctionDef, self_class: str | None = None
    ) -> _FunctionSig:
        scope: dict[str, str] = {}
        if self_class:
            scope["self"] = self_class
        param_types: list[str] = []
        for p in fn.params:
            if p.type_ref is not None:
                t = self._sql_type(p.type_ref, p)
            elif p.default is not None:
                t = self._infer(p.default, scope)
                if t in (UNKNOWN, VOID):
                    t = NUMERIC
            else:
                t = NUMERIC
                self.warnings.append(
                    CodegenWarning(
                        f"parameter '{p.name}' of function '{fn.name}' has no type "
                        "annotation; assumed 'numeric' (you can add a type like p: int"
                        ")",
                        p.pos.line,
                        p.pos.col,
                    )
                )
            param_types.append(t)
            scope[p.name] = t

        self._collect_declarations(fn.body, scope)
        mutates_self = self_class is not None and self._mutates_self(fn.body)
        ret = self_class if mutates_self else self._find_return_type(fn.body, scope)
        required_params = sum(1 for p in fn.params if p.default is None)
        return _FunctionSig(
            param_types=param_types,
            return_type=ret,
            required_params=required_params,
            mutates_self=mutates_self,
        )

    def _find_return_type(self, body: list[nodes.Node], scope: dict[str, str]) -> str:
        for stmt in body:
            if isinstance(stmt, nodes.Return):
                if stmt.value is None:
                    return VOID
                t = self._infer(stmt.value, scope)
                return NUMERIC if t in (UNKNOWN, VOID) else t
            for sub in _sub_blocks(stmt):
                t = self._find_return_type(sub, scope)
                if t != VOID:
                    return t
        return VOID

    def _mutates_self(self, body: list[nodes.Node]) -> bool:
        for stmt in body:
            if isinstance(stmt, nodes.Assignment):
                target = stmt.target
                if (
                    isinstance(target, nodes.Attribute)
                    and isinstance(target.target, nodes.Identifier)
                    and target.target.name == "self"
                ):
                    return True
            if any(self._mutates_self(sub) for sub in _sub_blocks(stmt)):
                return True
        return False

    def _emit_function(self, fn: nodes.FunctionDef, self_class: str | None = None) -> str:
        if fn.async_def:
            raise CodegenError("async functions are not supported in the SQL target", fn)
        sig = (
            self._classes[self_class].methods[fn.name]
            if self_class
            else self._functions[fn.name]
        )
        fname = f"{self_class}_{fn.name}" if self_class else fn.name

        scope: dict[str, str] = {}
        params: list[str] = []
        if self_class:
            scope["self"] = self_class
            params.append(f"self {self_class}")
        for p, t in zip(fn.params, sig.param_types):
            scope[p.name] = t
            if p.default is not None:
                default_sql = self._coerce(p.default, t, scope)
                params.append(f"{p.name} {t} DEFAULT {default_sql}")
            else:
                params.append(f"{p.name} {t}")

        declarations = self._collect_declarations(fn.body, scope)
        return_override = "self" if sig.mutates_self else None
        body_lines = self._emit_body(fn.body, scope, indent=1, return_override=return_override)

        lines = [
            f"CREATE OR REPLACE FUNCTION {fname}({', '.join(params)})",
            f"RETURNS {sig.return_type}",
            "LANGUAGE plpgsql AS $fn$",
        ]
        if declarations:
            lines.append("DECLARE")
            lines.extend(f"  {name} {t};" for name, t in declarations.items())
        lines.append("BEGIN")
        lines.extend(body_lines)
        if sig.return_type == VOID:
            lines.append("  RETURN;")
        elif sig.mutates_self and (
            not body_lines or body_lines[-1].strip() != "RETURN self;"
        ):
            lines.append("  RETURN self;")
        lines.append("END")
        lines.append("$fn$;\n")
        return "\n".join(lines)

    # ------------------------------------------------------------ DO block

    def _emit_top_level(self, body: list[nodes.Node]) -> list[str]:
        parts: list[str] = []
        pending: list[nodes.Node] = []

        def flush_pending() -> None:
            if pending:
                parts.append(self._emit_do_block(list(pending)))
                pending.clear()

        for stmt in body:
            if isinstance(stmt, _TOP_LEVEL_SQL_STMTS):
                flush_pending()
                parts.append(self._emit_direct_sql(stmt) + ";")
            else:
                pending.append(stmt)
        flush_pending()
        return parts

    def _emit_do_block(self, body: list[nodes.Node]) -> str:
        scope: dict[str, str] = {}
        declarations = self._collect_declarations(body, scope)
        lines = ["DO $main$"]
        if declarations:
            lines.append("DECLARE")
            lines.extend(f"  {name} {t};" for name, t in declarations.items())
        lines.append("BEGIN")
        lines.extend(self._emit_body(body, scope, indent=1))
        lines.append("END")
        lines.append("$main$;")
        return "\n".join(lines)

    # -------------------------------------------------------- declarations

    def _collect_declarations(
        self, body: list[nodes.Node], scope: dict[str, str]
    ) -> dict[str, str]:
        """PL/pgSQL declares all variables up front — walk every nested block
        (except nested functions, which are rejected) and collect first-
        assignment types. Mutates ``scope`` with the collected names."""
        declarations: dict[str, str] = {}
        self._walk_declarations(body, scope, declarations)
        return declarations

    def _walk_declarations(
        self,
        body: list[nodes.Node],
        scope: dict[str, str],
        out: dict[str, str],
    ) -> None:
        for stmt in body:
            if isinstance(stmt, nodes.FunctionDef):
                raise CodegenError(
                    "nested functions cannot be defined in the SQL target — define functions "
                    "at the top level",
                    stmt,
                )
            if isinstance(stmt, nodes.ClassDef):
                raise CodegenError(
                    "classes can only be defined at the top level in the SQL target",
                    stmt,
                )
            if isinstance(stmt, nodes.Assignment) and isinstance(
                stmt.target, nodes.Identifier
            ):
                name = stmt.target.name
                if name not in scope:
                    if stmt.annotation is not None:
                        t = self._sql_type(stmt.annotation, stmt)
                    else:
                        t = self._infer(stmt.value, scope)
                        if t in (UNKNOWN, VOID):
                            t = JSONB
                    scope[name] = t
                    out[name] = t
            elif isinstance(stmt, nodes.ForLoop):
                if stmt.var_name not in scope:
                    t = INTEGER if _is_range_call(stmt.iterable) else JSONB
                    scope[stmt.var_name] = t
                    # integer FOR loops auto-declare their variable in PL/pgSQL
                    if t is not INTEGER:
                        out[stmt.var_name] = t
                self._walk_declarations(stmt.body, scope, out)
            elif isinstance(stmt, nodes.TryExcept):
                self._walk_declarations(stmt.try_body, scope, out)
                for h in stmt.handlers:
                    if h.bind_name and h.bind_name not in scope:
                        scope[h.bind_name] = TEXT
                        out[h.bind_name] = TEXT
                    self._walk_declarations(h.body, scope, out)
                if stmt.finally_body:
                    self._walk_declarations(stmt.finally_body, scope, out)
            else:
                for sub in _sub_blocks(stmt):
                    self._walk_declarations(sub, scope, out)

    # ----------------------------------------------------------- statements

    def _emit_body(
        self,
        body: list[nodes.Node],
        scope: dict[str, str],
        indent: int,
        return_override: str | None = None,
    ) -> list[str]:
        lines: list[str] = []
        for stmt in body:
            lines.extend(self._emit_stmt(stmt, scope, indent, return_override))
        return lines

    def _emit_stmt(
        self,
        stmt: nodes.Node,
        scope: dict[str, str],
        indent: int,
        return_override: str | None = None,
    ) -> list[str]:
        pad = "  " * indent

        if isinstance(stmt, nodes.Assignment):
            return self._emit_assignment(stmt, scope, pad)

        if isinstance(stmt, nodes.ExprStatement):
            return self._emit_expr_statement(stmt.expr, scope, pad)

        if isinstance(stmt, nodes.Return):
            if return_override is not None:
                return [f"{pad}RETURN {return_override};"]
            if stmt.value is None:
                return [f"{pad}RETURN;"]
            return [f"{pad}RETURN {self._expr(stmt.value, scope)};"]

        if isinstance(stmt, nodes.If):
            lines = [f"{pad}IF {self._condition(stmt.condition, scope)} THEN"]
            lines.extend(
                self._emit_body(stmt.then_body, scope, indent + 1, return_override)
            )
            for cond, body in stmt.elif_branches:
                lines.append(f"{pad}ELSIF {self._condition(cond, scope)} THEN")
                lines.extend(self._emit_body(body, scope, indent + 1, return_override))
            if stmt.else_body is not None:
                lines.append(f"{pad}ELSE")
                lines.extend(
                    self._emit_body(stmt.else_body, scope, indent + 1, return_override)
                )
            lines.append(f"{pad}END IF;")
            return lines

        if isinstance(stmt, nodes.ForLoop):
            return self._emit_for(stmt, scope, indent, return_override)

        if isinstance(stmt, nodes.WhileLoop):
            lines = [f"{pad}WHILE {self._condition(stmt.condition, scope)} LOOP"]
            lines.extend(self._emit_body(stmt.body, scope, indent + 1, return_override))
            lines.append(f"{pad}END LOOP;")
            return lines

        if isinstance(stmt, nodes.Break):
            return [f"{pad}EXIT;"]

        if isinstance(stmt, nodes.Continue):
            return [f"{pad}CONTINUE;"]

        if isinstance(stmt, nodes.Pass):
            return [f"{pad}NULL;"]

        if isinstance(stmt, (nodes.Global, nodes.Nonlocal)):
            raise CodegenError(
                "global/nonlocal is only supported by the Python target",
                stmt,
            )

        if isinstance(stmt, nodes.Delete):
            return self._emit_delete(stmt, scope, pad)

        if isinstance(stmt, nodes.Assert):
            message = (
                self._coerce(stmt.message, TEXT, scope)
                if stmt.message is not None
                else "'assertion failed'"
            )
            return [
                f"{pad}IF NOT {self._condition(stmt.condition, scope)} THEN",
                f"{pad}  RAISE EXCEPTION '%', {message};",
                f"{pad}END IF;",
            ]

        if isinstance(stmt, nodes.Raise):
            if stmt.value is None:
                return [f"{pad}RAISE EXCEPTION 'raised from CodeVerse';"]
            return [f"{pad}RAISE EXCEPTION '%', {self._coerce(stmt.value, TEXT, scope)};"]

        if isinstance(stmt, nodes.TryExcept):
            return self._emit_try(stmt, scope, indent, return_override)

        if isinstance(stmt, (nodes.FromImport, nodes.With, nodes.Match)):
            raise CodegenError(
                f"this Python construct is not supported in the SQL target: {type(stmt).__name__}",
                stmt,
            )

        if isinstance(stmt, nodes.SqlSelect):
            return [f"{pad}PERFORM * FROM ({self._emit_select(stmt)}) AS _cv_query;"]

        if isinstance(
            stmt,
            _TOP_LEVEL_SQL_STMTS,
        ):
            raise CodegenError(
                "SQL DDL/DML statements are only supported at the top level",
                stmt,
            )

        raise CodegenError(
            f"the SQL generator does not support this construct: {type(stmt).__name__}", stmt
        )

    def _emit_assignment(
        self, stmt: nodes.Assignment, scope: dict[str, str], pad: str
    ) -> list[str]:
        if isinstance(stmt.target, nodes.Identifier):
            t = scope.get(stmt.target.name, JSONB)
            value_sql = self._coerce(stmt.value, t, scope)
            return [f"{pad}{stmt.target.name} := {value_sql};"]

        if isinstance(stmt.target, nodes.Index):
            base = stmt.target.target
            if not isinstance(base, nodes.Identifier):
                raise CodegenError(
                    "nested index assignment is not supported in the SQL target "
                    "(assign the intermediate value to a variable first)",
                    stmt,
                )
            key_sql = self._to_jsonb(stmt.target.key, scope)
            val_sql = self._to_jsonb(stmt.value, scope)
            return [f"{pad}{base.name} := _cv_set({base.name}, {key_sql}, {val_sql});"]

        if isinstance(stmt.target, nodes.Attribute):
            base_sql = self._expr(stmt.target.target, scope)
            field_type = self._attribute_type(stmt.target, scope)
            val_sql = self._coerce(stmt.value, field_type, scope)
            return [f"{pad}{base_sql}.{stmt.target.name} := {val_sql};"]

        raise CodegenError("invalid assignment target", stmt)

    def _emit_delete(
        self, stmt: nodes.Delete, scope: dict[str, str], pad: str
    ) -> list[str]:
        lines: list[str] = []
        for target in stmt.targets:
            if isinstance(target, nodes.Identifier):
                lines.append(f"{pad}{target.name} := NULL;")
            elif isinstance(target, nodes.Index) and isinstance(
                target.target, nodes.Identifier
            ):
                key_sql = self._to_jsonb(target.key, scope)
                lines.append(
                    f"{pad}{target.target.name} := _cv_del({target.target.name}, {key_sql});"
                )
            elif isinstance(target, nodes.Attribute):
                base_sql = self._expr(target.target, scope)
                lines.append(f"{pad}{base_sql}.{target.name} := NULL;")
            else:
                raise CodegenError("this delete target is not supported in the SQL target", target)
        return lines

    def _emit_expr_statement(
        self, expr: nodes.Node, scope: dict[str, str], pad: str
    ) -> list[str]:
        # print(...) -> RAISE NOTICE
        if isinstance(expr, nodes.Call) and _callee_name(expr) == "print":
            return [f"{pad}RAISE NOTICE '%', {self._print_args(expr.args, scope)};"]

        # collection mutations get statement forms
        if isinstance(expr, nodes.MethodCall):
            method = expr.method
            if method in ("append", "remove", "set", "delete"):
                base = expr.target
                if not isinstance(base, nodes.Identifier):
                    raise CodegenError(
                        "collection operations in the SQL target can only be performed "
                        "on variables",
                        expr,
                    )
                self._expect_method_arity(
                    expr,
                    {"append": 1, "remove": 1, "set": 2, "delete": 1}[method],
                )
                args = [self._to_jsonb(a, scope) for a in expr.args]
                fn = {
                    "append": "_cv_append",
                    "remove": "_cv_remove",
                    "set": "_cv_set",
                    "delete": "_cv_del",
                }[method]
                return [f"{pad}{base.name} := {fn}({base.name}, {', '.join(args)});"]

            if method in taxonomy.JSONB_STATEMENT_METHODS:
                base = expr.target
                if not isinstance(base, nodes.Identifier):
                    raise CodegenError(
                        "collection operations in the SQL target can only be performed "
                        "on variables",
                        expr,
                    )
                if self._infer(base, scope) not in (JSONB, UNKNOWN):
                    shown = expr.themed_method or method
                    raise CodegenError(
                        f"'{shown}' can only be used on list/dict values",
                        expr,
                    )
                spec = taxonomy.JSONB_STATEMENT_METHODS[method]
                self._expect_taxonomy_arity(expr, method, spec.min_args, spec.max_args)
                args = self._coerce_taxonomy_args(expr.args, spec, scope)
                return [f"{pad}{base.name} := {spec.render(base.name, args)};"]

            if isinstance(expr.target, nodes.Identifier):
                target_type = self._infer(expr.target, scope)
                if target_type in self._classes:
                    sig = self._classes[target_type].methods.get(method)
                    if sig is not None and sig.mutates_self:
                        return [
                            f"{pad}{expr.target.name} := {self._method_call(expr, scope)};"
                        ]

        # any other bare expression: evaluate and discard
        t = self._infer(expr, scope)
        sql = self._expr(expr, scope)
        if t == VOID:
            return [f"{pad}PERFORM {sql[7:] if sql.startswith('(SELECT') else sql};"]
        return [f"{pad}PERFORM {sql};"]

    def _emit_for(
        self,
        stmt: nodes.ForLoop,
        scope: dict[str, str],
        indent: int,
        return_override: str | None = None,
    ) -> list[str]:
        pad = "  " * indent
        if _is_range_call(stmt.iterable):
            args = stmt.iterable.args  # type: ignore[attr-defined]
            if len(args) == 1:
                start_sql, end_sql = "0", self._coerce_int(args[0], scope)
            elif len(args) == 2:
                start_sql = self._coerce_int(args[0], scope)
                end_sql = self._coerce_int(args[1], scope)
            else:
                raise CodegenError("range takes 1 or 2 arguments", stmt.iterable)
            lines = [
                f"{pad}FOR {stmt.var_name} IN {start_sql}..({end_sql}) - 1 LOOP"
            ]
        else:
            iter_sql = self._expr(stmt.iterable, scope)
            lines = [
                f"{pad}FOR {stmt.var_name} IN "
                f"SELECT * FROM jsonb_array_elements({iter_sql}) LOOP"
            ]
        lines.extend(self._emit_body(stmt.body, scope, indent + 1, return_override))
        lines.append(f"{pad}END LOOP;")
        return lines

    def _emit_try(
        self,
        stmt: nodes.TryExcept,
        scope: dict[str, str],
        indent: int,
        return_override: str | None = None,
    ) -> list[str]:
        if len(stmt.handlers) > 1:
            raise CodegenError(
                "multiple except blocks are not supported — use a single block",
                stmt.handlers[1],
            )
        pad = "  " * indent
        lines = [f"{pad}BEGIN"]
        lines.extend(self._emit_body(stmt.try_body, scope, indent + 1, return_override))
        for handler in stmt.handlers:
            lines.append(f"{pad}EXCEPTION WHEN OTHERS THEN")
            if handler.bind_name:
                lines.append(f"{pad}  {handler.bind_name} := SQLERRM;")
            lines.extend(self._emit_body(handler.body, scope, indent + 1, return_override))
        lines.append(f"{pad}END;")
        if stmt.finally_body is not None:
            # PL/pgSQL has no FINALLY; emit the block right after the guarded
            # BEGIN/EXCEPTION/END so it runs on both paths (the exception was
            # already handled above).
            lines.extend(self._emit_body(stmt.finally_body, scope, indent, return_override))
        return lines

    # ---------------------------------------------------------- expressions

    def _expr(self, expr: nodes.Node, scope: dict[str, str]) -> str:
        if isinstance(expr, nodes.Identifier):
            return expr.name

        if isinstance(expr, nodes.Literal):
            return self._literal(expr)

        if isinstance(expr, (nodes.ListLiteral, nodes.DictLiteral)):
            return self._container_literal(expr, scope)

        if isinstance(expr, nodes.BinaryOp):
            return self._binary(expr, scope)

        if isinstance(expr, nodes.UnaryOp):
            if expr.op == "not":
                return f"(NOT {self._condition(expr.operand, scope)})"
            return f"(-{self._coerce(expr.operand, NUMERIC, scope)})"

        if isinstance(expr, nodes.AssignmentExpr):
            raise CodegenError("walrus expressions are not supported in the SQL target", expr)

        if isinstance(expr, nodes.LambdaExpr):
            raise CodegenError("lambda expressions are not supported in the SQL target", expr)

        if isinstance(expr, nodes.ConditionalExpr):
            return (
                f"(CASE WHEN {self._condition(expr.condition, scope)} "
                f"THEN {self._expr(expr.then_expr, scope)} "
                f"ELSE {self._expr(expr.else_expr, scope)} END)"
            )

        if isinstance(expr, nodes.BetweenOp):
            op = "NOT BETWEEN" if expr.negated else "BETWEEN"
            return (
                f"({self._expr(expr.expr, scope)} {op} "
                f"{self._expr(expr.lower, scope)} AND {self._expr(expr.upper, scope)})"
            )

        if isinstance(expr, nodes.Star):
            return "*"

        if isinstance(expr, nodes.Call):
            return self._call(expr, scope)

        if isinstance(expr, nodes.MethodCall):
            return self._method_call(expr, scope)

        if isinstance(expr, nodes.Index):
            target_sql = self._expr(expr.target, scope)
            key_sql = self._to_jsonb(expr.key, scope)
            return f"_cv_get({target_sql}, {key_sql})"

        if isinstance(expr, nodes.Attribute):
            base_sql = self._expr(expr.target, scope)
            return f"({base_sql}).{expr.name}"

        raise CodegenError(
            f"the SQL generator does not support this expression: {type(expr).__name__}", expr
        )

    def _literal(self, lit: nodes.Literal) -> str:
        if lit.literal_type == "str":
            return dialect.quote_text_literal(str(lit.value))
        if lit.literal_type == "bool":
            return "true" if lit.value else "false"
        if lit.literal_type == "none":
            return "NULL"
        return str(lit.value)

    def _container_literal(self, expr: nodes.Node, scope: dict[str, str]) -> str:
        if isinstance(expr, nodes.ListLiteral):
            if not expr.elements:
                return "'[]'::jsonb"
            parts = ", ".join(self._to_jsonb(e, scope) for e in expr.elements)
            return f"jsonb_build_array({parts})"
        assert isinstance(expr, nodes.DictLiteral)
        if not expr.entries:
            return "'{}'::jsonb"
        parts: list[str] = []
        for k, v in expr.entries:
            parts.append(self._coerce(k, TEXT, scope))
            parts.append(self._to_jsonb(v, scope))
        return f"jsonb_build_object({', '.join(parts)})"

    def _binary(self, expr: nodes.BinaryOp, scope: dict[str, str]) -> str:
        op = expr.op

        if op in ("and", "or"):
            left = self._condition(expr.left, scope)
            right = self._condition(expr.right, scope)
            return f"({left} {op.upper()} {right})"

        if op in ("==", "!="):
            return self._equality(expr, scope)

        if op in ("is", "is not"):
            left = self._expr(expr.left, scope)
            right = self._expr(expr.right, scope)
            return f"({left} {op.upper()} {right})"

        if op == "like":
            left = self._coerce(expr.left, TEXT, scope)
            right = self._coerce(expr.right, TEXT, scope)
            return f"({left} LIKE {right})"

        if op == "in":
            return f"({self._expr(expr.left, scope)} IN {self._sql_in_values(expr.right)})"

        if op in ("<", "<=", ">", ">="):
            lt, rt = self._infer(expr.left, scope), self._infer(expr.right, scope)
            if TEXT in (lt, rt):
                left = self._coerce(expr.left, TEXT, scope)
                right = self._coerce(expr.right, TEXT, scope)
            else:
                left = self._coerce(expr.left, NUMERIC, scope)
                right = self._coerce(expr.right, NUMERIC, scope)
            return f"({left} {op} {right})"

        if op == "+":
            lt, rt = self._infer(expr.left, scope), self._infer(expr.right, scope)
            if TEXT in (lt, rt):
                left = self._coerce(expr.left, TEXT, scope)
                right = self._coerce(expr.right, TEXT, scope)
                return f"({left} || {right})"
            left = self._coerce(expr.left, NUMERIC, scope)
            right = self._coerce(expr.right, NUMERIC, scope)
            return f"({left} + {right})"

        if op in ("-", "*", "/", "%"):
            left = self._coerce(expr.left, NUMERIC, scope)
            right = self._coerce(expr.right, NUMERIC, scope)
            return f"({left} {op} {right})"

        raise CodegenError(f"the SQL generator does not support the '{op}' operator", expr)

    def _equality(self, expr: nodes.BinaryOp, scope: dict[str, str]) -> str:
        sql_op = "=" if expr.op == "==" else "<>"

        # comparisons against none -> IS [NOT] NULL
        for side, other in ((expr.left, expr.right), (expr.right, expr.left)):
            if isinstance(side, nodes.Literal) and side.literal_type == "none":
                other_sql = self._expr(other, scope)
                return (
                    f"({other_sql} IS NULL)"
                    if expr.op == "=="
                    else f"({other_sql} IS NOT NULL)"
                )

        lt, rt = self._infer(expr.left, scope), self._infer(expr.right, scope)
        if lt == JSONB and rt == JSONB:
            return f"({self._expr(expr.left, scope)} {sql_op} {self._expr(expr.right, scope)})"
        if JSONB in (lt, rt):
            # compare through the scalar side's type
            scalar_type = rt if lt == JSONB else lt
            target = TEXT if scalar_type == TEXT else NUMERIC
            left = self._coerce(expr.left, target, scope)
            right = self._coerce(expr.right, target, scope)
            return f"({left} {sql_op} {right})"
        left = self._expr(expr.left, scope)
        right = self._expr(expr.right, scope)
        return f"({left} {sql_op} {right})"

    def _call(self, expr: nodes.Call, scope: dict[str, str]) -> str:
        name = _callee_name(expr)
        if name is None:
            raise CodegenError(
                "only named calls are allowed in the SQL target", expr
            )

        if name == "print":
            raise CodegenError(
                "printing output is not an expression; use it on its "
                "own line",
                expr,
            )
        if name == "range":
            raise CodegenError(
                "range can only be used in a loop header", expr
            )
        if name == "len":
            if len(expr.args) != 1:
                raise CodegenError("len takes exactly 1 argument", expr)
            arg = expr.args[0]
            t = self._infer(arg, scope)
            if t == TEXT:
                return f"_cv_len({self._expr(arg, scope)})"
            return f"_cv_len({self._to_jsonb(arg, scope)})"

        if name in taxonomy.SQL_FUNCTIONS:
            return self._emit_taxonomy_function(name, expr, scope)

        # class constructor
        if name in self._classes:
            return self._constructor(name, expr, scope)

        # user function
        sig = self._functions.get(name)
        if sig is None:
            raise CodegenError(f"undefined function: '{name}'", expr)
        self._expect_call_arity(
            expr,
            name,
            required=sig.required_params,
            total=len(sig.param_types),
        )
        args: list[str] = []
        for i, a in enumerate(expr.args):
            target = sig.param_types[i] if i < len(sig.param_types) else NUMERIC
            args.append(self._coerce(a, target, scope))
        return f"{name}({', '.join(args)})"

    def _constructor(self, class_name: str, expr: nodes.Call, scope: dict[str, str]) -> str:
        info = self._classes[class_name]
        field_items = list(info.fields.items())
        if len(expr.args) > len(field_items):
            raise CodegenError(
                f"'{class_name}' takes {len(field_items)} fields, "
                f"{len(expr.args)} given",
                expr,
            )
        values: list[str] = []
        for i, (fname, (ftype, fdefault)) in enumerate(field_items):
            if i < len(expr.args):
                values.append(self._coerce(expr.args[i], ftype, scope))
            elif fdefault is not None:
                values.append(self._coerce(fdefault, ftype, scope))
            else:
                values.append("NULL")
        return f"ROW({', '.join(values)})::{class_name}"

    def _method_call(self, expr: nodes.MethodCall, scope: dict[str, str]) -> str:
        method = expr.method
        target_type = self._infer(expr.target, scope)

        if method in ("contains", "get", "keys", "values"):
            self._expect_method_arity(
                expr,
                {"contains": 1, "get": 1, "keys": 0, "values": 0}[method],
            )

        if method == "contains" and len(expr.args) == 1:
            target_sql = self._expr(expr.target, scope)
            return f"_cv_contains({target_sql}, {self._to_jsonb(expr.args[0], scope)})"
        if method == "get" and len(expr.args) == 1:
            target_sql = self._expr(expr.target, scope)
            return f"_cv_get({target_sql}, {self._to_jsonb(expr.args[0], scope)})"
        if method == "keys" and not expr.args:
            return f"_cv_keys({self._expr(expr.target, scope)})"
        if method == "values" and not expr.args:
            return f"_cv_values({self._expr(expr.target, scope)})"
        if method in ("append", "remove", "set", "delete"):
            self._expect_method_arity(
                expr,
                {"append": 1, "remove": 1, "set": 2, "delete": 1}[method],
            )
            shown = expr.themed_method or method
            raise CodegenError(
                f"'{shown}' can only be used as a statement on its own line",
                expr,
            )

        taxonomy_method = self._taxonomy_method_call(expr, target_type, scope)
        if taxonomy_method is not None:
            return taxonomy_method

        if method in taxonomy.JSONB_STATEMENT_METHODS:
            shown = expr.themed_method or method
            raise CodegenError(
                f"'{shown}' can only be used as a statement on its own line",
                expr,
            )

        # method on a class instance -> classname_method(self, ...)
        if target_type in self._classes:
            info = self._classes[target_type]
            sig = info.methods.get(method)
            if sig is None:
                raise CodegenError(
                    f"class '{target_type}' has no method '{method}'", expr
                )
            self._expect_call_arity(
                expr,
                f"{target_type}.{method}",
                required=sig.required_params,
                total=len(sig.param_types),
            )
            args = [self._expr(expr.target, scope)]
            for i, a in enumerate(expr.args):
                target = sig.param_types[i] if i < len(sig.param_types) else NUMERIC
                args.append(self._coerce(a, target, scope))
            return f"{target_type}_{method}({', '.join(args)})"

        shown = expr.themed_method or method
        raise CodegenError(
            f"method '{shown}' cannot be used on this value "
            f"(value type: {target_type})",
            expr,
        )

    def _emit_direct_sql(self, stmt: nodes.Node) -> str:
        if isinstance(stmt, nodes.SqlSelect):
            return self._emit_select(stmt)
        if isinstance(stmt, nodes.SqlCreateTable):
            return self._emit_create_table(stmt)
        if isinstance(stmt, nodes.SqlInsert):
            return self._emit_insert(stmt)
        if isinstance(stmt, nodes.SqlUpdate):
            return self._emit_update(stmt)
        if isinstance(stmt, nodes.SqlDelete):
            return self._emit_delete_sql(stmt)
        if isinstance(stmt, nodes.SqlDropTable):
            return f"DROP TABLE {stmt.table}"
        if isinstance(stmt, nodes.SqlTruncateTable):
            return f"TRUNCATE TABLE {stmt.table}"
        if isinstance(stmt, nodes.SqlAlterTable):
            return self._emit_alter_table(stmt)
        if isinstance(stmt, nodes.SqlCreateIndex):
            unique = "UNIQUE " if stmt.unique else ""
            return (
                f"CREATE {unique}INDEX {stmt.name} ON {stmt.table} "
                f"({', '.join(stmt.columns)})"
            )
        if isinstance(stmt, nodes.SqlDropIndex):
            return f"DROP INDEX {stmt.name}"
        if isinstance(stmt, nodes.SqlCreateView):
            if stmt.query is None:
                raise CodegenError("CREATE VIEW requires a SELECT query", stmt)
            return f"CREATE VIEW {stmt.name} AS\n{self._emit_select(stmt.query)}"
        if isinstance(stmt, nodes.SqlDropView):
            return f"DROP VIEW {stmt.name}"
        if isinstance(stmt, nodes.SqlCreateDatabase):
            return f"CREATE DATABASE {stmt.name}"
        if isinstance(stmt, nodes.SqlDropDatabase):
            return f"DROP DATABASE {stmt.name}"
        raise CodegenError(
            f"the SQL generator does not support this top-level construct: {type(stmt).__name__}",
            stmt,
        )

    def _emit_create_table(self, stmt: nodes.SqlCreateTable) -> str:
        if stmt.table is None:
            raise CodegenError("CREATE TABLE requires a table name", stmt)
        cols = ",\n  ".join(self._emit_column_def(col, stmt) for col in stmt.columns)
        return f"CREATE TABLE {stmt.table.name} (\n  {cols}\n)"

    def _emit_column_def(self, col: nodes.SqlColumnDef, stmt: nodes.Node) -> str:
        parts = [col.name, self._sql_type(col.type_ref, stmt)]
        for constraint in col.constraints:
            if constraint == "not_null":
                parts.append("NOT NULL")
            elif constraint == "unique":
                parts.append("UNIQUE")
            elif constraint == "primary_key":
                parts.append("PRIMARY KEY")
            else:
                raise CodegenError(f"unknown column constraint: {constraint}", stmt)
        if col.check is not None:
            parts.append(f"CHECK {self._query_expr(col.check)}")
        return " ".join(parts)

    def _emit_insert(self, stmt: nodes.SqlInsert) -> str:
        columns = f" ({', '.join(stmt.columns)})" if stmt.columns else ""
        values = ", ".join(self._query_expr(value) for value in stmt.values)
        return f"INSERT INTO {stmt.table}{columns} VALUES ({values})"

    def _emit_update(self, stmt: nodes.SqlUpdate) -> str:
        assignments = ", ".join(
            f"{item.name} = {self._query_expr(item.value)}" for item in stmt.assignments
        )
        sql = f"UPDATE {stmt.table} SET {assignments}"
        if stmt.where is not None:
            sql += f" WHERE {self._query_expr(stmt.where)}"
        return sql

    def _emit_delete_sql(self, stmt: nodes.SqlDelete) -> str:
        sql = f"DELETE FROM {stmt.table}"
        if stmt.where is not None:
            sql += f" WHERE {self._query_expr(stmt.where)}"
        return sql

    def _emit_alter_table(self, stmt: nodes.SqlAlterTable) -> str:
        if stmt.action == "add_column":
            if stmt.type_ref is None:
                raise CodegenError("ADD COLUMN requires a type", stmt)
            return (
                f"ALTER TABLE {stmt.table} ADD COLUMN {stmt.column} "
                f"{self._sql_type(stmt.type_ref, stmt)}"
            )
        if stmt.action == "drop_column":
            return f"ALTER TABLE {stmt.table} DROP COLUMN {stmt.column}"
        if stmt.action == "alter_column":
            if stmt.type_ref is None:
                raise CodegenError("ALTER COLUMN requires a type", stmt)
            return (
                f"ALTER TABLE {stmt.table} ALTER COLUMN {stmt.column} TYPE "
                f"{self._sql_type(stmt.type_ref, stmt)}"
            )
        raise CodegenError(f"unknown ALTER TABLE operation: {stmt.action}", stmt)

    def _emit_select(self, stmt: nodes.SqlSelect) -> str:
        if stmt.table is None:
            raise CodegenError("SELECT query requires FROM", stmt)
        select_prefix = "SELECT DISTINCT" if stmt.distinct else "SELECT"
        lines = [
            f"{select_prefix} "
            + ", ".join(self._query_select_item(item) for item in stmt.items),
            f"FROM {self._query_table(stmt.table)}",
        ]
        for join in stmt.joins:
            lines.append(
                f"{join.join_type} {self._query_table(join.table)} "
                f"ON {self._query_expr(join.condition)}"
            )
        if stmt.where is not None:
            lines.append(f"WHERE {self._query_expr(stmt.where)}")
        if stmt.group_by:
            lines.append(
                "GROUP BY " + ", ".join(self._query_expr(e) for e in stmt.group_by)
            )
        if stmt.having is not None:
            lines.append(f"HAVING {self._query_expr(stmt.having)}")
        if stmt.order_by:
            lines.append(
                "ORDER BY "
                + ", ".join(
                    f"{self._query_expr(item.expr)} {item.direction.upper()}"
                    for item in stmt.order_by
                )
            )
        if stmt.limit is not None:
            lines.append(f"LIMIT {self._query_expr(stmt.limit)}")
        return "\n".join(lines)

    def _query_select_item(self, item: nodes.SqlSelectItem) -> str:
        sql = self._query_expr(item.expr)
        if item.alias:
            return f"{sql} AS {item.alias}"
        return sql

    def _query_table(self, table: nodes.SqlTableRef) -> str:
        if table.alias:
            return f"{table.name} AS {table.alias}"
        return table.name

    def _sql_in_values(self, expr: nodes.Node) -> str:
        if isinstance(expr, nodes.ListLiteral):
            return "(" + ", ".join(self._query_expr(item) for item in expr.elements) + ")"
        return self._query_expr(expr)

    def _query_expr(self, expr: nodes.Node) -> str:
        if isinstance(expr, nodes.Identifier):
            if expr.name in ("none", "null"):
                return "NULL"
            return expr.name
        if isinstance(expr, nodes.Star):
            return "*"
        if isinstance(expr, nodes.Literal):
            return self._literal(expr)
        if isinstance(expr, nodes.ListLiteral):
            if not expr.elements:
                return "'[]'::jsonb"
            return (
                "jsonb_build_array("
                + ", ".join(self._query_expr(item) for item in expr.elements)
                + ")"
            )
        if isinstance(expr, nodes.DictLiteral):
            if not expr.entries:
                return "'{}'::jsonb"
            parts: list[str] = []
            for key, value in expr.entries:
                parts.append(self._query_expr(key))
                parts.append(self._query_expr(value))
            return f"jsonb_build_object({', '.join(parts)})"
        if isinstance(expr, nodes.Attribute):
            return f"{self._query_expr(expr.target)}.{expr.name}"
        if isinstance(expr, nodes.BinaryOp):
            if expr.op in ("==", "!="):
                for side, other in ((expr.left, expr.right), (expr.right, expr.left)):
                    if _is_query_null(side):
                        other_sql = self._query_expr(other)
                        return (
                            f"({other_sql} IS NULL)"
                            if expr.op == "=="
                            else f"({other_sql} IS NOT NULL)"
                        )
            if expr.op in ("and", "or"):
                op = expr.op.upper()
            elif expr.op == "==":
                op = "="
            elif expr.op == "!=":
                op = "<>"
            elif expr.op in ("is", "is not"):
                op = expr.op.upper()
            elif expr.op == "like":
                op = "LIKE"
            elif expr.op == "in":
                return (
                    f"({self._query_expr(expr.left)} "
                    f"IN {self._sql_in_values(expr.right)})"
                )
            else:
                op = expr.op
            return f"({self._query_expr(expr.left)} {op} {self._query_expr(expr.right)})"
        if isinstance(expr, nodes.UnaryOp):
            if expr.op == "not":
                return f"(NOT {self._query_expr(expr.operand)})"
            return f"(-{self._query_expr(expr.operand)})"
        if isinstance(expr, nodes.BetweenOp):
            op = "NOT BETWEEN" if expr.negated else "BETWEEN"
            return (
                f"({self._query_expr(expr.expr)} {op} "
                f"{self._query_expr(expr.lower)} AND {self._query_expr(expr.upper)})"
            )
        if isinstance(expr, nodes.ConditionalExpr):
            return (
                f"(CASE WHEN {self._query_expr(expr.condition)} "
                f"THEN {self._query_expr(expr.then_expr)} "
                f"ELSE {self._query_expr(expr.else_expr)} END)"
            )
        if isinstance(expr, nodes.Call):
            name = _callee_name(expr)
            if name is None:
                raise CodegenError("SQL sorgusunda yalnizca isimle cagri yapilabilir", expr)
            args = [self._query_expr(arg) for arg in expr.args]
            spec = taxonomy.SQL_FUNCTIONS.get(name)
            if spec is not None:
                self._expect_taxonomy_arity(expr, name, spec.min_args, spec.max_args)
                return spec.render(name, args)
            return f"{name}({', '.join(args)})"
        raise CodegenError(
            f"this expression is not supported in a SQL query: {type(expr).__name__}", expr
        )

    def _emit_taxonomy_function(
        self, name: str, expr: nodes.Call, scope: dict[str, str]
    ) -> str:
        spec = taxonomy.SQL_FUNCTIONS[name]
        self._expect_taxonomy_arity(expr, name, spec.min_args, spec.max_args)
        args = self._coerce_taxonomy_args(expr.args, spec, scope)
        return spec.render(name, args)

    def _taxonomy_method_call(
        self, expr: nodes.MethodCall, target_type: str, scope: dict[str, str]
    ) -> str | None:
        method = expr.method
        if target_type == TEXT and method in taxonomy.TEXT_METHODS:
            spec = taxonomy.TEXT_METHODS[method]
        elif target_type in (JSONB, UNKNOWN) and method in taxonomy.JSONB_EXPR_METHODS:
            spec = taxonomy.JSONB_EXPR_METHODS[method]
        else:
            return None

        self._expect_taxonomy_arity(expr, method, spec.min_args, spec.max_args)
        target = self._coerce(expr.target, spec.target_type, scope)
        args = self._coerce_taxonomy_args(expr.args, spec, scope)
        return spec.render(target, args)

    def _coerce_taxonomy_args(
        self,
        args: list[nodes.Node],
        spec: taxonomy.SqlCallSpec | taxonomy.SqlMethodSpec,
        scope: dict[str, str],
    ) -> list[str]:
        return [self._coerce(arg, spec.arg_type(i), scope) for i, arg in enumerate(args)]

    def _expect_taxonomy_arity(
        self,
        expr: nodes.Call | nodes.MethodCall,
        name: str,
        required: int,
        total: int | None,
    ) -> None:
        actual = len(expr.args)
        if actual >= required and (total is None or actual <= total):
            return
        expected = (
            f"{required}+"
            if total is None
            else str(total)
            if required == total
            else f"{required}-{total}"
        )
        raise CodegenError(
            f"'{name}' takes {expected} arguments, {actual} given",
            expr,
        )

    def _expect_call_arity(
        self,
        expr: nodes.Call | nodes.MethodCall,
        name: str,
        *,
        required: int,
        total: int,
    ) -> None:
        actual = len(expr.args)
        if required <= actual <= total:
            return
        expected = str(total) if required == total else f"{required}-{total}"
        raise CodegenError(
            f"'{name}' takes {expected} arguments, {actual} given",
            expr,
        )

    def _expect_method_arity(self, expr: nodes.MethodCall, expected: int) -> None:
        actual = len(expr.args)
        if actual == expected:
            return
        shown = expr.themed_method or expr.method
        raise CodegenError(
            f"'{shown}' takes {expected} arguments, {actual} given",
            expr,
        )

    def _print_args(self, args: list[nodes.Node], scope: dict[str, str]) -> str:
        if not args:
            return "''"
        parts: list[str] = []
        for a in args:
            t = self._infer(a, scope)
            sql = self._expr(a, scope)
            if t == TEXT:
                part = sql
            elif t == BOOL:
                part = f"(CASE WHEN {sql} THEN 'True' ELSE 'False' END)"
            elif t in (NUMERIC, INTEGER):
                part = f"({sql})::text"
            elif t == JSONB:
                part = f"_cv_str({sql})"
            elif t in self._classes:
                part = f"({sql})::text"
            else:
                part = f"({sql})::text"
            parts.append(f"coalesce({part}, 'None')")
        return " || ' ' || ".join(parts)

    # -------------------------------------------------------------- typing

    def _infer(self, expr: nodes.Node, scope: dict[str, str]) -> str:
        if isinstance(expr, nodes.Identifier):
            return scope.get(expr.name, UNKNOWN)
        if isinstance(expr, nodes.Literal):
            return {
                "int": NUMERIC,
                "float": NUMERIC,
                "str": TEXT,
                "bool": BOOL,
                "none": UNKNOWN,
            }[expr.literal_type]
        if isinstance(expr, (nodes.ListLiteral, nodes.DictLiteral)):
            return JSONB
        if isinstance(expr, nodes.BinaryOp):
            if expr.op in (
                "and",
                "or",
                "==",
                "!=",
                "<",
                "<=",
                ">",
                ">=",
                "is",
                "is not",
                "in",
                "like",
            ):
                return BOOL
            if expr.op == "+":
                lt = self._infer(expr.left, scope)
                rt = self._infer(expr.right, scope)
                return TEXT if TEXT in (lt, rt) else NUMERIC
            return NUMERIC
        if isinstance(expr, nodes.UnaryOp):
            return BOOL if expr.op == "not" else NUMERIC
        if isinstance(expr, nodes.AssignmentExpr):
            return UNKNOWN
        if isinstance(expr, nodes.LambdaExpr):
            return UNKNOWN
        if isinstance(expr, nodes.ConditionalExpr):
            then_type = self._infer(expr.then_expr, scope)
            else_type = self._infer(expr.else_expr, scope)
            if then_type == else_type:
                return then_type
            if TEXT in (then_type, else_type):
                return TEXT
            if then_type == UNKNOWN:
                return else_type
            if else_type == UNKNOWN:
                return then_type
            return UNKNOWN
        if isinstance(expr, nodes.BetweenOp):
            return BOOL
        if isinstance(expr, (nodes.YieldExpr, nodes.AwaitExpr)):
            return UNKNOWN
        if isinstance(expr, nodes.Star):
            return UNKNOWN
        if isinstance(expr, nodes.Call):
            name = _callee_name(expr)
            if name == "len":
                return INTEGER
            if name == "print":
                return VOID
            if name in self._classes:
                return name
            if name in self._functions:
                return self._functions[name].return_type
            if name in taxonomy.SQL_FUNCTIONS:
                return taxonomy.SQL_FUNCTIONS[name].return_type
            return UNKNOWN
        if isinstance(expr, nodes.MethodCall):
            if expr.method == "contains":
                return BOOL
            if expr.method in ("get", "keys", "values", "append", "remove", "set", "delete"):
                return JSONB
            target_type = self._infer(expr.target, scope)
            if target_type == TEXT and expr.method in taxonomy.TEXT_METHODS:
                return taxonomy.TEXT_METHODS[expr.method].return_type
            if target_type in (JSONB, UNKNOWN):
                if expr.method in taxonomy.JSONB_EXPR_METHODS:
                    return taxonomy.JSONB_EXPR_METHODS[expr.method].return_type
                if expr.method in taxonomy.JSONB_STATEMENT_METHODS:
                    return taxonomy.JSONB_STATEMENT_METHODS[expr.method].return_type
            if target_type in self._classes:
                sig = self._classes[target_type].methods.get(expr.method)
                if sig:
                    return sig.return_type
            return UNKNOWN
        if isinstance(expr, nodes.Index):
            return JSONB
        if isinstance(expr, nodes.Attribute):
            return self._attribute_type(expr, scope)
        return UNKNOWN

    def _attribute_type(self, expr: nodes.Attribute, scope: dict[str, str]) -> str:
        target_type = self._infer(expr.target, scope)
        if target_type in self._classes:
            f = self._classes[target_type].fields.get(expr.name)
            if f is None:
                raise CodegenError(
                    f"class '{target_type}' has no field '{expr.name}'", expr
                )
            return f[0]
        return UNKNOWN

    def _sql_type(self, type_ref: nodes.TypeRef, node: nodes.Node) -> str:
        if type_ref.name in dialect.TYPE_MAP:
            return dialect.TYPE_MAP[type_ref.name]
        if type_ref.name in self._classes:
            return type_ref.name
        raise CodegenError(f"unknown type in the SQL target: '{type_ref.name}'", node)

    # --------------------------------------------------------------- casts

    def _coerce(self, expr: nodes.Node, target: str, scope: dict[str, str]) -> str:
        actual = self._infer(expr, scope)
        sql = self._expr(expr, scope)

        if target == actual or target == UNKNOWN:
            return sql
        if target == JSONB:
            return self._to_jsonb(expr, scope)
        if target in (NUMERIC, INTEGER):
            if actual == JSONB:
                sql = f"_cv_num({sql})"
            elif actual not in (NUMERIC, INTEGER):
                sql = f"({sql})::numeric"
            return f"({sql})::int" if target == INTEGER and actual != INTEGER else sql
        if target == TEXT:
            if actual == JSONB:
                return f"_cv_str({sql})"
            if actual == BOOL:
                return f"(CASE WHEN {sql} THEN 'True' ELSE 'False' END)"
            if actual in (NUMERIC, INTEGER):
                return f"({sql})::text"
            return f"({sql})::text" if actual == UNKNOWN else sql
        if target == BOOL:
            if actual == BOOL:
                return sql
            raise CodegenError(
                "a condition expression must be boolean — use an explicit comparison "
                "(e.g. x > 0)",
                expr,
            )
        if target in self._classes:
            return sql  # composite passthrough
        return sql

    def _coerce_int(self, expr: nodes.Node, scope: dict[str, str]) -> str:
        actual = self._infer(expr, scope)
        sql = self._expr(expr, scope)
        if actual == JSONB:
            return f"(_cv_num({sql}))::int"
        if actual == INTEGER:
            return sql
        return f"({sql})::int"

    def _to_jsonb(self, expr: nodes.Node, scope: dict[str, str]) -> str:
        actual = self._infer(expr, scope)
        sql = self._expr(expr, scope)
        if actual == JSONB:
            return sql
        if actual in (NUMERIC, INTEGER):
            return f"to_jsonb(({sql})::numeric)"
        if actual == TEXT:
            return f"to_jsonb(({sql})::text)"
        if actual == BOOL:
            return f"to_jsonb({sql})"
        if isinstance(expr, nodes.Literal) and expr.literal_type == "none":
            return "'null'::jsonb"
        return f"to_jsonb(({sql})::text)"

    def _condition(self, expr: nodes.Node, scope: dict[str, str]) -> str:
        return self._coerce(expr, BOOL, scope)


def _callee_name(expr: nodes.Call) -> str | None:
    if isinstance(expr.callee, nodes.Identifier):
        return expr.callee.name
    return None


def _is_range_call(expr: nodes.Node) -> bool:
    return isinstance(expr, nodes.Call) and _callee_name(expr) == "range"


def _is_query_null(expr: nodes.Node) -> bool:
    if isinstance(expr, nodes.Literal) and expr.literal_type == "none":
        return True
    return isinstance(expr, nodes.Identifier) and expr.name in ("none", "null")


def _sub_blocks(stmt: nodes.Node) -> list[list[nodes.Node]]:
    if isinstance(stmt, nodes.If):
        blocks = [stmt.then_body] + [b for _, b in stmt.elif_branches]
        if stmt.else_body is not None:
            blocks.append(stmt.else_body)
        return blocks
    if isinstance(stmt, (nodes.ForLoop, nodes.WhileLoop)):
        return [stmt.body]
    if isinstance(stmt, nodes.TryExcept):
        blocks = [stmt.try_body] + [h.body for h in stmt.handlers]
        if stmt.finally_body is not None:
            blocks.append(stmt.finally_body)
        return blocks
    return []
