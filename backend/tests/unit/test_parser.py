from __future__ import annotations

import pytest

from codeverse_core.lexer.lexer import Lexer
from codeverse_core.parser.errors import ParseError
from codeverse_core.parser.parser import Parser
from codeverse_core.theme_mapping.dictionary import CANONICAL_DICTIONARY
from codeverse_core.uasl import nodes


def parse(source, dictionary=CANONICAL_DICTIONARY):
    tokens = Lexer(source, dictionary).tokenize()
    return Parser(tokens, dictionary).parse_program()


def test_function_def():
    program = parse("func topla(a, b):\n    return a + b")
    fn = program.body[0]
    assert isinstance(fn, nodes.FunctionDef)
    assert fn.name == "topla"
    assert [p.name for p in fn.params] == ["a", "b"]
    ret = fn.body[0]
    assert isinstance(ret, nodes.Return)
    assert isinstance(ret.value, nodes.BinaryOp)
    assert ret.value.op == "+"


def test_if_elif_else():
    src = "if x > 1:\n    y = 1\nelif x > 0:\n    y = 2\nelse:\n    y = 3"
    program = parse(src)
    stmt = program.body[0]
    assert isinstance(stmt, nodes.If)
    assert len(stmt.elif_branches) == 1
    assert stmt.else_body is not None


def test_for_and_while():
    program = parse("for i in range(10):\n    x = i\nwhile x > 0:\n    x = x - 1")
    for_loop, while_loop = program.body
    assert isinstance(for_loop, nodes.ForLoop)
    assert for_loop.var_name == "i"
    assert isinstance(while_loop, nodes.WhileLoop)


def test_class_with_fields_and_methods():
    src = (
        "class Oyuncu:\n"
        "    isim = \"bilinmiyor\"\n"
        "    puan = 0\n"
        "    func skor_ekle(self_puan):\n"
        "        self.puan = self.puan + self_puan\n"
    )
    program = parse(src)
    cls = program.body[0]
    assert isinstance(cls, nodes.ClassDef)
    assert [f.name for f in cls.fields] == ["isim", "puan"]
    assert [m.name for m in cls.methods] == ["skor_ekle"]


def test_try_except_finally():
    src = (
        "try:\n    x = 1 / 0\n"
        "except hata:\n    print(hata)\n"
        "finally:\n    print(\"bitti\")\n"
    )
    program = parse(src)
    stmt = program.body[0]
    assert isinstance(stmt, nodes.TryExcept)
    assert stmt.handlers[0].bind_name == "hata"
    assert stmt.finally_body is not None


def test_list_and_dict_literals():
    program = parse('xs = [1, 2, 3]\nd = {"a": 1, "b": 2}')
    assert isinstance(program.body[0].value, nodes.ListLiteral)
    assert isinstance(program.body[1].value, nodes.DictLiteral)


def test_method_call_and_index():
    program = parse("xs.append(4)\nv = d[\"a\"]\nxs[0] = 9")
    call = program.body[0].expr
    assert isinstance(call, nodes.MethodCall)
    assert call.method == "append"
    idx = program.body[1].value
    assert isinstance(idx, nodes.Index)
    assign = program.body[2]
    assert isinstance(assign.target, nodes.Index)


def test_operator_precedence():
    program = parse("x = 1 + 2 * 3")
    top = program.body[0].value
    assert top.op == "+"
    assert top.right.op == "*"


def test_logic_precedence():
    program = parse("x = a > 1 and b < 2 or not c == 3")
    top = program.body[0].value
    assert top.op == "or"
    assert top.left.op == "and"


def test_themed_source_parses(space_dictionary):
    src = (
        "singularity fib(n):\n"
        "    event_horizon n <= 1:\n"
        "        emit n\n"
        "    emit fib(n - 1) + fib(n - 2)\n"
    )
    program = parse(src, space_dictionary)
    fn = program.body[0]
    assert isinstance(fn, nodes.FunctionDef)
    assert fn.name == "fib"
    assert isinstance(fn.body[0], nodes.If)


def test_themed_error_message_uses_themed_keyword(space_dictionary):
    # missing 'around' (themed 'in') in a for loop
    with pytest.raises(ParseError, match="around"):
        parse("orbit i lightyears(10):\n    radiate(i)", space_dictionary)


def test_missing_block_rejected():
    with pytest.raises(ParseError, match="girintili"):
        parse("if x > 1:\ny = 2")


def test_annotation_assignment():
    program = parse("sayi: int = 5")
    assign = program.body[0]
    assert assign.annotation.name == "int"


def test_assignment_to_literal_rejected():
    with pytest.raises(ParseError, match="sol taraf"):
        parse("5 = x")


def test_import_dotted():
    program = parse("import a.b.c")
    assert program.body[0].module == "a.b.c"


def test_trailing_commas_in_calls_params_and_literals():
    program = parse(
        "func f(a, b,):\n"
        "    return [a, b,]\n"
        "x = f(1, 2,)\n"
        'd = {"a": 1, "b": 2,}\n'
    )

    fn = program.body[0]
    assert [p.name for p in fn.params] == ["a", "b"]
    assert isinstance(fn.body[0].value, nodes.ListLiteral)
    assert len(fn.body[0].value.elements) == 2
    assert len(program.body[1].value.args) == 2
    assert len(program.body[2].value.entries) == 2


def test_extended_python_statements_parse():
    program = parse(
        "global g\n"
        "nonlocal n\n"
        "assert g > 0, \"bad\"\n"
        "del xs[0], obj.field\n"
        "raise \"boom\"\n"
        "pass\n"
    )

    assert isinstance(program.body[0], nodes.Global)
    assert isinstance(program.body[1], nodes.Nonlocal)
    assert isinstance(program.body[2], nodes.Assert)
    assert isinstance(program.body[3], nodes.Delete)
    assert isinstance(program.body[4], nodes.Raise)
    assert isinstance(program.body[5], nodes.Pass)


def test_lambda_and_walrus_parse():
    program = parse("f = lambda x, y: x + y\nprint(n := f(1, 2))")

    assert isinstance(program.body[0].value, nodes.LambdaExpr)
    call = program.body[1].expr
    assert isinstance(call.args[0], nodes.AssignmentExpr)


def test_conditional_expression_parse():
    program = parse('label = "fast" if score > 10 else "steady"')

    expr = program.body[0].value
    assert isinstance(expr, nodes.ConditionalExpr)
    assert isinstance(expr.condition, nodes.BinaryOp)
    assert expr.condition.op == ">"


def test_extended_python_keyword_surface_parse():
    program = parse(
        "from math import sqrt as kok\n"
        "with open(\"x.txt\") as f:\n"
        "    data = f.read()\n"
        "match data:\n"
        "    case \"\":\n"
        "        pass\n"
        "    case _:\n"
        "        pass\n"
        "async func load(x):\n"
        "    value = await fetch(x)\n"
        "    yield value\n"
        "same = data is None\n"
    )

    assert isinstance(program.body[0], nodes.FromImport)
    assert isinstance(program.body[1], nodes.With)
    assert isinstance(program.body[2], nodes.Match)
    assert isinstance(program.body[3], nodes.FunctionDef)
    assert program.body[3].async_def is True
    assert isinstance(program.body[3].body[0].value, nodes.AwaitExpr)
    assert isinstance(program.body[3].body[1].expr, nodes.YieldExpr)
    assert program.body[4].value.op == "is"


def test_sql_select_join_query_parses():
    program = parse(
        "select c.CustomerName, count(o.OrderID) as order_count "
        "from Customers as c "
        "left_join Orders as o on c.CustomerID == o.CustomerID "
        "where o.OrderID != none "
        "group_by c.CustomerName "
        "having count(o.OrderID) > 1 "
        "order_by order_count desc "
        "limit 10"
    )

    query = program.body[0]
    assert isinstance(query, nodes.SqlSelect)
    assert query.table.name == "Customers"
    assert query.table.alias == "c"
    assert query.joins[0].join_type == "LEFT JOIN"
    assert query.group_by
    assert query.having is not None
    assert query.order_by[0].direction == "desc"


def test_sql_dml_ddl_parse():
    program = parse(
        "create_table Cars (id int primary_key, driver str not_null unique, active bool)\n"
        "insert_into Cars (id, driver, active) values (1, \"Ada\", true)\n"
        "update Cars set driver = \"Babbage\", active = false where id == 1\n"
        "delete from Cars where active == false\n"
    )

    create, insert, update, delete = program.body
    assert isinstance(create, nodes.SqlCreateTable)
    assert [c.name for c in create.columns] == ["id", "driver", "active"]
    assert create.columns[0].constraints == ["primary_key"]
    assert create.columns[1].constraints == ["not_null", "unique"]
    assert isinstance(insert, nodes.SqlInsert)
    assert insert.columns == ["id", "driver", "active"]
    assert isinstance(update, nodes.SqlUpdate)
    assert [item.name for item in update.assignments] == ["driver", "active"]
    assert update.where is not None
    assert isinstance(delete, nodes.SqlDelete)
    assert delete.where is not None


def test_sql_extended_filters_and_ddl_parse():
    program = parse(
        "select * from Cars where name like \"A%\" and id in (1, 2) "
        "and score between 10 and 20 and deleted_at is_null\n"
        "alter_table Cars add column pace str\n"
        "alter_table Cars drop_column old_pace\n"
        "alter_table Cars alter_column score float\n"
        "create_index idx_cars_name on Cars (name)\n"
        "create_unique_index idx_cars_id on Cars (id)\n"
        "create_view FastCars as select * from Cars where score > 10\n"
        "drop_index idx_cars_name\n"
        "drop_view FastCars\n"
        "truncate_table Cars\n"
        "drop_table Cars\n"
        "create_database RaceDb\n"
        "drop_database RaceDb\n"
    )

    assert isinstance(program.body[0], nodes.SqlSelect)
    assert isinstance(program.body[1], nodes.SqlAlterTable)
    assert isinstance(program.body[4], nodes.SqlCreateIndex)
    assert program.body[5].unique is True
    assert isinstance(program.body[6], nodes.SqlCreateView)
    assert isinstance(program.body[10], nodes.SqlDropTable)
    assert isinstance(program.body[11], nodes.SqlCreateDatabase)
