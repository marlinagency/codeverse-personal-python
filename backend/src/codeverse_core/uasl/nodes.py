"""Universal Abstract Syntax Layer (UASL) node definitions.

The language-agnostic intermediate representation between the themed DSL and
target-language codegen modules. Every node carries a source Position so
codegen errors and semantic errors can point back at the user's own code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal as TypingLiteral


@dataclass(frozen=True)
class Position:
    line: int
    col: int

    @classmethod
    def unknown(cls) -> "Position":
        return cls(0, 0)


@dataclass
class Node:
    pos: Position


# --------------------------------------------------------------------------
# expressions
# --------------------------------------------------------------------------


@dataclass
class Identifier(Node):
    name: str
    #: what the user actually typed, when it differs (themed builtins etc.)
    themed_name: str | None = None


@dataclass
class Literal(Node):
    value: str | int | float | bool | None
    literal_type: TypingLiteral["str", "int", "float", "bool", "none"] = "str"


@dataclass
class ListLiteral(Node):
    elements: list[Node] = field(default_factory=list)


@dataclass
class DictLiteral(Node):
    entries: list[tuple[Node, Node]] = field(default_factory=list)


@dataclass
class BinaryOp(Node):
    op: str  # + - * / % == != < <= > >= and or
    left: Node = None  # type: ignore[assignment]
    right: Node = None  # type: ignore[assignment]


@dataclass
class UnaryOp(Node):
    op: str  # "-" | "not"
    operand: Node = None  # type: ignore[assignment]


@dataclass
class AssignmentExpr(Node):
    """``name := value`` inside an expression."""

    name: str = ""
    value: Node = None  # type: ignore[assignment]


@dataclass
class LambdaExpr(Node):
    params: list[str] = field(default_factory=list)
    body: Node = None  # type: ignore[assignment]


@dataclass
class ConditionalExpr(Node):
    condition: Node = None  # type: ignore[assignment]
    then_expr: Node = None  # type: ignore[assignment]
    else_expr: Node = None  # type: ignore[assignment]


@dataclass
class BetweenOp(Node):
    expr: Node = None  # type: ignore[assignment]
    lower: Node = None  # type: ignore[assignment]
    upper: Node = None  # type: ignore[assignment]
    negated: bool = False


@dataclass
class YieldExpr(Node):
    value: Node | None = None


@dataclass
class AwaitExpr(Node):
    value: Node = None  # type: ignore[assignment]


@dataclass
class Call(Node):
    callee: Node = None  # type: ignore[assignment]
    args: list[Node] = field(default_factory=list)


@dataclass
class MethodCall(Node):
    """``target.method(args)``.

    ``method`` is the canonical method name after theme resolution — for the
    known collection ops (append/remove/contains/get/set/keys/values/delete)
    codegen lowers this to language-native constructs; for other names it is
    treated as a user-defined method (Python: attribute call; SQL: a
    ``classname_method(self, ...)`` function when the target's class is known).
    """

    target: Node = None  # type: ignore[assignment]
    method: str = ""
    themed_method: str | None = None
    args: list[Node] = field(default_factory=list)


@dataclass
class Index(Node):
    """``target[key]`` — list indexing (0-based) or dict key access."""

    target: Node = None  # type: ignore[assignment]
    key: Node = None  # type: ignore[assignment]


@dataclass
class Attribute(Node):
    """``target.name`` without a call — field access on an object."""

    target: Node = None  # type: ignore[assignment]
    name: str = ""


@dataclass
class Star(Node):
    """``*`` in SQL select lists or count(*)."""

    pass


# --------------------------------------------------------------------------
# statements
# --------------------------------------------------------------------------


@dataclass
class TypeRef(Node):
    name: str = ""  # int | float | str | bool | list | dict | <class name>


@dataclass
class Assignment(Node):
    #: Identifier, Index, or Attribute
    target: Node = None  # type: ignore[assignment]
    value: Node = None  # type: ignore[assignment]
    annotation: TypeRef | None = None


@dataclass
class ExprStatement(Node):
    expr: Node = None  # type: ignore[assignment]


@dataclass
class Param(Node):
    name: str = ""
    type_ref: TypeRef | None = None
    default: Node | None = None


@dataclass
class FunctionDef(Node):
    name: str = ""
    params: list[Param] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)
    return_type: TypeRef | None = None
    async_def: bool = False


@dataclass
class Return(Node):
    value: Node | None = None


@dataclass
class If(Node):
    condition: Node = None  # type: ignore[assignment]
    then_body: list[Node] = field(default_factory=list)
    elif_branches: list[tuple[Node, list[Node]]] = field(default_factory=list)
    else_body: list[Node] | None = None


@dataclass
class ForLoop(Node):
    var_name: str = ""
    iterable: Node = None  # type: ignore[assignment]
    body: list[Node] = field(default_factory=list)


@dataclass
class WhileLoop(Node):
    condition: Node = None  # type: ignore[assignment]
    body: list[Node] = field(default_factory=list)


@dataclass
class Break(Node):
    pass


@dataclass
class Continue(Node):
    pass


@dataclass
class Pass(Node):
    pass


@dataclass
class Global(Node):
    names: list[str] = field(default_factory=list)


@dataclass
class Nonlocal(Node):
    names: list[str] = field(default_factory=list)


@dataclass
class Delete(Node):
    targets: list[Node] = field(default_factory=list)


@dataclass
class Assert(Node):
    condition: Node = None  # type: ignore[assignment]
    message: Node | None = None


@dataclass
class Raise(Node):
    value: Node | None = None


@dataclass
class WithItem:
    context: Node
    alias: str | None = None


@dataclass
class With(Node):
    items: list[WithItem] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)


@dataclass
class MatchCase:
    pattern: Node
    body: list[Node] = field(default_factory=list)


@dataclass
class Match(Node):
    subject: Node = None  # type: ignore[assignment]
    cases: list[MatchCase] = field(default_factory=list)


@dataclass
class ClassDef(Node):
    name: str = ""
    base: str | None = None
    fields: list[Param] = field(default_factory=list)
    methods: list[FunctionDef] = field(default_factory=list)


@dataclass
class Import(Node):
    module: str = ""
    alias: str | None = None


@dataclass
class FromImport(Node):
    module: str = ""
    names: list[tuple[str, str | None]] = field(default_factory=list)


@dataclass
class ExceptHandler(Node):
    bind_name: str | None = None
    body: list[Node] = field(default_factory=list)


@dataclass
class TryExcept(Node):
    try_body: list[Node] = field(default_factory=list)
    handlers: list[ExceptHandler] = field(default_factory=list)
    finally_body: list[Node] | None = None


@dataclass
class SqlSelectItem:
    expr: Node
    alias: str | None = None


@dataclass
class SqlTableRef:
    name: str
    alias: str | None = None


@dataclass
class SqlJoin:
    join_type: str
    table: SqlTableRef
    condition: Node


@dataclass
class SqlOrderItem:
    expr: Node
    direction: TypingLiteral["asc", "desc"] = "asc"


@dataclass
class SqlColumnDef:
    name: str
    type_ref: TypeRef
    constraints: list[str] = field(default_factory=list)
    check: Node | None = None


@dataclass
class SqlAssignment:
    name: str
    value: Node


@dataclass
class SqlSelect(Node):
    items: list[SqlSelectItem] = field(default_factory=list)
    table: SqlTableRef | None = None
    distinct: bool = False
    joins: list[SqlJoin] = field(default_factory=list)
    where: Node | None = None
    group_by: list[Node] = field(default_factory=list)
    having: Node | None = None
    order_by: list[SqlOrderItem] = field(default_factory=list)
    limit: Node | None = None


@dataclass
class SqlCreateTable(Node):
    table: SqlTableRef | None = None
    columns: list[SqlColumnDef] = field(default_factory=list)


@dataclass
class SqlInsert(Node):
    table: str = ""
    columns: list[str] = field(default_factory=list)
    values: list[Node] = field(default_factory=list)


@dataclass
class SqlUpdate(Node):
    table: str = ""
    assignments: list[SqlAssignment] = field(default_factory=list)
    where: Node | None = None


@dataclass
class SqlDelete(Node):
    table: str = ""
    where: Node | None = None


@dataclass
class SqlDropTable(Node):
    table: str = ""


@dataclass
class SqlTruncateTable(Node):
    table: str = ""


@dataclass
class SqlAlterTable(Node):
    table: str = ""
    action: str = ""
    column: str = ""
    type_ref: TypeRef | None = None


@dataclass
class SqlCreateIndex(Node):
    name: str = ""
    table: str = ""
    columns: list[str] = field(default_factory=list)
    unique: bool = False


@dataclass
class SqlDropIndex(Node):
    name: str = ""


@dataclass
class SqlCreateView(Node):
    name: str = ""
    query: SqlSelect | None = None


@dataclass
class SqlDropView(Node):
    name: str = ""


@dataclass
class SqlCreateDatabase(Node):
    name: str = ""


@dataclass
class SqlDropDatabase(Node):
    name: str = ""


@dataclass
class Program(Node):
    body: list[Node] = field(default_factory=list)
