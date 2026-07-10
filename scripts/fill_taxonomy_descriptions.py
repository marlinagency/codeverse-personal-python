"""Taxonomy Step 4: fill original, copyright-safe descriptions.

This script intentionally does NOT read cached W3Schools HTML or scraped prose.
It uses only Step 3 metadata (concept_id, language, category, tier, title, and
real_syntax) to author short original descriptions. Run it after
``build_taxonomy.py`` whenever the taxonomy is regenerated.

Usage:
    python scripts/fill_taxonomy_descriptions.py
    python scripts/fill_taxonomy_descriptions.py --check
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TAXONOMY_DIR = ROOT / "scripts" / "taxonomy"
TAXONOMY_FILES = ("taxonomy_python.json", "taxonomy_sql.json")


_PY_BUILTIN_ACTIONS = {
    "abs": "returns the absolute magnitude of a numeric value",
    "all": "checks whether every item in an iterable is truthy",
    "any": "checks whether at least one item in an iterable is truthy",
    "ascii": "returns a printable representation with non-ASCII characters escaped",
    "bin": "formats an integer as a binary string",
    "bool": "converts a value to its boolean truth value",
    "bytearray": "creates a mutable sequence of bytes",
    "bytes": "creates an immutable bytes object",
    "callable": "checks whether a value can be called like a function",
    "chr": "converts a Unicode code point to its character",
    "compile": "turns source text into a code object",
    "complex": "creates a complex number",
    "delattr": "removes an attribute from an object",
    "dict": "creates or converts data into a dictionary",
    "dir": "lists names available on an object or in the current scope",
    "divmod": "returns quotient and remainder together",
    "enumerate": "pairs iterable items with their index",
    "eval": "evaluates a Python expression from text",
    "exec": "runs dynamically supplied Python code",
    "filter": "keeps iterable items that pass a predicate",
    "float": "converts a value to a floating-point number",
    "format": "formats a value according to a format specification",
    "frozenset": "creates an immutable set",
    "getattr": "reads an attribute by name",
    "globals": "returns the current global namespace dictionary",
    "hasattr": "checks whether an object has a named attribute",
    "hash": "returns an object's hash value",
    "help": "opens interactive help for an object or topic",
    "hex": "formats an integer as a hexadecimal string",
    "id": "returns the runtime identity number of an object",
    "input": "reads a line of text from standard input",
    "int": "converts a value to an integer",
    "isinstance": "checks whether an object belongs to a type or tuple of types",
    "issubclass": "checks whether one class inherits from another",
    "iter": "returns an iterator for an object",
    "len": "returns the number of items in a container",
    "list": "creates or converts data into a list",
    "locals": "returns the current local namespace dictionary",
    "map": "applies a function to each item from one or more iterables",
    "max": "returns the largest item or argument",
    "memoryview": "creates a view over binary data without copying it",
    "min": "returns the smallest item or argument",
    "next": "retrieves the next value from an iterator",
    "object": "creates the base object type",
    "oct": "formats an integer as an octal string",
    "open": "opens a file and returns a file object",
    "ord": "returns the Unicode code point of a character",
    "pow": "raises a number to a power, optionally modulo another value",
    "print": "writes values to standard output",
    "property": "declares managed attribute access on a class",
    "range": "creates an arithmetic sequence of integers",
    "repr": "returns an unambiguous string representation of a value",
    "reversed": "iterates over items in reverse order",
    "round": "rounds a number to a requested precision",
    "set": "creates or converts data into a set",
    "setattr": "sets an attribute by name",
    "slice": "creates an index range object for slicing",
    "sorted": "returns a sorted list from an iterable",
    "staticmethod": "defines a function that does not receive class or instance state",
    "str": "converts a value to text",
    "sum": "adds numeric items from an iterable",
    "super": "returns a proxy for parent-class behavior",
    "tuple": "creates or converts data into a tuple",
    "type": "returns or creates a type object",
    "vars": "returns the attribute dictionary for an object",
    "zip": "combines parallel iterables into tuples",
}

_PY_METHOD_ACTIONS = {
    "capitalize": "returns text with its first character capitalized",
    "casefold": "normalizes text for aggressive case-insensitive comparison",
    "center": "pads text so it is centered inside a requested width",
    "count": "counts matching values or substrings",
    "encode": "converts text into bytes using an encoding",
    "endswith": "checks whether text ends with a suffix",
    "expandtabs": "replaces tab characters with spaces",
    "find": "returns the first index of a substring or -1 when absent",
    "format": "substitutes values into placeholder fields",
    "format_map": "formats text from a mapping object",
    "index": "returns the position of a value and errors when it is absent",
    "isalnum": "checks whether all characters are letters or digits",
    "isalpha": "checks whether all characters are alphabetic",
    "isascii": "checks whether all characters are ASCII",
    "isdecimal": "checks whether all characters are decimal digits",
    "isdigit": "checks whether all characters are digit characters",
    "isidentifier": "checks whether text can be used as a Python identifier",
    "islower": "checks whether cased characters are lowercase",
    "isnumeric": "checks whether all characters are numeric",
    "isprintable": "checks whether text contains only printable characters",
    "isspace": "checks whether all characters are whitespace",
    "istitle": "checks whether text follows title-case rules",
    "isupper": "checks whether cased characters are uppercase",
    "join": "combines iterable text fragments with a separator",
    "ljust": "pads text on the right to reach a width",
    "lower": "returns a lowercase copy of text",
    "lstrip": "removes leading characters from text",
    "maketrans": "creates a translation table for character replacement",
    "partition": "splits text into a before, separator, and after tuple",
    "replace": "returns text with matching fragments replaced",
    "rfind": "finds the last occurrence of a substring",
    "rindex": "returns the last index of a value and errors when absent",
    "rjust": "pads text on the left to reach a width",
    "rpartition": "splits text from the right into three parts",
    "rsplit": "splits text from the right into a list",
    "rstrip": "removes trailing characters from text",
    "split": "splits text into a list of pieces",
    "splitlines": "splits text at line boundaries",
    "startswith": "checks whether text begins with a prefix",
    "strip": "removes leading and trailing characters from text",
    "swapcase": "switches uppercase letters to lowercase and the reverse",
    "title": "returns title-cased text",
    "translate": "maps characters through a translation table",
    "upper": "returns an uppercase copy of text",
    "zfill": "pads text with leading zeroes",
    "append": "adds one item to the end of the container",
    "clear": "removes all items from the container",
    "copy": "creates a shallow copy of the container",
    "extend": "adds multiple items from another iterable",
    "insert": "places an item at a specific position",
    "pop": "removes and returns an item",
    "remove": "removes a matching item",
    "reverse": "reverses item order in place",
    "sort": "orders list items in place",
    "fromkeys": "creates a dictionary with chosen keys and a shared value",
    "get": "reads a dictionary value with an optional fallback",
    "items": "returns key-value pairs from a dictionary",
    "keys": "returns dictionary keys",
    "popitem": "removes and returns a dictionary key-value pair",
    "update": "merges new values into a container",
    "values": "returns dictionary values",
    "add": "inserts one item into a set",
    "difference": "returns items present in one set but not another",
    "difference_update": "removes items found in another set",
    "discard": "removes a set item if it exists",
    "intersection": "returns items shared by sets",
    "intersection_update": "keeps only items shared by sets",
    "isdisjoint": "checks whether sets have no items in common",
    "issubset": "checks whether all items are contained in another set",
    "issuperset": "checks whether all items from another set are contained here",
    "symmetric_difference": "returns items that appear in exactly one set",
    "symmetric_difference_update": "keeps items that appear in exactly one set",
    "union": "returns a set containing items from all inputs",
    "close": "closes an open file handle",
    "fileno": "returns the operating-system file descriptor",
    "flush": "forces buffered file data to be written",
    "isatty": "checks whether a file is connected to a terminal",
    "read": "reads data from a file",
    "readable": "checks whether a file supports reading",
    "readline": "reads one line from a file",
    "readlines": "reads file lines into a list",
    "seek": "moves the file cursor",
    "seekable": "checks whether the file cursor can move",
    "tell": "returns the current file cursor position",
    "truncate": "resizes a file",
    "writable": "checks whether a file supports writing",
    "write": "writes data to a file",
    "writelines": "writes multiple lines to a file",
}

_PY_EXCEPTION_ACTIONS = {
    "ArithmeticError": "covers failures from numeric calculations",
    "AssertionError": "signals that an assert condition failed",
    "AttributeError": "signals that an attribute lookup or assignment failed",
    "ImportError": "signals that importing a module or name failed",
    "IndentationError": "signals invalid indentation in Python source",
    "IndexError": "signals that a sequence index is out of range",
    "KeyError": "signals that a mapping key is missing",
    "NameError": "signals that a name is not defined in the current scope",
    "OverflowError": "signals that a numeric result is too large to represent",
    "TypeError": "signals that an operation received an incompatible type",
    "ValueError": "signals that a value has the right type but invalid content",
    "ZeroDivisionError": "signals division or modulo by zero",
}

_PY_CATEGORY_PHRASES = {
    "basics": "basic Python source structure",
    "control_flow": "control-flow logic",
    "data_structures": "Python container handling",
    "dsa": "data-structure or algorithm practice",
    "error_handling": "exception-handling flow",
    "file_io": "file input and output",
    "functions": "function definition or invocation",
    "lib_datascience": "data-science library usage",
    "lib_matplotlib": "Matplotlib plotting usage",
    "lib_mongodb": "MongoDB access from Python",
    "lib_mysql": "MySQL access from Python",
    "modules": "module or package usage",
    "oop": "object-oriented Python design",
    "operators": "operator behavior",
    "recipes": "a practical Python recipe",
    "strings": "string handling",
    "types": "Python type handling",
    "variables": "variable binding and scope",
}

_SQL_KEYWORD_ACTIONS = {
    "SELECT": "chooses columns or expressions for a result set",
    "SELECT DISTINCT": "returns only unique result rows for selected expressions",
    "FROM": "names the source table or subquery for a query",
    "WHERE": "filters rows before grouping or projection",
    "ORDER BY": "sorts query results by one or more expressions",
    "GROUP BY": "groups rows so aggregate calculations can run per group",
    "HAVING": "filters grouped rows after aggregation",
    "INSERT INTO": "adds new rows to a table",
    "UPDATE": "changes existing rows in a table",
    "DELETE": "removes rows from a table",
    "VALUES": "provides literal row values for insertion",
    "JOIN": "combines rows from related tables",
    "INNER JOIN": "keeps only rows that match on both joined sides",
    "LEFT JOIN": "keeps all left-side rows and matching right-side data",
    "RIGHT JOIN": "keeps all right-side rows and matching left-side data",
    "FULL OUTER JOIN": "keeps matched and unmatched rows from both sides",
    "UNION": "combines result sets while removing duplicates",
    "UNION ALL": "combines result sets without removing duplicates",
    "CREATE TABLE": "defines a new table structure",
    "ALTER TABLE": "changes an existing table definition",
    "DROP TABLE": "removes a table definition and its data",
    "CREATE DATABASE": "creates a database container",
    "DROP DATABASE": "removes a database container",
    "CREATE INDEX": "creates an index to speed up lookups",
    "CREATE VIEW": "defines a saved query as a virtual table",
    "CREATE PROCEDURE": "defines a stored routine in the database",
    "CASE": "chooses a value from conditional branches",
    "AND": "requires both filter conditions to be true",
    "OR": "accepts rows where at least one condition is true",
    "NOT": "negates a filter condition",
    "IN": "checks whether a value appears in a set",
    "BETWEEN": "checks whether a value falls inside a range",
    "LIKE": "matches text against a pattern",
    "IS NULL": "checks for missing SQL values",
    "EXISTS": "checks whether a subquery returns any row",
    "ANY": "compares a value against at least one subquery result",
    "ALL": "compares a value against every subquery result",
}

_SQL_CATEGORY_PHRASES = {
    "aggregation": "aggregate query logic",
    "conditional": "conditional SQL expression logic",
    "constraints": "table constraint behavior",
    "data_modification": "data-changing SQL statements",
    "database_ddl": "database-level definition statements",
    "filtering": "row filtering logic",
    "indexes_views": "index or view definitions",
    "joins": "multi-table query composition",
    "keywords_misc": "general SQL keyword usage",
    "procedures": "stored procedure or procedural SQL behavior",
    "query_basics": "core query syntax",
    "string_numeric_functions": "SQL string or numeric function usage",
    "subqueries": "subquery-based filtering",
    "table_ddl": "table definition statements",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxonomy-dir", type=Path, default=DEFAULT_TAXONOMY_DIR)
    parser.add_argument("--check", action="store_true", help="Validate without writing.")
    args = parser.parse_args()

    failures: list[str] = []
    changed = 0
    for filename in TAXONOMY_FILES:
        path = args.taxonomy_dir / filename
        concepts = json.loads(path.read_text(encoding="utf-8"))
        for concept in concepts:
            description = describe(concept)
            if not _valid_description(description):
                failures.append(f"{filename}:{concept['concept_id']}: {description!r}")
            if args.check and concept.get("description") != description:
                failures.append(
                    f"{filename}:{concept['concept_id']}: description is stale or missing"
                )
            if concept.get("description") != description:
                changed += 1
                if not args.check:
                    concept["description"] = description
        if not args.check:
            path.write_text(
                json.dumps(concepts, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    if failures:
        for failure in failures:
            print(failure)
        return 1

    if args.check:
        print("taxonomy descriptions are valid")
    else:
        print(f"filled/updated {changed} taxonomy descriptions")
    return 0


def describe(concept: dict) -> str:
    if concept["language"] == "python":
        return _describe_python(concept)
    if concept["language"] == "sql":
        return _describe_sql(concept)
    raise ValueError(f"unsupported language: {concept['language']}")


def _describe_python(concept: dict) -> str:
    title = _clean_title(concept["title"], "Python")
    category = concept["category"]
    tier = concept["tier"]
    name = _callable_name(title)

    if tier == "builtin":
        action = _PY_BUILTIN_ACTIONS.get(name, f"performs the built-in operation named {name}")
        return f"Represents the Python built-in `{name}()`, which {action}."

    if tier == "method":
        owner = _python_method_owner(category)
        action = _PY_METHOD_ACTIONS.get(name, f"performs the `{name}` operation for {owner}")
        return f"Represents the `{name}()` {owner} method, which {action}."

    if tier == "exception":
        action = _PY_EXCEPTION_ACTIONS.get(title, "represents a runtime error condition")
        return f"Represents the Python exception `{title}`, which {action}."

    if tier == "library":
        phrase = _PY_CATEGORY_PHRASES.get(category, "external Python library usage")
        return (
            f"Represents the {title} library concept for {phrase}; it is themeable, "
            "but sandbox support depends on the installed package and runtime."
        )

    if category == "keywords":
        return f"Represents the Python keyword `{title}`, used as part of core language syntax."

    phrase = _PY_CATEGORY_PHRASES.get(category, "Python language behavior")
    return f"Represents {phrase} for {title}, giving the theming engine a named Python construct."


def _describe_sql(concept: dict) -> str:
    title = _clean_title(concept["title"], "SQL")
    category = concept["category"]
    tier = concept["tier"]
    upper_title = title.upper()

    if tier == "library":
        fn = _sql_function_name(title)
        return (
            f"Represents the SQL dialect function `{fn}`, a themeable library-tier "
            "name whose sandbox support depends on the selected database engine."
        )

    action = _SQL_KEYWORD_ACTIONS.get(upper_title)
    if action:
        return f"Represents the SQL construct `{upper_title}`, which {action}."

    phrase = _SQL_CATEGORY_PHRASES.get(category, "SQL language behavior")
    return f"Represents {phrase} for {title}, giving the theming engine a named SQL construct."


def _clean_title(title: str, language_prefix: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    cleaned = re.sub(rf"^{re.escape(language_prefix)}\s+", "", cleaned, flags=re.I)
    return cleaned


def _callable_name(title: str) -> str:
    match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\(\)$", title.strip())
    if match:
        return match.group(1)
    return re.sub(r"[^A-Za-z0-9_]+", "_", title.strip()).strip("_").lower()


def _python_method_owner(category: str) -> str:
    return {
        "string_methods": "string",
        "list_methods": "list",
        "dict_methods": "dictionary",
        "set_methods": "set",
        "tuple_methods": "tuple",
        "file_methods": "file object",
    }.get(category, "object")


def _sql_function_name(title: str) -> str:
    return re.sub(r"\(\)$", "", title.strip()).upper()


def _valid_description(description: str) -> bool:
    if not description or len(description) > 260:
        return False
    if "\n" in description:
        return False
    if not description.endswith("."):
        return False
    if "W3Schools" in description:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
