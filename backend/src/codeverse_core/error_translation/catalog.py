from __future__ import annotations

import re

from codeverse_core.concepts import UniversalConcept
from codeverse_core.theme_mapping.dictionary import ThemeDictionary


def infer_error_concepts(message: str, stage: str) -> tuple[UniversalConcept, ...]:
    """Best-effort concept tags for deterministic fallback translation."""

    folded = message.casefold()
    concepts: list[UniversalConcept] = []

    if "fonksiyon" in folded or "function" in folded:
        concepts.append(UniversalConcept.FUNCTION_DEF)
    if "return" in folded or "deger dondur" in _ascii_fold(folded):
        concepts.append(UniversalConcept.RETURN)
    if "break" in folded:
        concepts.append(UniversalConcept.BREAK)
    if "continue" in folded:
        concepts.append(UniversalConcept.CONTINUE)
    if "dongu" in _ascii_fold(folded) or "loop" in folded:
        concepts.extend([UniversalConcept.FOR, UniversalConcept.WHILE])
    if "if" in folded or "kosul" in _ascii_fold(folded):
        concepts.append(UniversalConcept.IF)
    if "try" in folded or "except" in folded or "hata yakala" in folded:
        concepts.extend([UniversalConcept.TRY, UniversalConcept.EXCEPT])
    if "undefined" in folded or "tanimsiz" in _ascii_fold(folded):
        concepts.append(UniversalConcept.IMPORT)
    if stage == "lex":
        concepts.extend([UniversalConcept.FUNCTION_DEF, UniversalConcept.IF])

    return tuple(dict.fromkeys(concepts))


def render_catalog_message(
    *,
    message: str,
    stage: str,
    dictionary: ThemeDictionary,
    concepts: tuple[UniversalConcept, ...] | None = None,
) -> str:
    """Deterministic theme-aware fallback when no LLM is available."""

    tags = concepts if concepts is not None else infer_error_concepts(message, stage)
    folded = _ascii_fold(message.casefold())

    if "fonksiyon disinda deger dondurulemez" in folded:
        return (
            f"`{dictionary.token_for(UniversalConcept.RETURN)}` sadece "
            f"`{dictionary.token_for(UniversalConcept.FUNCTION_DEF)}` blogunun "
            "icinde kullanilabilir."
        )

    if "dongu disinda 'break' kullanilamaz" in folded:
        return (
            f"`{dictionary.token_for(UniversalConcept.BREAK)}` yalnizca "
            f"`{dictionary.token_for(UniversalConcept.FOR)}` veya "
            f"`{dictionary.token_for(UniversalConcept.WHILE)}` dongusunun "
            "icinde kullanilabilir."
        )

    if "dongu disinda 'continue' kullanilamaz" in folded:
        return (
            f"`{dictionary.token_for(UniversalConcept.CONTINUE)}` yalnizca "
            f"`{dictionary.token_for(UniversalConcept.FOR)}` veya "
            f"`{dictionary.token_for(UniversalConcept.WHILE)}` dongusunun "
            "icinde kullanilabilir."
        )

    undefined = re.search(r"tan.msz isim: '([^']+)'", folded)
    if undefined:
        return (
            f"`{undefined.group(1)}` bu akista henuz tanimli degil. Once deger "
            "ata, import et veya temali kelime sozlugunu kontrol et."
        )

    if tags:
        themed = ", ".join(f"`{dictionary.token_for(c)}`" for c in tags)
        return f"{dictionary.theme} sozlugunde {themed} etrafinda hata: {message}"

    return f"{dictionary.theme} sozlugunde hata: {message}"


def _ascii_fold(value: str) -> str:
    table = str.maketrans(
        {
            "ç": "c",
            "ğ": "g",
            "ı": "i",
            "ö": "o",
            "ş": "s",
            "ü": "u",
            "Ç": "c",
            "Ğ": "g",
            "İ": "i",
            "Ö": "o",
            "Ş": "s",
            "Ü": "u",
        }
    )
    return value.translate(table)
