"""Line-oriented themed->canonical translation, for the translation panel.

The lexer already resolves tokens for parsing; this resolver exists for the
UI feature that shows, per line, "what you wrote" next to "what it means in
the canonical DSL" — and for tooling that needs pure text substitution
without a full parse.
"""

from __future__ import annotations

from codeverse_core.lexer.lexer import Lexer
from codeverse_core.lexer.tokens import TokenType
from codeverse_core.theme_mapping.dictionary import ThemeDictionary


class TokenResolver:
    def __init__(self, dictionary: ThemeDictionary) -> None:
        self._dictionary = dictionary

    def resolve_source(self, source: str) -> list[tuple[int, str, str]]:
        """Return (line_no, themed_line, canonical_line) for each source line.

        Comments and blank lines pass through unchanged. Raises LexError on
        malformed input (same rules as compilation).
        """
        tokens = Lexer(source, self._dictionary).tokenize()
        substitutions: dict[int, list[tuple[int, str, str]]] = {}
        for tok in tokens:
            if tok.concept is not None and tok.themed_text != tok.resolved_text:
                substitutions.setdefault(tok.line, []).append(
                    (tok.col, tok.themed_text, tok.resolved_text)
                )
            elif tok.type is TokenType.STRING:
                # strings must never be substituted; nothing to record, the
                # positional replacement below only touches recorded spans
                pass

        result: list[tuple[int, str, str]] = []
        for line_no, line in enumerate(source.split("\n"), start=1):
            line = line.rstrip("\r")
            subs = sorted(substitutions.get(line_no, []), reverse=True)
            canonical = line
            for col, themed, resolved in subs:
                start = col - 1
                canonical = canonical[:start] + resolved + canonical[start + len(themed):]
            result.append((line_no, line, canonical))
        return result
