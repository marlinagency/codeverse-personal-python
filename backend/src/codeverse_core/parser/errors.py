from __future__ import annotations


class ParseError(Exception):
    """Syntax error with 1-based position and optional expectation hint.

    ``message`` is written in terms of the user's THEMED vocabulary whenever
    the expectation involves a themed keyword — the parser knows each token's
    themed spelling and the active dictionary's tokens.
    """

    def __init__(
        self,
        message: str,
        line: int,
        col: int,
        hint: str | None = None,
    ) -> None:
        self.message = message
        self.line = line
        self.col = col
        self.hint = hint
        text = f"{message} (satır {line}, sütun {col})"
        if hint:
            text += f" — {hint}"
        super().__init__(text)
