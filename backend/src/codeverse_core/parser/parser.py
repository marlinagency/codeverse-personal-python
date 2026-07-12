"""Recursive-descent parser: resolved token stream -> UASL.

One method per grammar production (see grammar.py). Error messages speak the
user's themed vocabulary: whenever the parser expects a keyword, it names the
THEMED token from the active dictionary, not the canonical one.
"""

from __future__ import annotations

from codeverse_core.concepts import DSL_TYPE_NAMES, UniversalConcept
from codeverse_core.lexer.tokens import Token, TokenType
from codeverse_core.parser.errors import ParseError
from codeverse_core.theme_mapping.dictionary import ThemeDictionary
from codeverse_core.uasl import nodes

_COMPARISON_OPS = {
    TokenType.EQ: "==",
    TokenType.NE: "!=",
    TokenType.LT: "<",
    TokenType.LE: "<=",
    TokenType.GT: ">",
    TokenType.GE: ">=",
}

_ADDITIVE_OPS = {TokenType.PLUS: "+", TokenType.MINUS: "-"}
_MULTIPLICATIVE_OPS = {TokenType.STAR: "*", TokenType.SLASH: "/", TokenType.PERCENT: "%"}
_SQL_JOIN_NAMES = {
    "join": "JOIN",
    "inner_join": "INNER JOIN",
    "left_join": "LEFT JOIN",
    "right_join": "RIGHT JOIN",
    "full_join": "FULL OUTER JOIN",
    "full_outer_join": "FULL OUTER JOIN",
    "outer_join": "FULL OUTER JOIN",
}
_SQL_CLAUSE_NAMES = frozenset(
    {
        "from",
        "where",
        "join",
        "inner_join",
        "left_join",
        "right_join",
        "full_join",
        "full_outer_join",
        "outer_join",
        "group_by",
        "having",
        "order_by",
        "limit",
        "set",
        "values",
        "on",
        "as",
    }
)


class Parser:
    def __init__(self, tokens: list[Token], dictionary: ThemeDictionary) -> None:
        self._tokens = tokens
        self._dictionary = dictionary
        self._pos = 0

    # ------------------------------------------------------------------ api

    def parse_program(self) -> nodes.Program:
        start = self._peek()
        body: list[nodes.Node] = []
        while not self._check(TokenType.EOF):
            body.append(self._parse_statement())
        return nodes.Program(pos=_pos_of(start), body=body)

    # ------------------------------------------------------------- helpers

    def _peek(self, offset: int = 0) -> Token:
        i = min(self._pos + offset, len(self._tokens) - 1)
        return self._tokens[i]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        if tok.type is not TokenType.EOF:
            self._pos += 1
        return tok

    def _check(self, *types: TokenType) -> bool:
        return self._peek().type in types

    def _match(self, *types: TokenType) -> Token | None:
        if self._check(*types):
            return self._advance()
        return None

    def _is_name(self, name: str, offset: int = 0) -> bool:
        tok = self._peek(offset)
        return tok.type is TokenType.NAME and tok.resolved_text == name

    def _match_name(self, name: str) -> Token | None:
        if self._is_name(name):
            return self._advance()
        return None

    def _expect_name_token(self, what: str) -> Token:
        return self._expect(TokenType.NAME, what)

    def _themed(self, concept: UniversalConcept) -> str:
        """The user's themed token for a concept — for error messages."""
        try:
            return f"'{self._dictionary.token_for(concept)}'"
        except KeyError:
            return f"'{concept.canonical}'"

    def _expect(self, ttype: TokenType, what: str) -> Token:
        tok = self._peek()
        if tok.type is not ttype:
            got = tok.themed_text or tok.type.name
            raise ParseError(
                f"expected {what}, found {got!r}", tok.line, tok.col
            )
        return self._advance()

    def _expect_newline(self) -> None:
        tok = self._peek()
        if tok.type is TokenType.NEWLINE:
            self._advance()
            return
        if tok.type in (TokenType.EOF, TokenType.DEDENT):
            return
        raise ParseError(
            f"expected end of line, found {tok.themed_text!r}", tok.line, tok.col
        )

    # ---------------------------------------------------------- statements

    def _parse_statement(self) -> nodes.Node:
        tok = self._peek()
        t = tok.type

        if self._is_name("async") and self._peek(1).type is TokenType.KW_FUNC:
            self._advance()
            return self._parse_func_def(async_def=True)
        if t is TokenType.KW_FUNC:
            return self._parse_func_def()
        if t is TokenType.KW_CLASS:
            return self._parse_class_def()
        if t is TokenType.KW_IF:
            return self._parse_if()
        if t is TokenType.KW_FOR:
            return self._parse_for()
        if t is TokenType.KW_WHILE:
            return self._parse_while()
        if t is TokenType.KW_TRY:
            return self._parse_try()
        if self._is_name("with"):
            return self._parse_with()
        if self._is_name("match"):
            return self._parse_match()

        stmt = self._parse_simple_statement()
        self._expect_newline()
        return stmt

    def _parse_simple_statement(self) -> nodes.Node:
        tok = self._peek()
        t = tok.type

        if t is TokenType.KW_RETURN:
            self._advance()
            value: nodes.Node | None = None
            if not self._check(TokenType.NEWLINE, TokenType.EOF, TokenType.DEDENT):
                value = self._parse_expr()
            return nodes.Return(pos=_pos_of(tok), value=value)

        if t is TokenType.KW_BREAK:
            self._advance()
            return nodes.Break(pos=_pos_of(tok))

        if t is TokenType.KW_CONTINUE:
            self._advance()
            return nodes.Continue(pos=_pos_of(tok))

        if t is TokenType.KW_IMPORT:
            self._advance()
            name = self._expect(TokenType.NAME, "a module name")
            module = name.resolved_text
            while self._match(TokenType.DOT):
                part = self._expect(TokenType.NAME, "a module name")
                module += "." + part.resolved_text
            alias = None
            if self._match_name("as"):
                alias = self._expect(TokenType.NAME, "an import alias").resolved_text
            return nodes.Import(pos=_pos_of(tok), module=module, alias=alias)

        if self._is_name("from"):
            return self._parse_from_import()

        if t is TokenType.KW_GLOBAL or self._is_name("global"):
            self._advance()
            return nodes.Global(pos=_pos_of(tok), names=self._parse_name_list())

        if t is TokenType.KW_NONLOCAL or self._is_name("nonlocal"):
            self._advance()
            return nodes.Nonlocal(pos=_pos_of(tok), names=self._parse_name_list())

        if t is TokenType.KW_DEL or self._is_name("del"):
            self._advance()
            return nodes.Delete(pos=_pos_of(tok), targets=self._parse_target_list())

        if t is TokenType.KW_ASSERT or self._is_name("assert"):
            self._advance()
            condition = self._parse_expr()
            message = self._parse_expr() if self._match(TokenType.COMMA) else None
            return nodes.Assert(pos=_pos_of(tok), condition=condition, message=message)

        if t is TokenType.KW_RAISE or self._is_name("raise"):
            self._advance()
            value = None
            if not self._check(TokenType.NEWLINE, TokenType.EOF, TokenType.DEDENT):
                value = self._parse_expr()
            return nodes.Raise(pos=_pos_of(tok), value=value)

        if self._is_name("pass"):
            self._advance()
            return nodes.Pass(pos=_pos_of(tok))

        if self._is_name("select"):
            return self._parse_sql_select()

        if self._is_name("create_table"):
            return self._parse_sql_create_table()

        if self._is_name("insert_into"):
            return self._parse_sql_insert()

        if self._is_name("update") and self._peek(1).type is TokenType.NAME:
            return self._parse_sql_update()

        if self._is_name("delete") and self._is_name("from", 1):
            return self._parse_sql_delete()

        if self._is_name("drop_table"):
            return self._parse_sql_drop_table()

        if self._is_name("truncate_table"):
            return self._parse_sql_truncate_table()

        if self._is_name("alter_table"):
            return self._parse_sql_alter_table()

        if self._is_name("create_index"):
            return self._parse_sql_create_index(unique=False)

        if self._is_name("create_unique_index"):
            return self._parse_sql_create_index(unique=True)

        if self._is_name("drop_index"):
            return self._parse_sql_drop_index()

        if self._is_name("create_view"):
            return self._parse_sql_create_view()

        if self._is_name("drop_view"):
            return self._parse_sql_drop_view()

        if self._is_name("create_database"):
            return self._parse_sql_create_database()

        if self._is_name("drop_database"):
            return self._parse_sql_drop_database()

        # assignment or bare expression
        expr = self._parse_expr()

        annotation: nodes.TypeRef | None = None
        if self._check(TokenType.COLON) and isinstance(expr, nodes.Identifier):
            colon = self._advance()
            annotation = self._parse_type_ref(colon)

        if self._check(TokenType.ASSIGN):
            assign_tok = self._advance()
            if not isinstance(expr, (nodes.Identifier, nodes.Index, nodes.Attribute)):
                raise ParseError(
                    "the left side of an assignment must be a name, index access, or attribute",
                    assign_tok.line,
                    assign_tok.col,
                )
            value = self._parse_expr()
            return nodes.Assignment(
                pos=_pos_of(tok), target=expr, value=value, annotation=annotation
            )

        if annotation is not None:
            raise ParseError(
                "a type-annotated variable must be assigned a value ('=' missing)",
                tok.line,
                tok.col,
            )

        return nodes.ExprStatement(pos=_pos_of(tok), expr=expr)

    def _parse_func_def(self, *, async_def: bool = False) -> nodes.FunctionDef:
        kw = self._advance()  # KW_FUNC
        name = self._expect(TokenType.NAME, "a function name")
        self._expect(TokenType.LPAREN, "'('")
        params = self._parse_params()
        self._expect(TokenType.RPAREN, "')'")

        return_type: nodes.TypeRef | None = None
        # optional return annotation: func f(a) : int  -- but ':' also opens
        # the block, so a return type must be a type name right after ':'
        # We use the form: func f(a): block  |  func f(a) : type : block is
        # ambiguous; instead return type uses '->' style with '-' '>'? Keep it
        # simple and unambiguous: type annotation comes before the block colon
        # only in parentheses form. We therefore do not support a separate
        # return-type syntax; SQL codegen infers it. (documented in grammar)
        body = self._parse_block("the function body")
        return nodes.FunctionDef(
            pos=_pos_of(kw),
            name=name.resolved_text,
            params=params,
            body=body,
            return_type=return_type,
            async_def=async_def,
        )

    def _parse_params(self) -> list[nodes.Param]:
        params: list[nodes.Param] = []
        if self._check(TokenType.RPAREN):
            return params
        while True:
            name = self._expect(TokenType.NAME, "a parameter name")
            type_ref: nodes.TypeRef | None = None
            default: nodes.Node | None = None
            if self._match(TokenType.COLON):
                type_ref = self._parse_type_ref(name)
            if self._match(TokenType.ASSIGN):
                default = self._parse_expr()
            params.append(
                nodes.Param(
                    pos=_pos_of(name),
                    name=name.resolved_text,
                    type_ref=type_ref,
                    default=default,
                )
            )
            if not self._match(TokenType.COMMA):
                break
            if self._check(TokenType.RPAREN):
                break
        return params

    def _parse_from_import(self) -> nodes.FromImport:
        start = self._advance()  # from
        module = self._parse_dotted_name("a module name")
        if self._peek().type is not TokenType.KW_IMPORT:
            tok = self._peek()
            raise ParseError("expected 'import'", tok.line, tok.col)
        self._advance()
        names: list[tuple[str, str | None]] = []
        while True:
            name = self._expect(TokenType.NAME, "an import name").resolved_text
            alias = None
            if self._match_name("as"):
                alias = self._expect(TokenType.NAME, "an import alias").resolved_text
            names.append((name, alias))
            if not self._match(TokenType.COMMA):
                break
        return nodes.FromImport(pos=_pos_of(start), module=module, names=names)

    def _parse_with(self) -> nodes.With:
        start = self._advance()  # with
        items: list[nodes.WithItem] = []
        while True:
            context = self._parse_expr()
            alias = None
            if self._match_name("as"):
                alias = self._expect(TokenType.NAME, "a with alias").resolved_text
            items.append(nodes.WithItem(context=context, alias=alias))
            if not self._match(TokenType.COMMA):
                break
        body = self._parse_block("the with body")
        return nodes.With(pos=_pos_of(start), items=items, body=body)

    def _parse_match(self) -> nodes.Match:
        start = self._advance()  # match
        subject = self._parse_expr()
        self._expect(TokenType.COLON, "':'")
        self._expect(TokenType.NEWLINE, "a new line")
        tok = self._peek()
        if tok.type is not TokenType.INDENT:
            raise ParseError("match requires indented case blocks", tok.line, tok.col)
        self._advance()
        cases: list[nodes.MatchCase] = []
        while not self._check(TokenType.DEDENT, TokenType.EOF):
            case_tok = self._expect_sql_name("case")
            pattern = self._parse_expr()
            body = self._parse_block("the case body")
            cases.append(nodes.MatchCase(pattern=pattern, body=body))
            if case_tok.type is TokenType.EOF:
                break
        self._match(TokenType.DEDENT)
        if not cases:
            raise ParseError("match must contain at least one case", start.line, start.col)
        return nodes.Match(pos=_pos_of(start), subject=subject, cases=cases)

    def _parse_name_list(self) -> list[str]:
        names = [self._expect(TokenType.NAME, "a name").resolved_text]
        while self._match(TokenType.COMMA):
            names.append(self._expect(TokenType.NAME, "a name").resolved_text)
        return names

    def _parse_target_list(self) -> list[nodes.Node]:
        targets = [self._parse_postfix()]
        while self._match(TokenType.COMMA):
            targets.append(self._parse_postfix())
        for target in targets:
            if not isinstance(target, (nodes.Identifier, nodes.Index, nodes.Attribute)):
                raise ParseError(
                    "a delete target must be a name, index access, or attribute",
                    target.pos.line,
                    target.pos.col,
                )
        return targets

    def _parse_type_ref(self, anchor: Token) -> nodes.TypeRef:
        tok = self._expect(TokenType.NAME, "a type name (int, float, str, bool, list, dict)")
        name = tok.resolved_text
        if name not in DSL_TYPE_NAMES and not name[0].isupper():
            raise ParseError(
                f"unknown type: {tok.themed_text!r} "
                "(must be int, float, str, bool, list, dict, or a class name)",
                tok.line,
                tok.col,
            )
        return nodes.TypeRef(pos=_pos_of(tok), name=name)

    def _parse_class_def(self) -> nodes.ClassDef:
        kw = self._advance()  # KW_CLASS
        name = self._expect(TokenType.NAME, "a class name")
        base: str | None = None
        if self._match(TokenType.LPAREN):
            base_tok = self._expect(TokenType.NAME, "a base class name")
            base = base_tok.resolved_text
            self._expect(TokenType.RPAREN, "')'")

        body = self._parse_block("the class body")

        fields: list[nodes.Param] = []
        methods: list[nodes.FunctionDef] = []
        for stmt in body:
            if isinstance(stmt, nodes.FunctionDef):
                methods.append(stmt)
            elif isinstance(stmt, nodes.Assignment) and isinstance(
                stmt.target, nodes.Identifier
            ):
                fields.append(
                    nodes.Param(
                        pos=stmt.pos,
                        name=stmt.target.name,
                        type_ref=stmt.annotation,
                        default=stmt.value,
                    )
                )
            else:
                raise ParseError(
                    "a class body may only contain field definitions (name = value) and "
                    f"{self._themed(UniversalConcept.FUNCTION_DEF)} definitions",
                    stmt.pos.line,
                    stmt.pos.col,
                )
        return nodes.ClassDef(
            pos=_pos_of(kw),
            name=name.resolved_text,
            base=base,
            fields=fields,
            methods=methods,
        )

    def _parse_if(self) -> nodes.If:
        kw = self._advance()  # KW_IF
        condition = self._parse_expr()
        then_body = self._parse_block("the condition body")

        elif_branches: list[tuple[nodes.Node, list[nodes.Node]]] = []
        while self._check(TokenType.KW_ELIF):
            self._advance()
            cond = self._parse_expr()
            body = self._parse_block("the condition body")
            elif_branches.append((cond, body))

        else_body: list[nodes.Node] | None = None
        if self._match(TokenType.KW_ELSE):
            else_body = self._parse_block("the else body")

        return nodes.If(
            pos=_pos_of(kw),
            condition=condition,
            then_body=then_body,
            elif_branches=elif_branches,
            else_body=else_body,
        )

    def _parse_for(self) -> nodes.ForLoop:
        kw = self._advance()  # KW_FOR
        var = self._expect(TokenType.NAME, "a loop variable")
        tok = self._peek()
        if tok.type is not TokenType.KW_IN:
            raise ParseError(
                f"expected {self._themed(UniversalConcept.IN)}, "
                f"found {tok.themed_text!r}",
                tok.line,
                tok.col,
            )
        self._advance()
        iterable = self._parse_expr()
        body = self._parse_block("the loop body")
        return nodes.ForLoop(
            pos=_pos_of(kw), var_name=var.resolved_text, iterable=iterable, body=body
        )

    def _parse_while(self) -> nodes.WhileLoop:
        kw = self._advance()  # KW_WHILE
        condition = self._parse_expr()
        body = self._parse_block("the loop body")
        return nodes.WhileLoop(pos=_pos_of(kw), condition=condition, body=body)

    def _parse_try(self) -> nodes.TryExcept:
        kw = self._advance()  # KW_TRY
        try_body = self._parse_block("the try block")

        handlers: list[nodes.ExceptHandler] = []
        while self._check(TokenType.KW_EXCEPT):
            h_kw = self._advance()
            bind_name: str | None = None
            if self._check(TokenType.NAME):
                bind_name = self._advance().resolved_text
            body = self._parse_block("the except body")
            handlers.append(
                nodes.ExceptHandler(pos=_pos_of(h_kw), bind_name=bind_name, body=body)
            )

        finally_body: list[nodes.Node] | None = None
        if self._match(TokenType.KW_FINALLY):
            finally_body = self._parse_block("the finally block")

        if not handlers and finally_body is None:
            tok = self._peek()
            raise ParseError(
                f"{self._themed(UniversalConcept.TRY)} block must be followed by "
                f"{self._themed(UniversalConcept.EXCEPT)} or "
                f"{self._themed(UniversalConcept.FINALLY)}",
                tok.line,
                tok.col,
            )

        return nodes.TryExcept(
            pos=_pos_of(kw),
            try_body=try_body,
            handlers=handlers,
            finally_body=finally_body,
        )

    def _parse_block(self, what: str) -> list[nodes.Node]:
        self._expect(TokenType.COLON, "':'")
        self._expect(TokenType.NEWLINE, "a new line")
        tok = self._peek()
        if tok.type is not TokenType.INDENT:
            raise ParseError(
                f"{what} requires at least one indented line", tok.line, tok.col
            )
        self._advance()
        body: list[nodes.Node] = []
        while not self._check(TokenType.DEDENT, TokenType.EOF):
            body.append(self._parse_statement())
        self._match(TokenType.DEDENT)
        return body

    def _parse_sql_select(self) -> nodes.SqlSelect:
        start = self._advance()  # select
        distinct = self._match_name("distinct") is not None
        items = self._parse_sql_select_items()
        self._expect_sql_name("from")
        table = self._parse_sql_table_ref()

        joins: list[nodes.SqlJoin] = []
        while self._check(TokenType.NAME) and self._peek().resolved_text in _SQL_JOIN_NAMES:
            join_token = self._advance()
            join_type = _SQL_JOIN_NAMES[join_token.resolved_text]
            join_table = self._parse_sql_table_ref()
            self._expect_sql_name("on")
            condition = self._parse_expr()
            joins.append(
                nodes.SqlJoin(join_type=join_type, table=join_table, condition=condition)
            )

        where = self._parse_expr() if self._match_name("where") else None

        group_by: list[nodes.Node] = []
        if self._match_name("group_by"):
            group_by = self._parse_sql_expr_list()

        having = self._parse_expr() if self._match_name("having") else None

        order_by: list[nodes.SqlOrderItem] = []
        if self._match_name("order_by"):
            order_by = self._parse_sql_order_items()

        limit = self._parse_expr() if self._match_name("limit") else None

        return nodes.SqlSelect(
            pos=_pos_of(start),
            items=items,
            table=table,
            distinct=distinct,
            joins=joins,
            where=where,
            group_by=group_by,
            having=having,
            order_by=order_by,
            limit=limit,
        )

    def _parse_sql_create_table(self) -> nodes.SqlCreateTable:
        start = self._advance()  # create_table
        table = nodes.SqlTableRef(name=self._parse_dotted_name("a table name"))
        self._expect(TokenType.LPAREN, "'('")
        columns: list[nodes.SqlColumnDef] = []
        if not self._check(TokenType.RPAREN):
            while True:
                name = self._expect(TokenType.NAME, "a column name")
                type_ref = self._parse_type_ref(name)
                constraints, check = self._parse_sql_column_constraints()
                columns.append(
                    nodes.SqlColumnDef(
                        name=name.resolved_text,
                        type_ref=type_ref,
                        constraints=constraints,
                        check=check,
                    )
                )
                if not self._match(TokenType.COMMA):
                    break
                if self._check(TokenType.RPAREN):
                    break
        self._expect(TokenType.RPAREN, "')'")
        if not columns:
            raise ParseError(
                "create_table must contain at least one column definition",
                start.line,
                start.col,
            )
        return nodes.SqlCreateTable(pos=_pos_of(start), table=table, columns=columns)

    def _parse_sql_column_constraints(self) -> tuple[list[str], nodes.Node | None]:
        constraints: list[str] = []
        check: nodes.Node | None = None
        while self._check(TokenType.NAME):
            name = self._peek().resolved_text
            if name in ("not_null", "unique", "primary_key"):
                constraints.append(self._advance().resolved_text)
                continue
            if name == "check":
                self._advance()
                check = self._parse_expr()
                continue
            break
        return constraints, check

    def _parse_sql_insert(self) -> nodes.SqlInsert:
        start = self._advance()  # insert_into
        table = self._parse_dotted_name("a table name")
        columns: list[str] = []
        if self._match(TokenType.LPAREN):
            if not self._check(TokenType.RPAREN):
                while True:
                    columns.append(self._expect(TokenType.NAME, "a column name").resolved_text)
                    if not self._match(TokenType.COMMA):
                        break
                    if self._check(TokenType.RPAREN):
                        break
            self._expect(TokenType.RPAREN, "')'")
        self._expect_sql_name("values")
        self._expect(TokenType.LPAREN, "'('")
        values = self._parse_sql_expr_list() if not self._check(TokenType.RPAREN) else []
        self._expect(TokenType.RPAREN, "')'")
        if columns and len(columns) != len(values):
            raise ParseError(
                "insert_into column count must equal the number of values",
                start.line,
                start.col,
            )
        if not values:
            raise ParseError("insert_into must contain at least one value", start.line, start.col)
        return nodes.SqlInsert(
            pos=_pos_of(start), table=table, columns=columns, values=values
        )

    def _parse_sql_update(self) -> nodes.SqlUpdate:
        start = self._advance()  # update
        table = self._parse_dotted_name("a table name")
        self._expect_sql_name("set")
        assignments = self._parse_sql_assignments()
        where = self._parse_expr() if self._match_name("where") else None
        return nodes.SqlUpdate(
            pos=_pos_of(start), table=table, assignments=assignments, where=where
        )

    def _parse_sql_delete(self) -> nodes.SqlDelete:
        start = self._advance()  # delete
        self._expect_sql_name("from")
        table = self._parse_dotted_name("a table name")
        where = self._parse_expr() if self._match_name("where") else None
        return nodes.SqlDelete(pos=_pos_of(start), table=table, where=where)

    def _parse_sql_drop_table(self) -> nodes.SqlDropTable:
        start = self._advance()
        table = self._parse_dotted_name("a table name")
        return nodes.SqlDropTable(pos=_pos_of(start), table=table)

    def _parse_sql_truncate_table(self) -> nodes.SqlTruncateTable:
        start = self._advance()
        table = self._parse_dotted_name("a table name")
        return nodes.SqlTruncateTable(pos=_pos_of(start), table=table)

    def _parse_sql_alter_table(self) -> nodes.SqlAlterTable:
        start = self._advance()
        table = self._parse_dotted_name("a table name")
        if self._match_name("add"):
            self._match_name("column")
            column = self._expect(TokenType.NAME, "a column name")
            type_ref = self._parse_type_ref(column)
            return nodes.SqlAlterTable(
                pos=_pos_of(start),
                table=table,
                action="add_column",
                column=column.resolved_text,
                type_ref=type_ref,
            )
        if self._match_name("drop_column"):
            column = self._expect(TokenType.NAME, "a column name")
            return nodes.SqlAlterTable(
                pos=_pos_of(start),
                table=table,
                action="drop_column",
                column=column.resolved_text,
            )
        if self._match_name("alter_column"):
            column = self._expect(TokenType.NAME, "a column name")
            type_ref = self._parse_type_ref(column)
            return nodes.SqlAlterTable(
                pos=_pos_of(start),
                table=table,
                action="alter_column",
                column=column.resolved_text,
                type_ref=type_ref,
            )
        tok = self._peek()
        raise ParseError("alter_table requires add, drop_column, or alter_column", tok.line, tok.col)

    def _parse_sql_create_index(self, *, unique: bool) -> nodes.SqlCreateIndex:
        start = self._advance()
        name = self._expect(TokenType.NAME, "an index name").resolved_text
        self._expect_sql_name("on")
        table = self._parse_dotted_name("a table name")
        self._expect(TokenType.LPAREN, "'('")
        columns = self._parse_sql_name_items()
        self._expect(TokenType.RPAREN, "')'")
        return nodes.SqlCreateIndex(
            pos=_pos_of(start), name=name, table=table, columns=columns, unique=unique
        )

    def _parse_sql_drop_index(self) -> nodes.SqlDropIndex:
        start = self._advance()
        name = self._expect(TokenType.NAME, "an index name").resolved_text
        return nodes.SqlDropIndex(pos=_pos_of(start), name=name)

    def _parse_sql_create_view(self) -> nodes.SqlCreateView:
        start = self._advance()
        name = self._expect(TokenType.NAME, "a view name").resolved_text
        self._expect_sql_name("as")
        query = self._parse_sql_select()
        return nodes.SqlCreateView(pos=_pos_of(start), name=name, query=query)

    def _parse_sql_drop_view(self) -> nodes.SqlDropView:
        start = self._advance()
        name = self._expect(TokenType.NAME, "a view name").resolved_text
        return nodes.SqlDropView(pos=_pos_of(start), name=name)

    def _parse_sql_create_database(self) -> nodes.SqlCreateDatabase:
        start = self._advance()
        name = self._expect(TokenType.NAME, "a database name").resolved_text
        return nodes.SqlCreateDatabase(pos=_pos_of(start), name=name)

    def _parse_sql_drop_database(self) -> nodes.SqlDropDatabase:
        start = self._advance()
        name = self._expect(TokenType.NAME, "a database name").resolved_text
        return nodes.SqlDropDatabase(pos=_pos_of(start), name=name)

    def _parse_sql_select_items(self) -> list[nodes.SqlSelectItem]:
        items: list[nodes.SqlSelectItem] = []
        while True:
            expr = self._parse_expr()
            alias = None
            if self._match_name("as"):
                alias = self._expect(TokenType.NAME, "a query field alias").resolved_text
            items.append(nodes.SqlSelectItem(expr=expr, alias=alias))
            if not self._match(TokenType.COMMA):
                return items

    def _parse_sql_expr_list(self) -> list[nodes.Node]:
        items = [self._parse_expr()]
        while self._match(TokenType.COMMA):
            items.append(self._parse_expr())
        return items

    def _parse_sql_assignments(self) -> list[nodes.SqlAssignment]:
        assignments: list[nodes.SqlAssignment] = []
        while True:
            name = self._expect(TokenType.NAME, "a column name")
            self._expect(TokenType.ASSIGN, "'='")
            value = self._parse_expr()
            assignments.append(nodes.SqlAssignment(name=name.resolved_text, value=value))
            if not self._match(TokenType.COMMA):
                return assignments

    def _parse_sql_name_items(self) -> list[str]:
        items = [self._expect(TokenType.NAME, "a column name").resolved_text]
        while self._match(TokenType.COMMA):
            items.append(self._expect(TokenType.NAME, "a column name").resolved_text)
        return items

    def _parse_sql_order_items(self) -> list[nodes.SqlOrderItem]:
        items: list[nodes.SqlOrderItem] = []
        while True:
            expr = self._parse_expr()
            direction = "asc"
            if self._is_name("asc") or self._is_name("desc"):
                direction = self._advance().resolved_text
            items.append(nodes.SqlOrderItem(expr=expr, direction=direction))  # type: ignore[arg-type]
            if not self._match(TokenType.COMMA):
                return items

    def _parse_sql_table_ref(self) -> nodes.SqlTableRef:
        name = self._parse_dotted_name("a table name")
        alias = None
        if self._match_name("as"):
            alias = self._expect(TokenType.NAME, "a table alias").resolved_text
        elif (
            self._check(TokenType.NAME)
            and self._peek().resolved_text not in _SQL_CLAUSE_NAMES
            and self._peek().resolved_text != "on"
        ):
            alias = self._advance().resolved_text
        return nodes.SqlTableRef(name=name, alias=alias)

    def _parse_dotted_name(self, what: str) -> str:
        tok = self._expect(TokenType.NAME, what)
        name = tok.resolved_text
        while self._match(TokenType.DOT):
            part = self._expect(TokenType.NAME, what)
            name += "." + part.resolved_text
        return name

    def _expect_sql_name(self, name: str) -> Token:
        tok = self._peek()
        if tok.type is TokenType.NAME and tok.resolved_text == name:
            return self._advance()
        got = tok.themed_text or tok.type.name
        raise ParseError(f"expected '{name}', found {got!r}", tok.line, tok.col)

    # --------------------------------------------------------- expressions

    def _parse_expr(self) -> nodes.Node:
        return self._parse_walrus()

    def _parse_walrus(self) -> nodes.Node:
        left = self._parse_conditional()
        if self._check(TokenType.WALRUS):
            op = self._advance()
            if not isinstance(left, nodes.Identifier):
                raise ParseError(
                    "the left side of the walrus operator must be a name",
                    op.line,
                    op.col,
                )
            value = self._parse_walrus()
            return nodes.AssignmentExpr(pos=_pos_of(op), name=left.name, value=value)
        return left

    def _parse_conditional(self) -> nodes.Node:
        then_expr = self._parse_or()
        if self._check(TokenType.KW_IF):
            if_tok = self._advance()
            condition = self._parse_or()
            if not self._check(TokenType.KW_ELSE):
                tok = self._peek()
                raise ParseError(
                    f"expected {self._themed(UniversalConcept.ELSE)}, "
                    f"found {tok.themed_text!r}",
                    tok.line,
                    tok.col,
                )
            self._advance()
            else_expr = self._parse_conditional()
            return nodes.ConditionalExpr(
                pos=_pos_of(if_tok),
                condition=condition,
                then_expr=then_expr,
                else_expr=else_expr,
            )
        return then_expr

    def _parse_or(self) -> nodes.Node:
        left = self._parse_and()
        while self._check(TokenType.KW_OR) or self._is_name("or"):
            op_tok = self._advance()
            right = self._parse_and()
            left = nodes.BinaryOp(pos=_pos_of(op_tok), op="or", left=left, right=right)
        return left

    def _parse_and(self) -> nodes.Node:
        left = self._parse_not()
        while self._check(TokenType.KW_AND) or self._is_name("and"):
            op_tok = self._advance()
            right = self._parse_not()
            left = nodes.BinaryOp(pos=_pos_of(op_tok), op="and", left=left, right=right)
        return left

    def _parse_not(self) -> nodes.Node:
        if self._check(TokenType.KW_NOT) or self._is_name("not"):
            op_tok = self._advance()
            operand = self._parse_not()
            return nodes.UnaryOp(pos=_pos_of(op_tok), op="not", operand=operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> nodes.Node:
        left = self._parse_arith()
        while (
            self._check(*_COMPARISON_OPS.keys())
            or self._is_name("is")
            or self._check(TokenType.KW_IN)
            or self._is_name("in")
            or self._is_name("like")
            or self._is_name("between")
            or self._is_name("is_null")
            or self._is_name("is_not_null")
        ):
            if self._is_name("is_null") or self._is_name("is_not_null"):
                op_tok = self._advance()
                op = "==" if op_tok.resolved_text == "is_null" else "!="
                left = nodes.BinaryOp(
                    pos=_pos_of(op_tok),
                    op=op,
                    left=left,
                    right=nodes.Literal(pos=_pos_of(op_tok), value=None, literal_type="none"),
                )
                continue

            if self._is_name("between"):
                op_tok = self._advance()
                lower = self._parse_arith()
                if not (self._check(TokenType.KW_AND) or self._is_name("and")):
                    tok = self._peek()
                    raise ParseError("expected 'and'", tok.line, tok.col)
                self._advance()
                upper = self._parse_arith()
                left = nodes.BetweenOp(
                    pos=_pos_of(op_tok), expr=left, lower=lower, upper=upper
                )
                continue

            op_tok = self._advance()
            if op_tok.type in _COMPARISON_OPS:
                op = _COMPARISON_OPS[op_tok.type]
            elif op_tok.type is TokenType.KW_IN:
                op = "in"
            elif op_tok.resolved_text in ("in", "like"):
                op = op_tok.resolved_text
            else:
                op = "is"
                if self._check(TokenType.KW_NOT) or self._is_name("not"):
                    self._advance()
                    op = "is not"
            right = self._parse_in_items() if op == "in" else self._parse_arith()
            left = nodes.BinaryOp(
                pos=_pos_of(op_tok), op=op, left=left, right=right
            )
        return left

    def _parse_in_items(self) -> nodes.Node:
        if not self._match(TokenType.LPAREN):
            return self._parse_arith()
        start = self._peek()
        elements: list[nodes.Node] = []
        if not self._check(TokenType.RPAREN):
            while True:
                elements.append(self._parse_expr())
                if not self._match(TokenType.COMMA):
                    break
                if self._check(TokenType.RPAREN):
                    break
        self._expect(TokenType.RPAREN, "')'")
        return nodes.ListLiteral(pos=_pos_of(start), elements=elements)

    def _parse_arith(self) -> nodes.Node:
        left = self._parse_term()
        while self._check(*_ADDITIVE_OPS.keys()):
            op_tok = self._advance()
            right = self._parse_term()
            left = nodes.BinaryOp(
                pos=_pos_of(op_tok), op=_ADDITIVE_OPS[op_tok.type], left=left, right=right
            )
        return left

    def _parse_term(self) -> nodes.Node:
        left = self._parse_unary()
        while self._check(*_MULTIPLICATIVE_OPS.keys()):
            op_tok = self._advance()
            right = self._parse_unary()
            left = nodes.BinaryOp(
                pos=_pos_of(op_tok),
                op=_MULTIPLICATIVE_OPS[op_tok.type],
                left=left,
                right=right,
            )
        return left

    def _parse_unary(self) -> nodes.Node:
        if self._check(TokenType.MINUS):
            op_tok = self._advance()
            operand = self._parse_unary()
            return nodes.UnaryOp(pos=_pos_of(op_tok), op="-", operand=operand)
        if self._is_name("await"):
            op_tok = self._advance()
            operand = self._parse_unary()
            return nodes.AwaitExpr(pos=_pos_of(op_tok), value=operand)
        return self._parse_postfix()

    def _parse_postfix(self) -> nodes.Node:
        expr = self._parse_primary()
        while True:
            if self._check(TokenType.LPAREN):
                self._advance()
                args = self._parse_args()
                self._expect(TokenType.RPAREN, "')'")
                expr = nodes.Call(pos=expr.pos, callee=expr, args=args)
            elif self._check(TokenType.LBRACKET):
                self._advance()
                key = self._parse_expr()
                self._expect(TokenType.RBRACKET, "']'")
                expr = nodes.Index(pos=expr.pos, target=expr, key=key)
            elif self._check(TokenType.DOT):
                self._advance()
                name_tok = self._expect(TokenType.NAME, "a field/method name")
                if self._check(TokenType.LPAREN):
                    self._advance()
                    args = self._parse_args()
                    self._expect(TokenType.RPAREN, "')'")
                    expr = nodes.MethodCall(
                        pos=_pos_of(name_tok),
                        target=expr,
                        method=name_tok.resolved_text,
                        themed_method=(
                            name_tok.themed_text
                            if name_tok.themed_text != name_tok.resolved_text
                            else None
                        ),
                        args=args,
                    )
                else:
                    expr = nodes.Attribute(
                        pos=_pos_of(name_tok), target=expr, name=name_tok.resolved_text
                    )
            else:
                return expr

    def _parse_args(self) -> list[nodes.Node]:
        args: list[nodes.Node] = []
        if self._check(TokenType.RPAREN):
            return args
        while True:
            args.append(self._parse_expr())
            if not self._match(TokenType.COMMA):
                return args
            if self._check(TokenType.RPAREN):
                return args

    def _parse_lambda(self) -> nodes.LambdaExpr:
        tok = self._advance()  # lambda
        params: list[str] = []
        if not self._check(TokenType.COLON):
            while True:
                params.append(self._expect(TokenType.NAME, "a lambda parameter").resolved_text)
                if not self._match(TokenType.COMMA):
                    break
        self._expect(TokenType.COLON, "':'")
        body = self._parse_expr()
        return nodes.LambdaExpr(pos=_pos_of(tok), params=params, body=body)

    def _parse_primary(self) -> nodes.Node:
        tok = self._peek()
        t = tok.type

        if t is TokenType.STAR:
            self._advance()
            return nodes.Star(pos=_pos_of(tok))

        if t is TokenType.KW_LAMBDA or self._is_name("lambda"):
            return self._parse_lambda()

        if self._is_name("yield"):
            self._advance()
            value = None
            if not self._check(
                TokenType.NEWLINE,
                TokenType.EOF,
                TokenType.DEDENT,
                TokenType.RPAREN,
                TokenType.RBRACKET,
                TokenType.RBRACE,
                TokenType.COMMA,
                TokenType.COLON,
            ):
                value = self._parse_expr()
            return nodes.YieldExpr(pos=_pos_of(tok), value=value)

        if t is TokenType.NUMBER:
            self._advance()
            if "." in tok.resolved_text:
                return nodes.Literal(
                    pos=_pos_of(tok), value=float(tok.resolved_text), literal_type="float"
                )
            return nodes.Literal(
                pos=_pos_of(tok), value=int(tok.resolved_text), literal_type="int"
            )

        if t is TokenType.STRING:
            self._advance()
            return nodes.Literal(pos=_pos_of(tok), value=tok.resolved_text, literal_type="str")

        if t is TokenType.KW_TRUE:
            self._advance()
            return nodes.Literal(pos=_pos_of(tok), value=True, literal_type="bool")

        if t is TokenType.KW_FALSE:
            self._advance()
            return nodes.Literal(pos=_pos_of(tok), value=False, literal_type="bool")

        if t is TokenType.KW_NONE:
            self._advance()
            return nodes.Literal(pos=_pos_of(tok), value=None, literal_type="none")

        if t is TokenType.NAME:
            self._advance()
            return nodes.Identifier(
                pos=_pos_of(tok),
                name=tok.resolved_text,
                themed_name=(
                    tok.themed_text if tok.themed_text != tok.resolved_text else None
                ),
            )

        if t is TokenType.LBRACKET:
            self._advance()
            elements: list[nodes.Node] = []
            if not self._check(TokenType.RBRACKET):
                while True:
                    elements.append(self._parse_expr())
                    if not self._match(TokenType.COMMA):
                        break
                    if self._check(TokenType.RBRACKET):
                        break
            self._expect(TokenType.RBRACKET, "']'")
            return nodes.ListLiteral(pos=_pos_of(tok), elements=elements)

        if t is TokenType.LBRACE:
            self._advance()
            entries: list[tuple[nodes.Node, nodes.Node]] = []
            if not self._check(TokenType.RBRACE):
                while True:
                    key = self._parse_expr()
                    self._expect(TokenType.COLON, "':'")
                    value = self._parse_expr()
                    entries.append((key, value))
                    if not self._match(TokenType.COMMA):
                        break
                    if self._check(TokenType.RBRACE):
                        break
            self._expect(TokenType.RBRACE, "'}'")
            return nodes.DictLiteral(pos=_pos_of(tok), entries=entries)

        if t is TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(TokenType.RPAREN, "')'")
            return expr

        got = tok.themed_text or tok.type.name
        raise ParseError(f"expected an expression, found {got!r}", tok.line, tok.col)


def _pos_of(tok: Token) -> nodes.Position:
    return nodes.Position(tok.line, tok.col)
