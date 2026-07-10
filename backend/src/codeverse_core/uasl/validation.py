"""Pre-codegen semantic validation of a UASL program.

Catches errors that are language-independent: use of undefined names,
``return`` outside a function, ``break``/``continue`` outside a loop,
duplicate function/class definitions. Language-specific restrictions (e.g.
SQL's top-level conditional rule) belong to the codegen modules.
"""

from __future__ import annotations

from dataclasses import dataclass

from codeverse_core.theme_mapping.taxonomy_prompts import extract_mappable
from codeverse_core.uasl import nodes


@dataclass(frozen=True)
class SemanticError:
    message: str
    line: int
    col: int


def validate_program(
    program: nodes.Program, known_globals: set[str] | frozenset[str] | None = None
) -> list[SemanticError]:
    checker = _Checker(known_globals or _KNOWN_GLOBALS)
    checker.check_block(program.body, scope=_Scope(), in_function=False, in_loop=False)
    return checker.errors


def known_globals_for_language(language: str) -> frozenset[str]:
    if language == "python":
        return _KNOWN_GLOBALS | _python_taxonomy_globals()
    if language == "sql":
        from codeverse_core.codegen.sql_gen.taxonomy import SQL_FUNCTIONS

        return _KNOWN_GLOBALS | frozenset(SQL_FUNCTIONS)
    return _KNOWN_GLOBALS


class _Scope:
    def __init__(self, parent: "_Scope | None" = None) -> None:
        self.parent = parent
        self.names: set[str] = set()

    def define(self, name: str) -> None:
        self.names.add(name)

    def is_defined(self, name: str) -> bool:
        scope: _Scope | None = self
        while scope is not None:
            if name in scope.names:
                return True
            scope = scope.parent
        return False


class _Checker:
    def __init__(self, known_globals: set[str] | frozenset[str]) -> None:
        self.errors: list[SemanticError] = []
        self.known_globals = known_globals

    def _error(self, message: str, node: nodes.Node) -> None:
        self.errors.append(SemanticError(message, node.pos.line, node.pos.col))

    def check_block(
        self,
        body: list[nodes.Node],
        scope: _Scope,
        in_function: bool,
        in_loop: bool,
    ) -> None:
        # hoist function/class names: mutual recursion and forward calls are legal
        for stmt in body:
            if isinstance(stmt, nodes.FunctionDef):
                if scope.is_defined(stmt.name):
                    self._error(f"'{stmt.name}' zaten tanımlı", stmt)
                self._define_user_name(stmt.name, stmt, scope)
            elif isinstance(stmt, nodes.ClassDef):
                if scope.is_defined(stmt.name):
                    self._error(f"'{stmt.name}' zaten tanımlı", stmt)
                self._define_user_name(stmt.name, stmt, scope)
            elif isinstance(stmt, nodes.Import):
                self._define_user_name(stmt.alias or stmt.module.split(".")[0], stmt, scope)
            elif isinstance(stmt, nodes.FromImport):
                for name, alias in stmt.names:
                    self._define_user_name(alias or name, stmt, scope)

        for stmt in body:
            self._check_stmt(stmt, scope, in_function, in_loop)

    def _check_stmt(
        self, stmt: nodes.Node, scope: _Scope, in_function: bool, in_loop: bool
    ) -> None:
        if isinstance(stmt, nodes.Assignment):
            self._check_expr(stmt.value, scope)
            if isinstance(stmt.target, nodes.Identifier):
                self._define_user_name(stmt.target.name, stmt.target, scope)
            else:
                self._check_expr(stmt.target, scope)
        elif isinstance(stmt, nodes.ExprStatement):
            self._check_expr(stmt.expr, scope)
        elif isinstance(stmt, nodes.FunctionDef):
            fn_scope = _Scope(scope)
            self._check_params(stmt.params)
            for p in stmt.params:
                self._define_user_name(p.name, p, fn_scope)
                if p.default is not None:
                    self._check_expr(p.default, scope)
            self.check_block(stmt.body, fn_scope, in_function=True, in_loop=False)
        elif isinstance(stmt, nodes.ClassDef):
            if stmt.base is not None and not scope.is_defined(stmt.base):
                self._error(f"temel sınıf '{stmt.base}' tanımlı değil", stmt)
            self._check_class_members(stmt)
            for method in stmt.methods:
                m_scope = _Scope(scope)
                m_scope.define("self")
                self._check_params(method.params)
                for p in method.params:
                    self._define_user_name(p.name, p, m_scope)
                self.check_block(method.body, m_scope, in_function=True, in_loop=False)
        elif isinstance(stmt, nodes.Return):
            if not in_function:
                self._error("fonksiyon dışında değer döndürülemez", stmt)
            if stmt.value is not None:
                self._check_expr(stmt.value, scope)
        elif isinstance(stmt, nodes.Pass):
            pass
        elif isinstance(stmt, (nodes.Global, nodes.Nonlocal)):
            pass
        elif isinstance(stmt, nodes.Delete):
            for target in stmt.targets:
                self._check_expr(target, scope)
        elif isinstance(stmt, nodes.Assert):
            self._check_expr(stmt.condition, scope)
            if stmt.message is not None:
                self._check_expr(stmt.message, scope)
        elif isinstance(stmt, nodes.Raise):
            if stmt.value is not None:
                self._check_expr(stmt.value, scope)
        elif isinstance(stmt, nodes.With):
            with_scope = _Scope(scope)
            for item in stmt.items:
                self._check_expr(item.context, scope)
                if item.alias:
                    self._define_user_name(item.alias, item, with_scope)
            self.check_block(stmt.body, with_scope, in_function, in_loop)
        elif isinstance(stmt, nodes.Match):
            self._check_expr(stmt.subject, scope)
            for case in stmt.cases:
                if not isinstance(case.pattern, nodes.Identifier):
                    self._check_expr(case.pattern, scope)
                self.check_block(case.body, _Scope(scope), in_function, in_loop)
        elif isinstance(stmt, nodes.If):
            self._check_expr(stmt.condition, scope)
            self.check_block(stmt.then_body, _Scope(scope), in_function, in_loop)
            for cond, body in stmt.elif_branches:
                self._check_expr(cond, scope)
                self.check_block(body, _Scope(scope), in_function, in_loop)
            if stmt.else_body is not None:
                self.check_block(stmt.else_body, _Scope(scope), in_function, in_loop)
        elif isinstance(stmt, nodes.ForLoop):
            self._check_expr(stmt.iterable, scope)
            loop_scope = _Scope(scope)
            self._define_user_name(stmt.var_name, stmt, loop_scope)
            self.check_block(stmt.body, loop_scope, in_function, in_loop=True)
        elif isinstance(stmt, nodes.WhileLoop):
            self._check_expr(stmt.condition, scope)
            self.check_block(stmt.body, _Scope(scope), in_function, in_loop=True)
        elif isinstance(stmt, (nodes.Break, nodes.Continue)):
            if not in_loop:
                kind = "break" if isinstance(stmt, nodes.Break) else "continue"
                self._error(f"döngü dışında '{kind}' kullanılamaz", stmt)
        elif isinstance(stmt, nodes.TryExcept):
            self.check_block(stmt.try_body, _Scope(scope), in_function, in_loop)
            for handler in stmt.handlers:
                h_scope = _Scope(scope)
                if handler.bind_name:
                    self._define_user_name(handler.bind_name, handler, h_scope)
                self.check_block(handler.body, h_scope, in_function, in_loop)
            if stmt.finally_body is not None:
                self.check_block(stmt.finally_body, _Scope(scope), in_function, in_loop)
        elif isinstance(stmt, nodes.Import):
            pass  # hoisted above
        elif isinstance(stmt, nodes.FromImport):
            pass  # hoisted above
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
            pass
        else:
            self._error(f"beklenmeyen ifade türü: {type(stmt).__name__}", stmt)

    def _check_params(self, params: list[nodes.Param]) -> None:
        seen: set[str] = set()
        default_seen = False
        for p in params:
            if p.name in seen:
                self._error(f"'{p.name}' parametresi iki kez tanımlanmış", p)
            seen.add(p.name)
            if p.default is not None:
                default_seen = True
            elif default_seen:
                self._error(
                    f"varsayılan değerli parametreden sonra zorunlu parametre "
                    f"gelemez ('{p.name}')",
                    p,
                )

    def _check_class_members(self, cls: nodes.ClassDef) -> None:
        seen_fields: set[str] = set()
        for f in cls.fields:
            if f.name in seen_fields:
                self._error(f"'{f.name}' alanı iki kez tanımlanmış", f)
            seen_fields.add(f.name)
        seen_methods: set[str] = set()
        for m in cls.methods:
            if m.name in seen_methods:
                self._error(f"'{m.name}' metodu iki kez tanımlanmış", m)
            seen_methods.add(m.name)

    def _define_user_name(self, name: str, node: nodes.Node, scope: _Scope) -> None:
        if name in self.known_globals:
            self._error(
                f"'{name}' yerlesik Python kavrami olarak ayrilmis; degisken adi olarak kullanilamaz",
                node,
            )
            return
        scope.define(name)

    def _check_expr(self, expr: nodes.Node, scope: _Scope) -> None:
        if isinstance(expr, nodes.Identifier):
            if not scope.is_defined(expr.name) and expr.name not in self.known_globals:
                shown = expr.themed_name or expr.name
                self._error(f"tanımsız isim: '{shown}'", expr)
        elif isinstance(expr, nodes.Literal):
            pass
        elif isinstance(expr, nodes.ListLiteral):
            for e in expr.elements:
                self._check_expr(e, scope)
        elif isinstance(expr, nodes.DictLiteral):
            for k, v in expr.entries:
                self._check_expr(k, scope)
                self._check_expr(v, scope)
        elif isinstance(expr, nodes.BinaryOp):
            self._check_expr(expr.left, scope)
            self._check_expr(expr.right, scope)
        elif isinstance(expr, nodes.UnaryOp):
            self._check_expr(expr.operand, scope)
        elif isinstance(expr, nodes.AssignmentExpr):
            self._check_expr(expr.value, scope)
            self._define_user_name(expr.name, expr, scope)
        elif isinstance(expr, nodes.LambdaExpr):
            lambda_scope = _Scope(scope)
            for p in expr.params:
                if p in self.known_globals:
                    self._error(
                        f"'{p}' yerlesik Python kavrami olarak ayrilmis; degisken adi olarak kullanilamaz",
                        expr,
                    )
                else:
                    lambda_scope.define(p)
            self._check_expr(expr.body, lambda_scope)
        elif isinstance(expr, nodes.ConditionalExpr):
            self._check_expr(expr.condition, scope)
            self._check_expr(expr.then_expr, scope)
            self._check_expr(expr.else_expr, scope)
        elif isinstance(expr, nodes.BetweenOp):
            self._check_expr(expr.expr, scope)
            self._check_expr(expr.lower, scope)
            self._check_expr(expr.upper, scope)
        elif isinstance(expr, nodes.YieldExpr):
            if expr.value is not None:
                self._check_expr(expr.value, scope)
        elif isinstance(expr, nodes.AwaitExpr):
            self._check_expr(expr.value, scope)
        elif isinstance(expr, nodes.Call):
            self._check_expr(expr.callee, scope)
            for a in expr.args:
                self._check_expr(a, scope)
        elif isinstance(expr, nodes.MethodCall):
            self._check_expr(expr.target, scope)
            for a in expr.args:
                self._check_expr(a, scope)
        elif isinstance(expr, nodes.Index):
            self._check_expr(expr.target, scope)
            self._check_expr(expr.key, scope)
        elif isinstance(expr, nodes.Attribute):
            self._check_expr(expr.target, scope)
        elif isinstance(expr, nodes.Star):
            pass


#: canonical builtins usable as bare names
_KNOWN_GLOBALS = frozenset({"print", "range", "len"})


def _python_taxonomy_globals() -> frozenset[str]:
    allowed_categories = {"builtin_functions", "exceptions"}
    return frozenset(
        concept.canonical_name
        for concept in extract_mappable("python")[0]
        if concept.category in allowed_categories
    )
