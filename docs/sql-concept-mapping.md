# CodeVerse SQL Concept Mapping

CodeVerse SQL targets PostgreSQL 16. The generated output is a self-contained
SQL/PL-pgSQL script that can run with `psql` inside the CodeVerse SQL sandbox.

SQL is not treated as a toy target. General programming constructs are mapped
to PostgreSQL features with an explicit support level so unsupported behavior
fails loudly in codegen instead of producing misleading SQL.

## Runtime Shape

Each generated script contains:

1. A CodeVerse prelude with helper functions such as `_cv_append`, `_cv_get`,
   `_cv_set`, `_cv_len`, and `_cv_str`.
2. Top-level function/type declarations.
3. A `DO $main$ ... END $main$;` block for executable top-level statements.

The sandbox image `codeverse-sql-runtime:16` starts an ephemeral local
PostgreSQL server inside the container, creates a temporary database, and runs
`/workspace/main.sql` through `psql -v ON_ERROR_STOP=1`.

## Concept Support

| Universal concept | SQL strategy | Support |
| --- | --- | --- |
| Function definition | `CREATE OR REPLACE FUNCTION ... LANGUAGE plpgsql` | FULL |
| Return | `RETURN <expr>;` inside PL/pgSQL functions | FULL |
| If / elif / else | `IF / ELSIF / ELSE / END IF` | FULL |
| For loop | Integer ranges become PL/pgSQL `FOR i IN a..b LOOP` | FULL |
| While loop | `WHILE <expr> LOOP` | FULL |
| Break / continue | `EXIT;` and `CONTINUE;` | FULL |
| Variable assignment | Function-local declarations plus `:=`; top-level variables live in the `DO` block | FULL |
| Try / except | Nested `BEGIN ... EXCEPTION WHEN OTHERS THEN ... END` blocks | FULL |
| Finally | Emitted after the guarded block as ordinary PL/pgSQL statements | EMULATED |
| Import | Whitelisted PostgreSQL extensions through `CREATE EXTENSION IF NOT EXISTS` | EMULATED |
| Class definition | Composite type plus standalone methods named `<Class>_<method>` | EMULATED |
| List literals | `jsonb_build_array(...)` | FULL |
| Dictionary literals | `jsonb_build_object(...)` | FULL |
| List append/remove | `_cv_append(jsonb, jsonb)` and `_cv_remove(jsonb, jsonb)` | FULL |
| Contains | `_cv_contains(jsonb, jsonb)` for arrays and object keys | FULL |
| Dictionary get/set/delete | `_cv_get`, `_cv_set`, `_cv_del` | FULL |
| Dictionary keys/values | `_cv_keys`, `_cv_values` | FULL |

## Important Semantic Choices

### JSONB Collections

Lists and dictionaries are represented as `jsonb`. This keeps mixed primitive
values usable across SQL expressions without creating a separate table model
for every collection. Helper functions normalize the common operations that
the UASL exposes.

### Indexing

CodeVerse source uses zero-based indexing. PostgreSQL JSONB arrays are also
zero-based for `->`, so `_cv_get` and `_cv_del` preserve source-level indexing.

### Class Emulation

A CodeVerse class becomes a PostgreSQL composite type:

```sql
CREATE TYPE Player AS (
  name text,
  score numeric
);
```

Methods become standalone functions with a `self` composite argument:

```sql
CREATE FUNCTION Player_add_score(self Player, value numeric) ...
```

**Self-mutation semantics.** PostgreSQL functions cannot mutate their
arguments, so a method that assigns to `self.<field>` anywhere in its body is
emitted with `RETURNS <Class>` and every return path yields `self` (any
user-written return value in such a method is overridden). At the call site,
a statement-position method call on a class-typed variable is rewritten to a
reassignment so the mutation actually takes effect:

```sql
-- source:  o.puan_ekle(5)
o := Oyuncu_puan_ekle(o, 5);
```

Consequence: a mutating method's return value cannot be consumed as an
expression in SQL — read the field afterwards instead (`o.puan`). Non-mutating
methods keep their inferred return type and behave like ordinary functions.

Inheritance is intentionally unsupported for SQL. If a source program requests
inheritance, codegen must raise a `CodegenError`.

### Error Handling

`try/except` maps to PL/pgSQL exception blocks. The caught error message can be
read from `SQLERRM` by generated code. This is a PostgreSQL-specific behavior,
so non-PostgreSQL SQL dialects are outside the current contract.

### Output

Print statements compile to `RAISE NOTICE`. The SQL sandbox captures `psql`
stdout/stderr; user-facing API layers may normalize PostgreSQL notice formatting
before returning execution output.
