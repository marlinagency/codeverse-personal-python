from __future__ import annotations

import pytest

from codeverse_core.cvl.pipeline import CompilationError, CompilationPipeline
from codeverse_core.lexer.lexer import Lexer
from codeverse_core.lexer.tokens import TokenType
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionary
from tests.golden.util import SPACE_DICTIONARY


def _compile_sql(body: str, dictionary=SPACE_DICTIONARY) -> str:
    source = f"""@theme: Formula yaris
@language: sql
@version: 1
---
{body}
"""
    return CompilationPipeline().compile(source, dictionary).codegen.source_code


def _compile_python(body: str, dictionary=SPACE_DICTIONARY) -> str:
    source = f"""@theme: Formula yaris
@language: python
@version: 1
---
{body}
"""
    return CompilationPipeline().compile(source, dictionary).codegen.source_code


def test_python_codegen_accepts_taxonomy_builtins_and_methods():
    dictionary = TaxonomyThemeDictionary(
        theme="Formula yaris",
        mappings={
            "py_fn_print": "telsiz",
            "py_fn_abs": "mutlak",
            "py_str_upper": "turbo",
        },
    )

    generated = _compile_python(
        'metin = "formula"\n'
        "telsiz(mutlak(-3))\n"
        "telsiz(metin.turbo())\n",
        dictionary,  # type: ignore[arg-type]
    )

    assert "print(abs(" in generated
    assert "metin.upper()" in generated


def test_python_codegen_extended_statements_and_expressions():
    generated = _compile_python(
        "x = 0\n"
        "assert x == 0, \"x bozuk\"\n"
        "f = lambda a, b: a + b\n"
        "print(n := f(2, 3))\n"
        "d = {\"a\": 1}\n"
        "del d[\"a\"]\n"
        "label = \"fast\" event_horizon n > 4 vacuum \"slow\"\n"
    )

    assert 'assert (x == 0), "x bozuk"' in generated
    assert "lambda a, b: (a + b)" in generated
    assert "print((n := f(2, 3)))" in generated
    assert 'del d["a"]' in generated
    assert 'label = ("fast" if (n > 4) else "slow")' in generated


def test_python_taxonomy_resolves_remaining_keyword_surface():
    dictionary = TaxonomyThemeDictionary(
        theme="Deniz alti",
        mappings={
            "py_kw_from": "dipten",
            "py_kw_import": "ice_al",
            "py_kw_as": "gibi",
            "py_kw_with": "basinc_kabini",
            "py_kw_match": "sonar",
            "py_kw_case": "yanki",
            "py_kw_async": "derin_akim",
            "py_kw_await": "bekle",
            "py_kw_yield": "yuzeye_ver",
            "py_kw_is": "ayni_mi",
            "py_kw_none": "bosluk",
            "py_kw_def": "istasyon",
            "py_fn_open": "kapak_ac",
        },
    )

    generated = _compile_python(
        "dipten asyncio ice_al sleep gibi nap\n"
        "basinc_kabini kapak_ac(\"x.txt\") gibi f:\n"
        "    data = f.read()\n"
        "sonar \"\":\n"
        "    yanki \"\":\n"
        "        pass\n"
        "    yanki _:\n"
        "        pass\n"
        "derin_akim istasyon load(x):\n"
        "    value = bekle nap(0)\n"
        "    yuzeye_ver value\n"
        "same = 1 ayni_mi bosluk\n",
        dictionary,  # type: ignore[arg-type]
    )

    assert "from asyncio import sleep as nap" in generated
    assert 'with open("x.txt") as f:' in generated
    assert "match \"\":" in generated
    assert "case \"\":" in generated
    assert "async def load(x):" in generated
    assert "value = (await nap(0))" in generated
    assert "yield value" in generated
    assert "same = (1 is None)" in generated


def test_sql_codegen_lowers_taxonomy_string_methods_and_functions():
    generated = _compile_sql(
        's: str = "Formula"\n'
        "radiate(s.upper())\n"
        'radiate(s.startswith("F"))\n'
        'radiate(concat("pit", "_", "lane"))\n'
        "radiate(sqrt(9))\n"
    )

    assert "upper(s)" in generated
    assert "left(s, char_length('F')) = 'F'" in generated
    assert "concat('pit', '_', 'lane')" in generated
    assert "sqrt(9)" in generated


def test_sql_codegen_lowers_taxonomy_collection_methods():
    generated = _compile_sql(
        "xs = [1]\n"
        "xs.extend([2, 3])\n"
        "xs.reverse()\n"
        'd = {"a": 1}\n'
        'd.update({"b": 2})\n'
        'radiate(",".join(["a", "b"]))\n'
    )

    assert "xs := _cv_extend(xs, jsonb_build_array" in generated
    assert "xs := _cv_reverse(xs);" in generated
    assert "d := _cv_update(d, jsonb_build_object" in generated
    assert "_cv_str_join(',', jsonb_build_array" in generated


def test_sql_codegen_rejects_mutating_taxonomy_method_in_expression():
    with pytest.raises(CompilationError) as raised:
        _compile_sql("xs = []\nradiate(xs.extend([1]))\n")

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.stage == "codegen"
    assert "extend" in diagnostic.message
    assert "satir" in diagnostic.message or "satÄ±r" in diagnostic.message


def test_taxonomy_dictionary_resolves_themed_tokens_for_pipeline():
    dictionary = TaxonomyThemeDictionary(
        theme="Formula yaris",
        mappings={
            "py_kw_def": "garaj",
            "py_fn_print": "telsiz",
            "py_str_upper": "turbo",
            "sql_mysql_concat": "birles",
        },
    )
    tokens = Lexer(
        'garaj rapor():\n    telsiz("pit")\nmetin = "formula"\ntelsiz(metin.turbo())\n',
        dictionary,  # type: ignore[arg-type]
    ).tokenize()

    assert tokens[0].type is TokenType.KW_FUNC
    assert any(t.themed_text == "telsiz" and t.resolved_text == "print" for t in tokens)
    assert any(t.themed_text == "turbo" and t.resolved_text == "upper" for t in tokens)

    generated = _compile_sql(
        'telsiz(birles("pit", "lane"))\n',
        dictionary,  # type: ignore[arg-type]
    )
    assert "RAISE NOTICE" in generated
    assert "concat('pit', 'lane')" in generated


def test_sql_codegen_emits_real_select_join_query():
    generated = _compile_sql(
        "select c.CustomerName, count(o.OrderID) as order_count "
        "from Customers as c "
        "left_join Orders as o on c.CustomerID == o.CustomerID "
        "where o.OrderID != none "
        "group_by c.CustomerName "
        "having count(o.OrderID) > 1 "
        "order_by order_count desc "
        "limit 10\n"
    )

    assert "SELECT c.CustomerName, count(o.OrderID) AS order_count" in generated
    assert "FROM Customers AS c" in generated
    assert "LEFT JOIN Orders AS o ON (c.CustomerID = o.CustomerID)" in generated
    assert "WHERE (o.OrderID IS NOT NULL)" in generated
    assert "GROUP BY c.CustomerName" in generated
    assert "HAVING (count(o.OrderID) > 1)" in generated
    assert "ORDER BY order_count DESC" in generated
    assert "LIMIT 10" in generated


def test_sql_codegen_emits_case_for_conditional_expression():
    generated = _compile_sql(
        'select id, "fast" event_horizon score > 10 vacuum "steady" as pace from Cars\n'
        'update Cars set pace = "fast" event_horizon score > 10 vacuum "steady" '
        "where id == 7\n"
    )

    expected = "(CASE WHEN (score > 10) THEN 'fast' ELSE 'steady' END)"
    assert f"SELECT id, {expected} AS pace" in generated
    assert f"UPDATE Cars SET pace = {expected} WHERE (id = 7)" in generated


def test_taxonomy_dictionary_resolves_themed_sql_query_tokens():
    dictionary = TaxonomyThemeDictionary(
        theme="Formula yaris",
        mappings={
            "sql_query_basics_select": "grid",
            "sql_kw_from": "garajdan",
            "sql_kw_where": "filtrele",
            "sql_kw_left_join": "sol_serit",
            "sql_kw_order_by": "sirala",
        },
    )

    generated = _compile_sql(
        "grid c.name "
        "garajdan Customers as c "
        "sol_serit Orders as o on c.id == o.customer_id "
        "filtrele o.id != none "
        "sirala c.name\n",
        dictionary,  # type: ignore[arg-type]
    )

    assert "SELECT c.name" in generated
    assert "LEFT JOIN Orders AS o ON (c.id = o.customer_id)" in generated
    assert "WHERE (o.id IS NOT NULL)" in generated
    assert "ORDER BY c.name ASC" in generated


def test_sql_codegen_emits_create_insert_update_delete():
    generated = _compile_sql(
        "create_table Cars ("
        "id int primary_key, "
        "driver str not_null unique, "
        "active bool, "
        "payload dict, "
        "score int check score > 0"
        ")\n"
        "insert_into Cars (id, driver, active, payload) "
        'values (1, "Ada", true, {"team": "red"})\n'
        'update Cars set driver = "Babbage", active = false where id == 1\n'
        "delete from Cars where active == false\n"
    )

    assert "CREATE TABLE Cars" in generated
    assert "id numeric PRIMARY KEY" in generated
    assert "driver text NOT NULL UNIQUE" in generated
    assert "active boolean" in generated
    assert "payload jsonb" in generated
    assert "score numeric CHECK (score > 0)" in generated
    assert (
        "INSERT INTO Cars (id, driver, active, payload) "
        "VALUES (1, 'Ada', true, jsonb_build_object('team', 'red'))"
    ) in generated
    assert (
        "UPDATE Cars SET driver = 'Babbage', active = false WHERE (id = 1)"
    ) in generated
    assert "DELETE FROM Cars WHERE (active = false)" in generated


def test_sql_codegen_emits_extended_filters_and_ddl():
    generated = _compile_sql(
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

    assert "name LIKE 'A%'" in generated
    assert "id IN (1, 2)" in generated
    assert "score BETWEEN 10 AND 20" in generated
    assert "deleted_at IS NULL" in generated
    assert "ALTER TABLE Cars ADD COLUMN pace text" in generated
    assert "ALTER TABLE Cars DROP COLUMN old_pace" in generated
    assert "ALTER TABLE Cars ALTER COLUMN score TYPE numeric" in generated
    assert "CREATE INDEX idx_cars_name ON Cars (name)" in generated
    assert "CREATE UNIQUE INDEX idx_cars_id ON Cars (id)" in generated
    assert "CREATE VIEW FastCars AS" in generated
    assert "DROP INDEX idx_cars_name" in generated
    assert "DROP VIEW FastCars" in generated
    assert "TRUNCATE TABLE Cars" in generated
    assert "DROP TABLE Cars" in generated
    assert "CREATE DATABASE RaceDb" in generated
    assert "DROP DATABASE RaceDb" in generated


def test_taxonomy_dictionary_resolves_themed_sql_dml_tokens():
    dictionary = TaxonomyThemeDictionary(
        theme="Formula yaris",
        mappings={
            "sql_kw_create_table": "garaj_kur",
            "sql_kw_primary_key": "ana_capa",
            "sql_kw_not_null": "bos_olmaz",
            "sql_kw_unique": "tek_incidir",
            "sql_data_modification_insert_into": "pite_yaz",
            "sql_kw_values": "tur_degeri",
            "sql_kw_update": "araci_guncelle",
            "sql_kw_set": "ayarla",
            "sql_kw_delete": "pisten_sil",
            "sql_kw_from": "garajdan",
            "sql_kw_where": "filtrele",
        },
    )

    generated = _compile_sql(
        "garaj_kur Cars (id int ana_capa, driver str bos_olmaz tek_incidir)\n"
        'pite_yaz Cars (id, driver) tur_degeri (7, "Senna")\n'
        'araci_guncelle Cars ayarla driver = "Prost" filtrele id == 7\n'
        "pisten_sil garajdan Cars filtrele id == 7\n",
        dictionary,  # type: ignore[arg-type]
    )

    assert "CREATE TABLE Cars" in generated
    assert "id numeric PRIMARY KEY" in generated
    assert "driver text NOT NULL UNIQUE" in generated
    assert "INSERT INTO Cars (id, driver) VALUES (7, 'Senna')" in generated
    assert "UPDATE Cars SET driver = 'Prost' WHERE (id = 7)" in generated
    assert "DELETE FROM Cars WHERE (id = 7)" in generated


def test_taxonomy_dictionary_resolves_themed_sql_ddl_and_filters():
    dictionary = TaxonomyThemeDictionary(
        theme="Deniz alti",
        mappings={
            "sql_query_basics_select": "sonar_sec",
            "sql_kw_from": "batiktan",
            "sql_kw_where": "suz",
            "sql_kw_like": "dalga_gibi",
            "sql_kw_in": "icinde",
            "sql_kw_between": "arasinda",
            "sql_kw_and": "ve_akinti",
            "sql_kw_is_null": "bos_mu",
            "sql_kw_alter_table": "govde_degistir",
            "sql_kw_add": "ekle",
            "sql_kw_column": "kolon",
            "sql_kw_create_index": "sonar_indeks",
            "sql_kw_drop_table": "enkazi_kaldir",
        },
    )

    generated = _compile_sql(
        'sonar_sec * batiktan Cars suz name dalga_gibi "A%" '
        "ve_akinti id icinde (1, 2) "
        "ve_akinti score arasinda 10 ve_akinti 20 "
        "ve_akinti deleted_at bos_mu\n"
        "govde_degistir Cars ekle kolon pace str\n"
        "sonar_indeks idx_cars_name on Cars (name)\n"
        "enkazi_kaldir Cars\n",
        dictionary,  # type: ignore[arg-type]
    )

    assert "SELECT *" in generated
    assert "name LIKE 'A%'" in generated
    assert "id IN (1, 2)" in generated
    assert "score BETWEEN 10 AND 20" in generated
    assert "deleted_at IS NULL" in generated
    assert "ALTER TABLE Cars ADD COLUMN pace text" in generated
    assert "CREATE INDEX idx_cars_name ON Cars (name)" in generated
    assert "DROP TABLE Cars" in generated
