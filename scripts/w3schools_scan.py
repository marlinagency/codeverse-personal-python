"""W3Schools taxonomy scanner — Taksonomi Planı Adım 1.

Crawls the W3Schools Python Tutorial and SQL Tutorial left-hand navigation
menus and, for each linked page, extracts ONLY:

  - the category (from the <h2 class="left"> menu section headers)
  - the topic title (the link text)
  - the URL
  - the "Syntax" code block(s) on that page, if any (e.g.
    "string.split(separator, maxsplit)" or "SELECT column1, column2 FROM
    table_name") — function/method/statement SIGNATURES only.

Per the project's copyright boundary (see plan Adım 0): explanation
paragraphs, prose, and example write-ups are NEVER collected here. The
"description" field is intentionally left null — it gets filled in later
with ORIGINAL wording (Adım 4), never copied from the source site.

Usage:
    python w3schools_scan.py --language python
    python w3schools_scan.py --language sql
    python w3schools_scan.py --language both
    python w3schools_scan.py --language python --limit 20   # quick smoke test
    python w3schools_scan.py --language python --refresh    # ignore HTML cache

Output:
    w3schools/output/ham_python_menu.json
    w3schools/output/ham_sql_menu.json

Each entry:
    {
      "category": "Python Strings",
      "title": "String split() Method",
      "url": "https://www.w3schools.com/python/ref_string_split.asp",
      "syntax": ["string.split(separator, maxsplit)"],
      "description": null
    }
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import re
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("w3schools_scan")

BASE_URL = "https://www.w3schools.com"
USER_AGENT = (
    "CodeVerseTaxonomyBot/1.0 (+educational-taxonomy-research; "
    "collects only code syntax signatures, no prose; see project's "
    "copyright-boundary plan)"
)
REQUEST_TIMEOUT = 15
DEFAULT_DELAY_SECONDS = 0.4

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "w3schools" / "output"
CACHE_DIR = SCRIPT_DIR / "w3schools" / "cache"

MENU_HOME_PATHS = {
    "python": "/python/python_intro.asp",
    "sql": "/sql/default.asp",
}

# Menu links that are navigational noise, not real topic pages, or link
# outside the tutorial (home links, cross-links to other language tutorials,
# the reference/example index pages themselves duplicate content we already
# capture per-item elsewhere).
_SKIP_HREF_PATTERNS = (
    re.compile(r"^default\.asp$", re.IGNORECASE),
    re.compile(r"^javascript:", re.IGNORECASE),
    re.compile(r"^mailto:", re.IGNORECASE),
    re.compile(r"^#"),
)

_SYNTAX_HEADING_RE = re.compile(r"syntax\s*$", re.IGNORECASE)


@dataclasses.dataclass
class MenuEntry:
    category: str
    title: str
    url: str


@dataclasses.dataclass
class ScannedPage:
    category: str
    title: str
    url: str
    syntax: list[str]
    #: every runnable code block on the page (Syntax boxes AND Example boxes)
    #: — the comprehensive "everything that is code" collection.
    code_examples: list[str]
    description: None = None


class W3SchoolsScanner:
    def __init__(
        self,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        use_cache: bool = True,
    ) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        self._delay = delay_seconds
        self._use_cache = use_cache
        self._robots = urllib.robotparser.RobotFileParser()
        self._robots.set_url(urljoin(BASE_URL, "/robots.txt"))
        try:
            self._robots.read()
        except Exception:  # noqa: BLE001 - crawling still proceeds; robots.txt
            logger.warning("robots.txt okunamadı, disallow kontrolü atlanıyor")
            self._robots = None

    # ------------------------------------------------------------- fetching

    def _allowed(self, url: str) -> bool:
        if self._robots is None:
            return True
        return self._robots.can_fetch(USER_AGENT, url)

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", urlparse(url).path.strip("/"))
        return CACHE_DIR / f"{safe_name}__{digest}.html"

    def fetch(self, url: str) -> str:
        if not self._allowed(url):
            raise PermissionError(f"robots.txt bu URL'i yasaklıyor: {url}")

        cache_path = self._cache_path(url)
        if self._use_cache and cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

        time.sleep(self._delay)
        resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        html = resp.text

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding="utf-8")
        return html

    # ---------------------------------------------------------------- menu

    def crawl_menu(self, language: str) -> list[MenuEntry]:
        home_path = MENU_HOME_PATHS[language]
        home_url = urljoin(BASE_URL, home_path)
        html = self.fetch(home_url)
        soup = BeautifulSoup(html, "html.parser")

        menu_root = soup.find(id="leftmenuinnerinner")
        if menu_root is None:
            raise RuntimeError(
                f"'#leftmenuinnerinner' menü kapsayıcısı bulunamadı — "
                f"W3Schools sayfa yapısı değişmiş olabilir ({home_url})"
            )

        entries: list[MenuEntry] = []
        seen_urls: set[str] = set()
        current_category = language.upper()

        for node in menu_root.find_all(["h2", "a"], recursive=True):
            if node.name == "h2":
                raw_category = node.get_text(separator=" ", strip=True)
                current_category = re.sub(r"\s+", " ", raw_category).strip() or current_category
                continue

            # node.name == "a"
            href = node.get("href")
            if not href:
                continue
            if any(pat.search(href) for pat in _SKIP_HREF_PATTERNS):
                continue

            absolute_url = urljoin(home_url, href)
            # keep only same-tutorial pages (avoid cross-links to other
            # W3Schools tutorials that sometimes appear in shared menu chrome)
            if urlparse(absolute_url).path.split("/")[1] != language:
                continue
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)

            title = node.get_text(strip=True)
            if not title:
                continue

            entries.append(MenuEntry(category=current_category, title=title, url=absolute_url))

        if language == "python":
            entries = self._expand_python_reference_index_pages(entries)

        return entries

    def _expand_python_reference_index_pages(self, entries: list[MenuEntry]) -> list[MenuEntry]:
        """Python's left menu only lists index pages (e.g. "Python String
        Methods" -> python_ref_string.asp); the ~300 individual method/
        keyword/exception pages live in a <table class="ws-table-all"> on
        each index page. Replace each expandable index entry with its
        table's row links (name + href only — never the description column).
        """
        expanded: list[MenuEntry] = []
        seen_urls = {e.url for e in entries}

        for entry in entries:
            if entry.category != "Python Reference":
                expanded.append(entry)
                continue

            try:
                html = self.fetch(entry.url)
            except (requests.RequestException, PermissionError) as exc:
                logger.warning("index sayfası alınamadı: %s — %s", entry.url, exc)
                expanded.append(entry)
                continue

            soup = BeautifulSoup(html, "html.parser")
            tables = soup.find_all("table", class_="ws-table-all")
            if not tables:
                expanded.append(entry)  # not a table index page (e.g. Glossary) — keep as-is
                continue

            child_count = 0
            for table in tables:
                for row in table.find_all("tr"):
                    cells = row.find_all("td")
                    if not cells:
                        continue  # header row
                    link = cells[0].find("a")
                    if link is None or not link.get("href"):
                        continue
                    child_url = urljoin(entry.url, link["href"])
                    if child_url in seen_urls:
                        continue
                    seen_urls.add(child_url)
                    child_title = link.get_text(strip=True)
                    if not child_title:
                        continue
                    expanded.append(
                        MenuEntry(category=entry.title, title=child_title, url=child_url)
                    )
                    child_count += 1

            if child_count == 0:
                expanded.append(entry)  # table existed but had no usable rows

        return expanded

    # ------------------------------------------------------------- syntax

    def extract_syntax(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[str] = []

        for heading in soup.find_all(["h2", "h3"]):
            text = heading.get_text(strip=True)
            if not _SYNTAX_HEADING_RE.search(text):
                continue

            code_block = self._find_next_code_block(heading)
            if code_block is None:
                continue

            syntax_text = self._normalize_code_text(code_block)
            if syntax_text and syntax_text not in results:
                results.append(syntax_text)

        return results

    def _find_next_code_block(self, heading: Tag) -> Tag | None:
        """Walk forward from a "Syntax" heading to the next code container.

        W3Schools uses two known shapes:
          Python ref pages: <div class="w3-code w3-border notranslate">
          SQL pages:         <div class="w3-example ..."><code class="sqlHigh">
        Stop looking once another heading is reached (syntax block missing).
        """
        for sibling in heading.find_next_siblings():
            if sibling.name in ("h1", "h2", "h3"):
                return None
            if not isinstance(sibling, Tag):
                continue
            classes = sibling.get("class") or []
            if sibling.name == "div" and (
                "w3-code" in classes or "w3-example" in classes
            ):
                return sibling
        return None

    def _normalize_code_text(self, block: Tag) -> str:
        # <br> becomes a real newline before text extraction, then multiple
        # whitespace/newlines collapse to single spaces — signatures should
        # read as one line, e.g. "SELECT column1, column2 FROM table_name".
        for br in block.find_all("br"):
            br.replace_with("\n")
        raw = block.get_text()
        collapsed = re.sub(r"\s+", " ", raw).strip()
        return collapsed

    # -------------------------------------------------------- code blocks

    def extract_code_blocks(self, html: str) -> list[str]:
        """Every runnable code block on the page (Syntax boxes AND Example
        boxes) — not just the ones under a formal "Syntax" heading. This is
        the broader collection used to build a taxonomy comprehensive enough
        that a theme can re-skin every construct actually demonstrated in the
        tutorial, not just documented function/statement signatures.
        """
        soup = BeautifulSoup(html, "html.parser")
        containers: list[Tag] = []

        for div in soup.find_all("div", class_="w3-code"):
            containers.append(div)
        for div in soup.find_all("div", class_="w3-example"):
            # only take bare w3-example boxes (inline <code>, no nested
            # w3-code) — otherwise this would duplicate the nested block
            # already collected above.
            if div.find("div", class_="w3-code") is None:
                containers.append(div)

        results: list[str] = []
        seen: set[str] = set()
        for block in containers:
            text = self._normalize_multiline_code(block)
            if text and text not in seen:
                seen.add(text)
                results.append(text)
        return results

    def _normalize_multiline_code(self, block: Tag) -> str:
        """Reconstruct a code block's real line structure.

        W3Schools marks intentional line breaks with <br> and intentional
        indentation with literal '&nbsp;' runs; everything else (raw
        newlines/tabs in the HTML source) is just source pretty-printing and
        carries no meaning, so it is collapsed away. Best-effort: exact
        indentation width isn't always perfectly reconstructed, which is
        acceptable for raw reference material feeding later curation steps.
        """
        block = BeautifulSoup(str(block), "html.parser")  # work on a copy
        for heading in block.find_all(["h2", "h3"]):
            heading.decompose()
        for btn in block.find_all("a", class_=re.compile(r"\bw3-btn\b")):
            btn.decompose()
        for br in block.find_all("br"):
            br.replace_with("\x00BR\x00")

        raw = block.get_text()
        raw = re.sub(r"[ \t\r\n\f\v]+", " ", raw)  # collapse source formatting noise
        lines = [seg.strip(" ") for seg in raw.split("\x00BR\x00")]
        lines = [ln.replace("\xa0", " ") for ln in lines]  # nbsp = real indentation
        lines = [ln for ln in lines if ln.strip()]
        return "\n".join(lines)

    # ----------------------------------------------------------------- run

    def scan(self, language: str, limit: int | None = None) -> list[ScannedPage]:
        entries = self.crawl_menu(language)
        if limit is not None:
            entries = entries[:limit]

        logger.info("%s: %d menü girdisi bulundu, sayfalar taranıyor...", language, len(entries))

        pages: list[ScannedPage] = []
        for i, entry in enumerate(entries, start=1):
            try:
                html = self.fetch(entry.url)
                syntax = self.extract_syntax(html)
                code_examples = self.extract_code_blocks(html)
            except PermissionError as exc:
                logger.warning("atlandı (robots.txt): %s — %s", entry.url, exc)
                continue
            except requests.RequestException as exc:
                logger.warning("atlandı (istek hatası): %s — %s", entry.url, exc)
                continue

            pages.append(
                ScannedPage(
                    category=entry.category,
                    title=entry.title,
                    url=entry.url,
                    syntax=syntax,
                    code_examples=code_examples,
                )
            )
            if i % 25 == 0:
                logger.info("%s: %d/%d sayfa tarandı", language, i, len(entries))

        return pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--language", choices=["python", "sql", "both"], default="both"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="ilk N menü girdisiyle sınırla (test için)"
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="istekler arası bekleme (sn)"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="HTML önbelleğini yok sayıp yeniden indir"
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    languages = ["python", "sql"] if args.language == "both" else [args.language]
    scanner = W3SchoolsScanner(delay_seconds=args.delay, use_cache=not args.refresh)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for language in languages:
        pages = scanner.scan(language, limit=args.limit)
        out_path = args.output_dir / f"ham_{language}_menu.json"
        payload = [dataclasses.asdict(p) for p in pages]
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with_syntax = sum(1 for p in pages if p.syntax)
        logger.info(
            "%s: %d sayfa yazıldı -> %s (%d sayfada syntax bulundu)",
            language,
            len(pages),
            out_path,
            with_syntax,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
