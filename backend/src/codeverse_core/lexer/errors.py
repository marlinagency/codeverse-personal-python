from __future__ import annotations


class LexError(Exception):
    """Lexical error with 1-based source position."""

    def __init__(self, message: str, line: int, col: int) -> None:
        self.message = message
        self.line = line
        self.col = col
        super().__init__(f"{message} (satır {line}, sütun {col})")
