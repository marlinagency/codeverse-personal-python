"""Taxonomy builder — Taksonomi Planı Adım 3.

Takes the raw scanner output (ham_python_menu.json / ham_sql_menu.json) and
produces a clean, categorized taxonomy: one entry per NAMED, themeable
language construct (a keyword, operator group, builtin, method, type,
statement, clause, or exception) — not one per page and not one per code
block.

Each concept carries:
  concept_id   stable, unique id (e.g. "py_str_upper", "sql_join_left")
  language     "python" | "sql"
  category     one of the curated category slugs (see CATEGORY_* below)
  tier         how the concept participates in the theming/codegen pipeline:
                 core      - keyword/operator/statement the codegen lowers to
                             a real construct (themed token -> UASL node)
                 builtin   - a global callable name (print, len, COUNT)
                 method    - a method on a built-in type (str.upper, list.append)
                 type      - a data-type name (int, VARCHAR)
                 exception - an error/exception name
                 library   - third-party / dialect-specific construct
                             (matplotlib, mysql-connector, MySQL-only funcs).
                             Themeable as a NAME only; NOT guaranteed to run
                             error-free in the sandbox. Kept for completeness.
  real_syntax  canonical signature/syntax string (best available)
  code_examples  every runnable code block scraped for this construct
                 (kept as raw reference material for Adım 4 description
                 authoring; never shipped verbatim to users)
  description  ALWAYS null here — filled with ORIGINAL wording in Adım 4.

Design note (the Adım 3 judgment call): reference pages (String/List/Dict/
Set/Tuple/File Methods, Built-in Functions, Keywords, Exceptions) are already
atomic — one construct per page — and form the backbone. Tutorial/glossary
pages are treated as one topic-concept each. Library categories (NumPy/
Pandas/Matplotlib/MySQL/MongoDB for Python; dialect function pages for SQL)
are retained but tier-tagged 'library' so the codegen/validator can gate
them. Navigation/challenge/exercise/quiz pages are dropped as noise.

Usage:
    python build_taxonomy.py
    python build_taxonomy.py --input-dir w3schools/output --output-dir taxonomy
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger("build_taxonomy")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = SCRIPT_DIR / "w3schools" / "output"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "taxonomy"

# --------------------------------------------------------------------------
# noise filtering
# --------------------------------------------------------------------------

# Pages that are navigation, practice, or meta — never a language construct.
_NOISE_TITLE_RE = re.compile(
    r"\b(code challenge|challenge|exercise|quiz|compiler|syllabus|study plan|"
    r"bootcamp|training|interview|certificate|cert|practice|quick ?ref|"
    r"get started|overview|home|intro)\b",
    re.IGNORECASE,
)
_NOISE_URL_RE = re.compile(
    r"(challenges?|exercise|quiz|compiler|syllabus|study_plan|bootcamp|"
    r"training|interview|certificate|practice|quickref|default\.asp|"
    r"_examples\.asp|_reference\.asp|_ref_keywords\.asp|_ref_glossary\.asp|"
    r"python_reference\.asp)",
    re.IGNORECASE,
)

# Whole raw categories dropped outright (pure example/nav buckets).
_DROP_CATEGORIES = {
    "Python Examples",
    "Python Cert",
    "Python Reference",
    "SQL Examples",
    "SQL Cert",
}

# --------------------------------------------------------------------------
# Python category & tier mapping
# --------------------------------------------------------------------------

# raw W3Schools category -> (taxonomy category slug, tier)
_PY_CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "Python Built-in Functions": ("builtin_functions", "builtin"),
    "Python String Methods": ("string_methods", "method"),
    "Python List Methods": ("list_methods", "method"),
    "Python Dictionary Methods": ("dict_methods", "method"),
    "Python Set Methods": ("set_methods", "method"),
    "Python Tuple Methods": ("tuple_methods", "method"),
    "Python File Methods": ("file_methods", "method"),
    "Python Keywords": ("keywords", "core"),
    "Python Exceptions": ("exceptions", "exception"),
    "Python Classes": ("oop", "core"),
    "File Handling": ("file_io", "core"),
    "Python Modules": ("modules", "library"),
    "Module Reference": ("modules", "library"),
    "Python Matplotlib": ("lib_matplotlib", "library"),
    "Python MySQL": ("lib_mysql", "library"),
    "Python MongoDB": ("lib_mongodb", "library"),
    "Machine Learning": ("lib_datascience", "library"),
    "Python DSA": ("dsa", "library"),
    "Python How To": ("recipes", "library"),
}

# Glossary/Tutorial pages are topic concepts; route by keyword in the title
# to a curated core-language category. Order matters (first match wins).
# NOTE: \b word boundaries are essential — without them "modIFy" matches
# "if", "FORmat" matches "for", etc., silently misrouting concepts.
_PY_TOPIC_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(string|str|f-?string|concat|escape|unicode|char|slic)", re.I), "strings"),
    (re.compile(r"\b(lambda|function|argument|args|kwargs|recursion|return)\b", re.I), "functions"),
    (re.compile(r"\b(class|object|inherit|self|__init__|method|polymorph|encapsul)", re.I), "oop"),
    (re.compile(r"\b(try|except|finally|raise|error|exception)\b", re.I), "error_handling"),
    (re.compile(r"\b(import|module|package|pip|__name__)\b", re.I), "modules"),
    (re.compile(r"\b(file|open|read|write)\b", re.I), "file_io"),
    (re.compile(r"\b(list|tuple|set|dict|array|comprehension|iterat|range|enumerate|zip)", re.I), "data_structures"),
    (re.compile(r"\b(for|while|loop|break|continue|pass|if|elif|else|condition|match|case)\b", re.I), "control_flow"),
    (re.compile(r"\b(number|int|float|complex|bool|math|round|cast|convert|type)\b", re.I), "types"),
    (re.compile(r"\b(operator|arithmetic|compar|logical|bitwise|identity|membership|walrus|ternary)", re.I), "operators"),
    (re.compile(r"\b(variable|scope|global|nonlocal|del|assign|constant)", re.I), "variables"),
    (re.compile(r"\b(comment|indent|syntax|statement|print|output|input)\b", re.I), "basics"),
]
_PY_TOPIC_DEFAULT = "basics"

_PY_TOPIC_CATEGORIES = {
    "functions", "oop", "control_flow", "error_handling", "modules",
    "file_io", "data_structures", "strings", "types", "operators",
    "variables", "basics",
}

# --------------------------------------------------------------------------
# SQL category & tier mapping
# --------------------------------------------------------------------------

# SQL tutorial-topic routing (title keyword -> category). First match wins.
_SQL_TOPIC_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"inner join|left join|right join|full join|self join|\bjoin", re.I), "joins"),
    (re.compile(r"union", re.I), "joins"),
    (re.compile(r"group by|having|aggregate|count|\bsum\b|\bavg\b|\bmin\b|\bmax\b", re.I), "aggregation"),
    (re.compile(r"insert|update|delete|select into|insert into select", re.I), "data_modification"),
    (re.compile(r"where|order by|distinct|select top|\blimit\b|\bselect\b|\bfrom\b", re.I), "query_basics"),
    (re.compile(r"\band\b|\bor\b|\bnot\b|\bin\b|between|like|wildcard|null value", re.I), "filtering"),
    (re.compile(r"exists|\bany\b|\ball\b|subquer", re.I), "subqueries"),
    (re.compile(r"\bcase\b|null function|ifnull|coalesce|nullif", re.I), "conditional"),
    (re.compile(r"stored procedure|procedure|comment", re.I), "procedures"),
    (re.compile(r"alias", re.I), "query_basics"),
    (re.compile(r"operator", re.I), "operators"),
]

# SQL reference keyword -> category (sql_ref_* pages). Keyword text matched.
_SQL_KEYWORD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(create|drop|alter|truncate) table$|^add|^drop column$|^alter column$|^rename", re.I), "table_ddl"),
    (re.compile(r"constraint|primary key|foreign key|unique|check|default|not null|^references$", re.I), "constraints"),
    (re.compile(r"index|view", re.I), "indexes_views"),
    (re.compile(r"database|backup", re.I), "database_ddl"),
    (re.compile(r"join|union", re.I), "joins"),
    (re.compile(r"group by|having|order by|distinct|top|limit|offset|fetch", re.I), "query_basics"),
    (re.compile(r"select|from|as$|^as ", re.I), "query_basics"),
    (re.compile(r"insert|update|delete|set$|values|into", re.I), "data_modification"),
    (re.compile(r"where|and|^or$|not|in$|between|like|is null|is not null|exists|any|all", re.I), "filtering"),
    (re.compile(r"case|when|then|else|end", re.I), "conditional"),
    (re.compile(r"procedure|function|declare|begin|commit|rollback|transaction", re.I), "procedures"),
]
_SQL_KEYWORD_DEFAULT = "keywords_misc"


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\(\)", "", text)
    # drop a redundant leading language word so ids read "sql_joins_inner_join"
    # not "sql_joins_sql_inner_join"
    text = re.sub(r"^(python|sql)\s+", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "x"


def _pick_real_syntax(page: dict) -> str:
    if page.get("syntax"):
        return page["syntax"][0]
    # fall back to the shortest single-line code block that looks like a
    # signature (contains "(" or an all-caps SQL keyword), else the first.
    candidates = page.get("code_examples") or []
    oneliners = [c for c in candidates if "\n" not in c]
    signature_like = [c for c in oneliners if "(" in c or c.isupper()]
    for pool in (signature_like, oneliners, candidates):
        if pool:
            return min(pool, key=len)
    return ""


class TaxonomyBuilder:
    def __init__(self) -> None:
        self._seen_ids: set[str] = set()

    def _unique_id(self, base: str) -> str:
        candidate = base
        n = 2
        while candidate in self._seen_ids:
            candidate = f"{base}_{n}"
            n += 1
        self._seen_ids.add(candidate)
        return candidate

    # ---------------------------------------------------------- python

    def build_python(self, pages: list[dict]) -> list[dict]:
        concepts: list[dict] = []
        for page in pages:
            if self._is_noise(page):
                continue
            raw_cat = page["category"]
            if raw_cat in _DROP_CATEGORIES:
                continue

            mapping = _PY_CATEGORY_MAP.get(raw_cat)
            if mapping is not None:
                category, tier = mapping
                prefix = self._py_prefix(category)
                concept_id = self._unique_id(f"{prefix}_{_slug(page['title'])}")
            else:
                # Glossary / Tutorial topic pages
                category = self._route_python_topic(page["title"])
                tier = "core" if category in _PY_TOPIC_CATEGORIES else "library"
                concept_id = self._unique_id(f"py_{category}_{_slug(page['title'])}")

            if not (page.get("code_examples") or page.get("syntax")):
                continue  # keep only concepts that actually carry code

            concepts.append(self._make_concept("python", concept_id, category, tier, page))
        return concepts

    @staticmethod
    def _py_prefix(category: str) -> str:
        return {
            "builtin_functions": "py_fn",
            "string_methods": "py_str",
            "list_methods": "py_list",
            "dict_methods": "py_dict",
            "set_methods": "py_set",
            "tuple_methods": "py_tuple",
            "file_methods": "py_file",
            "keywords": "py_kw",
            "exceptions": "py_exc",
            "oop": "py_oop",
            "file_io": "py_io",
            "modules": "py_mod",
            "lib_matplotlib": "py_plt",
            "lib_mysql": "py_mysql",
            "lib_mongodb": "py_mongo",
            "lib_datascience": "py_ds",
            "dsa": "py_dsa",
            "recipes": "py_howto",
        }.get(category, "py")

    def _route_python_topic(self, title: str) -> str:
        for pattern, category in _PY_TOPIC_RULES:
            if pattern.search(title):
                return category
        return _PY_TOPIC_DEFAULT

    # ------------------------------------------------------------- sql

    def build_sql(self, pages: list[dict]) -> list[dict]:
        concepts: list[dict] = []
        for page in pages:
            if self._is_noise(page):
                continue
            if page["category"] in _DROP_CATEGORIES:
                continue
            if not (page.get("code_examples") or page.get("syntax")):
                continue

            url = page["url"]
            title = page["title"]

            if "/func_" in url:
                category, tier, prefix = self._route_sql_function(url)
                concept_id = self._unique_id(f"{prefix}_{_slug(title)}")
            elif "/sql_ref_" in url:
                category = self._route_sql_keyword(title)
                tier = "core"
                concept_id = self._unique_id(f"sql_kw_{_slug(title)}")
            elif page["category"] == "SQL Database":
                category, tier = "table_ddl", "core"
                concept_id = self._unique_id(f"sql_db_{_slug(title)}")
            else:
                category = self._route_sql_topic(title)
                tier = "core"
                concept_id = self._unique_id(f"sql_{category}_{_slug(title)}")

            concepts.append(self._make_concept("sql", concept_id, category, tier, page))
        return concepts

    def _route_sql_topic(self, title: str) -> str:
        for pattern, category in _SQL_TOPIC_RULES:
            if pattern.search(title):
                return category
        return "query_basics"

    def _route_sql_keyword(self, title: str) -> str:
        for pattern, category in _SQL_KEYWORD_RULES:
            if pattern.search(title):
                return category
        return _SQL_KEYWORD_DEFAULT

    def _route_sql_function(self, url: str) -> tuple[str, str, str]:
        name = url.split("/")[-1]
        if "func_mysql" in name:
            return "string_numeric_functions", "library", "sql_mysql"
        if "func_sqlserver" in name:
            return "string_numeric_functions", "library", "sql_mssql"
        if "func_msaccess" in name:
            return "string_numeric_functions", "library", "sql_msaccess"
        return "string_numeric_functions", "library", "sql_fn"

    # --------------------------------------------------------- shared

    def _is_noise(self, page: dict) -> bool:
        return bool(
            _NOISE_TITLE_RE.search(page["title"]) or _NOISE_URL_RE.search(page["url"])
        )

    def _make_concept(
        self, language: str, concept_id: str, category: str, tier: str, page: dict
    ) -> dict:
        return {
            "concept_id": concept_id,
            "language": language,
            "category": category,
            "tier": tier,
            "title": page["title"],
            "real_syntax": _pick_real_syntax(page),
            "code_examples": page.get("code_examples", []),
            "source_url": page["url"],
            "description": None,
        }


def _summary(concepts: list[dict]) -> str:
    from collections import Counter

    by_cat = Counter(c["category"] for c in concepts)
    by_tier = Counter(c["tier"] for c in concepts)
    lines = [f"  toplam: {len(concepts)} concept"]
    lines.append("  tier: " + ", ".join(f"{t}={n}" for t, n in by_tier.most_common()))
    lines.append("  kategoriler:")
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        with_syntax = sum(1 for c in concepts if c["category"] == cat and c["real_syntax"])
        lines.append(f"    {cat:28s} {n:4d}  (real_syntax dolu: {with_syntax})")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    builder = TaxonomyBuilder()

    py_pages = json.loads((args.input_dir / "ham_python_menu.json").read_text("utf-8"))
    py_concepts = builder.build_python(py_pages)
    (args.output_dir / "taxonomy_python.json").write_text(
        json.dumps(py_concepts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("PYTHON taksonomisi:\n%s", _summary(py_concepts))

    sql_pages = json.loads((args.input_dir / "ham_sql_menu.json").read_text("utf-8"))
    sql_concepts = builder.build_sql(sql_pages)
    (args.output_dir / "taxonomy_sql.json").write_text(
        json.dumps(sql_concepts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("SQL taksonomisi:\n%s", _summary(sql_concepts))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
