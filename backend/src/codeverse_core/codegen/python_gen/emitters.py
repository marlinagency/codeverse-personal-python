"""UASL -> Python source emission."""

from __future__ import annotations

from codeverse_core.codegen.base import CodegenError
from codeverse_core.uasl import nodes

_INDENT = "    "

#: canonical collection ops that only make sense as statements
_STATEMENT_ONLY_METHODS = frozenset({"set", "delete", "append", "remove"})


class PythonEmitter:
    def __init__(self) -> None:
        self._lines: list[str] = []
        self._depth = 0

    # ------------------------------------------------------------- output

    def emit_program(self, program: nodes.Program) -> str:
        for stmt in program.body:
            self._emit_stmt(stmt)
        return "\n".join(self._lines) + "\n"

    def _line(self, text: str) -> None:
        self._lines.append(f"{_INDENT * self._depth}{text}" if text else "")

    # ---------------------------------------------------------- statements

    def _emit_block(self, body: list[nodes.Node]) -> None:
        self._depth += 1
        if not body:
            self._line("pass")
        for stmt in body:
            self._emit_stmt(stmt)
        self._depth -= 1

    def _emit_stmt(self, stmt: nodes.Node) -> None:
        if isinstance(stmt, nodes.Assignment):
            target = self._expr(stmt.target)
            self._line(f"{target} = {self._expr(stmt.value)}")
        elif isinstance(stmt, nodes.ExprStatement):
            self._line(self._expr_statement(stmt.expr))
        elif isinstance(stmt, nodes.FunctionDef):
            self._emit_function(stmt)
        elif isinstance(stmt, nodes.ClassDef):
            self._emit_class(stmt)
        elif isinstance(stmt, nodes.Return):
            if stmt.value is None:
                self._line("return")
            else:
                self._line(f"return {self._expr(stmt.value)}")
        elif isinstance(stmt, nodes.If):
            self._line(f"if {self._expr(stmt.condition)}:")
            self._emit_block(stmt.then_body)
            for cond, body in stmt.elif_branches:
                self._line(f"elif {self._expr(cond)}:")
                self._emit_block(body)
            if stmt.else_body is not None:
                self._line("else:")
                self._emit_block(stmt.else_body)
        elif isinstance(stmt, nodes.ForLoop):
            self._line(f"for {stmt.var_name} in {self._expr(stmt.iterable)}:")
            self._emit_block(stmt.body)
        elif isinstance(stmt, nodes.WhileLoop):
            self._line(f"while {self._expr(stmt.condition)}:")
            self._emit_block(stmt.body)
        elif isinstance(stmt, nodes.Break):
            self._line("break")
        elif isinstance(stmt, nodes.Continue):
            self._line("continue")
        elif isinstance(stmt, nodes.Pass):
            self._line("pass")
        elif isinstance(stmt, nodes.Global):
            self._line(f"global {', '.join(stmt.names)}")
        elif isinstance(stmt, nodes.Nonlocal):
            self._line(f"nonlocal {', '.join(stmt.names)}")
        elif isinstance(stmt, nodes.Delete):
            self._line("del " + ", ".join(self._expr(t) for t in stmt.targets))
        elif isinstance(stmt, nodes.Assert):
            if stmt.message is None:
                self._line(f"assert {self._expr(stmt.condition)}")
            else:
                self._line(
                    f"assert {self._expr(stmt.condition)}, {self._expr(stmt.message)}"
                )
        elif isinstance(stmt, nodes.Raise):
            if stmt.value is None:
                self._line("raise")
            else:
                value = self._expr(stmt.value)
                self._line(
                    f"raise {value}" if isinstance(stmt.value, nodes.Call) else f"raise Exception({value})"
                )
        elif isinstance(stmt, nodes.Import):
            if stmt.alias:
                self._line(f"import {stmt.module} as {stmt.alias}")
            else:
                self._line(f"import {stmt.module}")
        elif isinstance(stmt, nodes.FromImport):
            names = ", ".join(
                f"{name} as {alias}" if alias else name for name, alias in stmt.names
            )
            self._line(f"from {stmt.module} import {names}")
        elif isinstance(stmt, nodes.TryExcept):
            self._emit_try(stmt)
        elif isinstance(stmt, nodes.With):
            items = ", ".join(
                f"{self._expr(item.context)} as {item.alias}"
                if item.alias
                else self._expr(item.context)
                for item in stmt.items
            )
            self._line(f"with {items}:")
            self._emit_block(stmt.body)
        elif isinstance(stmt, nodes.Match):
            self._line(f"match {self._expr(stmt.subject)}:")
            self._depth += 1
            for case in stmt.cases:
                self._line(f"case {self._pattern(case.pattern)}:")
                self._emit_block(case.body)
            self._depth -= 1
        elif isinstance(
            stmt,
            (
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
            ),
        ):
            raise CodegenError("SQL sorgu ifadeleri Python hedefinde desteklenmiyor", stmt)
        else:
            raise CodegenError(
                f"Python üretici bu yapıyı desteklemiyor: {type(stmt).__name__}", stmt
            )

    def _emit_function(self, fn: nodes.FunctionDef, in_class: bool = False) -> None:
        params: list[str] = ["self"] if in_class else []
        for p in fn.params:
            if p.default is not None:
                params.append(f"{p.name}={self._expr(p.default)}")
            else:
                params.append(p.name)
        prefix = "async " if fn.async_def else ""
        self._line(f"{prefix}def {fn.name}({', '.join(params)}):")
        self._emit_block(fn.body)

    def _emit_class(self, cls: nodes.ClassDef) -> None:
        head = f"class {cls.name}({cls.base}):" if cls.base else f"class {cls.name}:"
        self._line(head)
        self._depth += 1

        if cls.fields:
            params = ["self"]
            for f in cls.fields:
                params.append(f"{f.name}={self._expr(f.default)}" if f.default else f.name)
            self._line(f"def __init__({', '.join(params)}):")
            self._depth += 1
            for f in cls.fields:
                self._line(f"self.{f.name} = {f.name}")
            self._depth -= 1
        elif not cls.methods:
            self._line("pass")

        for method in cls.methods:
            self._emit_function(method, in_class=True)
        self._depth -= 1

    def _emit_try(self, stmt: nodes.TryExcept) -> None:
        if len(stmt.handlers) > 1:
            raise CodegenError(
                "birden fazla hata yakalama bloğu desteklenmiyor — tek blok kullanın",
                stmt.handlers[1],
            )
        self._line("try:")
        self._emit_block(stmt.try_body)
        for handler in stmt.handlers:
            if handler.bind_name:
                # bind the MESSAGE, not the exception object — the DSL's
                # error binding is a string in every target language (SQL
                # binds SQLERRM), so Python matches with str(e)
                self._line(f"except Exception as {handler.bind_name}:")
                self._depth += 1
                self._line(f"{handler.bind_name} = str({handler.bind_name})")
                self._depth -= 1
            else:
                self._line("except Exception:")
            self._emit_block(handler.body)
        if stmt.finally_body is not None:
            self._line("finally:")
            self._emit_block(stmt.finally_body)

    def _expr_statement(self, expr: nodes.Node) -> str:
        """Statement-position expressions: collection mutations get their
        native statement forms here (``d[k] = v``, ``del d[k]``, ...)."""
        if isinstance(expr, nodes.MethodCall):
            target = self._expr(expr.target)
            if expr.method == "set" and len(expr.args) == 2:
                return f"{target}[{self._expr(expr.args[0])}] = {self._expr(expr.args[1])}"
            if expr.method == "delete" and len(expr.args) == 1:
                return f"del {target}[{self._expr(expr.args[0])}]"
        return self._expr(expr)

    # --------------------------------------------------------- expressions

    def _expr(self, expr: nodes.Node) -> str:
        if isinstance(expr, nodes.Identifier):
            return expr.name
        if isinstance(expr, nodes.Literal):
            return _literal(expr)
        if isinstance(expr, nodes.ListLiteral):
            return "[" + ", ".join(self._expr(e) for e in expr.elements) + "]"
        if isinstance(expr, nodes.DictLiteral):
            entries = ", ".join(
                f"{self._expr(k)}: {self._expr(v)}" for k, v in expr.entries
            )
            return "{" + entries + "}"
        if isinstance(expr, nodes.BinaryOp):
            none_comparison = self._none_comparison(expr)
            if none_comparison is not None:
                return none_comparison
            if expr.op == "like":
                raise CodegenError("'like' yalnizca SQL hedefinde desteklenir", expr)
            return f"({self._expr(expr.left)} {expr.op} {self._expr(expr.right)})"
        if isinstance(expr, nodes.BetweenOp):
            target = self._expr(expr.expr)
            lower = self._expr(expr.lower)
            upper = self._expr(expr.upper)
            expr_sql = f"({lower} <= {target} <= {upper})"
            return f"(not {expr_sql})" if expr.negated else expr_sql
        if isinstance(expr, nodes.UnaryOp):
            if expr.op == "not":
                return f"(not {self._expr(expr.operand)})"
            return f"(-{self._expr(expr.operand)})"
        if isinstance(expr, nodes.AssignmentExpr):
            return f"({expr.name} := {self._expr(expr.value)})"
        if isinstance(expr, nodes.LambdaExpr):
            return f"(lambda {', '.join(expr.params)}: {self._expr(expr.body)})"
        if isinstance(expr, nodes.ConditionalExpr):
            return (
                f"({self._expr(expr.then_expr)} if {self._expr(expr.condition)} "
                f"else {self._expr(expr.else_expr)})"
            )
        if isinstance(expr, nodes.YieldExpr):
            if expr.value is None:
                return "(yield)"
            return f"(yield {self._expr(expr.value)})"
        if isinstance(expr, nodes.AwaitExpr):
            return f"(await {self._expr(expr.value)})"
        if isinstance(expr, nodes.Call):
            callee = self._expr(expr.callee)
            args = ", ".join(self._expr(a) for a in expr.args)
            return f"{callee}({args})"
        if isinstance(expr, nodes.MethodCall):
            return self._method_call(expr)
        if isinstance(expr, nodes.Index):
            return f"{self._expr(expr.target)}[{self._expr(expr.key)}]"
        if isinstance(expr, nodes.Attribute):
            return f"{self._expr(expr.target)}.{expr.name}"
        if isinstance(expr, nodes.Star):
            return "*"
        raise CodegenError(
            f"Python üretici bu ifadeyi desteklemiyor: {type(expr).__name__}", expr
        )

    def _pattern(self, expr: nodes.Node) -> str:
        if isinstance(expr, nodes.Identifier) and expr.name == "_":
            return "_"
        return self._expr(expr)

    def _method_call(self, expr: nodes.MethodCall) -> str:
        target = self._expr(expr.target)
        args = [self._expr(a) for a in expr.args]
        method = expr.method

        if method == "append" and len(args) == 1:
            return f"{target}.append({args[0]})"
        if method == "remove" and len(args) == 1:
            return f"{target}.remove({args[0]})"
        if method == "contains" and len(args) == 1:
            return f"({args[0]} in {target})"
        if method == "get" and len(args) == 1:
            return f"{target}.get({args[0]})"
        if method == "keys" and not args:
            return f"list({target}.keys())"
        if method == "values" and not args:
            return f"list({target}.values())"
        if method in ("set", "delete"):
            shown = expr.themed_method or method
            raise CodegenError(
                f"'{shown}' yalnızca kendi başına bir satır olarak kullanılabilir, "
                "bir ifadenin içinde değil",
                expr,
            )
        # user-defined method on an object
        return f"{target}.{method}({', '.join(args)})"

    def _none_comparison(self, expr: nodes.BinaryOp) -> str | None:
        if expr.op not in ("==", "!="):
            return None
        for side, other in ((expr.left, expr.right), (expr.right, expr.left)):
            if isinstance(side, nodes.Literal) and side.literal_type == "none":
                op = "is" if expr.op == "==" else "is not"
                return f"({self._expr(other)} {op} None)"
        return None


def _literal(lit: nodes.Literal) -> str:
    if lit.literal_type == "str":
        escaped = (
            str(lit.value)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            .replace("\r", "\\r")
        )
        return f'"{escaped}"'
    if lit.literal_type == "bool":
        return "True" if lit.value else "False"
    if lit.literal_type == "none":
        return "None"
    return str(lit.value)
