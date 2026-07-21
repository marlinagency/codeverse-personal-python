""".cvl file format.

    @theme: <free text theme, may contain spaces>
    @language: <registered codegen target, e.g. python | sql>
    @version: 1
    ---
    <themed source body>

Header keys are strict: all three are required, unknown keys rejected, and
the separator line ``---`` is mandatory. Body line numbers are preserved for
diagnostics by counting header lines.
"""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_FORMAT_VERSIONS = frozenset({1})

#: Fallback header values used when the editor sends header-less source (the
#: common "just type code and hit Run" case). ``@theme`` is informational only
#: — the real theme comes from the ThemeDictionary passed to the pipeline — so
#: any placeholder is fine; the language is what actually selects codegen.
DEFAULT_HEADER_THEME = "canonical"
DEFAULT_HEADER_LANGUAGE = "python"


class CvlFormatError(Exception):
    def __init__(self, message: str, line: int = 1) -> None:
        self.message = message
        self.line = line
        super().__init__(f"{message} (line {line})")


@dataclass(frozen=True)
class CvlDocument:
    theme: str
    language: str
    version: int
    body: str
    #: how many lines the header occupies (incl. ``---``) — diagnostics on
    #: the body must add this offset to map back to file line numbers.
    body_line_offset: int


def _is_headerless(content: str) -> bool:
    """True when the first non-blank line is not an ``@key`` header line.

    This is the "user typed plain code, no header" case. A partial or malformed
    header (first real line starts with ``@``) is NOT header-less — those still
    hit the strict parser so the user learns the exact format mistake.
    """
    for raw in content.split("\n"):
        line = raw.strip()
        if not line:
            continue
        return not line.startswith("@")
    return True  # only blanks / empty: nothing to parse as a header


def parse_cvl(
    content: str,
    *,
    default_theme: str | None = None,
    default_language: str | None = None,
) -> CvlDocument:
    """Parse a ``.cvl`` document.

    When ``default_language`` is given and ``content`` has no header block, the
    whole content is treated as the body and a default header is synthesized in
    memory. ``body_line_offset`` stays 0 so diagnostics line up with what the
    user sees in the editor (there is no header on screen to offset past).
    """
    if default_language is not None and _is_headerless(content):
        return CvlDocument(
            theme=default_theme or DEFAULT_HEADER_THEME,
            language=default_language.lower(),
            version=1,
            body=content,
            body_line_offset=0,
        )

    lines = content.split("\n")
    header: dict[str, str] = {}
    separator_index: int | None = None

    for i, raw in enumerate(lines):
        line = raw.strip()
        if line == "---":
            separator_index = i
            break
        if not line:
            continue
        if not line.startswith("@"):
            if all(k in header for k in ("theme", "language", "version")):
                raise CvlFormatError(
                    "missing the '---' line that separates the header from the body",
                    i + 1,
                )
            raise CvlFormatError(
                "every header line must be in '@key: value' form "
                "(e.g. '@theme: valorant')",
                i + 1,
            )
        if ":" not in line:
            raise CvlFormatError(f"header line is missing ':': {line!r}", i + 1)
        key, _, value = line[1:].partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key not in ("theme", "language", "version"):
            raise CvlFormatError(f"unknown header key: '@{key}'", i + 1)
        if key in header:
            raise CvlFormatError(f"header '@{key}' is defined twice", i + 1)
        if not value:
            raise CvlFormatError(f"header '@{key}' has an empty value", i + 1)
        header[key] = value

    if separator_index is None:
        raise CvlFormatError("missing the '---' line that separates the header from the body")

    missing = [k for k in ("theme", "language", "version") if k not in header]
    if missing:
        raise CvlFormatError(
            "missing header(s): " + ", ".join(f"@{k}" for k in missing)
        )

    try:
        version = int(header["version"])
    except ValueError:
        raise CvlFormatError(f"@version must be an integer: {header['version']!r}") from None
    if version not in SUPPORTED_FORMAT_VERSIONS:
        raise CvlFormatError(f"unsupported format version: {version}")

    return CvlDocument(
        theme=header["theme"],
        language=header["language"].lower(),
        version=version,
        body="\n".join(lines[separator_index + 1 :]),
        body_line_offset=separator_index + 1,
    )
