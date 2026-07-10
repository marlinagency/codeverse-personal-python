from __future__ import annotations

import pytest

from codeverse_core.concepts import UniversalConcept
from codeverse_core.theme_mapping.dictionary import ThemeDictionary


@pytest.fixture
def space_dictionary() -> ThemeDictionary:
    """A hand-written 'black holes in space' theme used across tests."""
    return ThemeDictionary(
        theme="uzayda karadelikleri seven biri",
        mappings={
            UniversalConcept.FUNCTION_DEF: "singularity",
            UniversalConcept.RETURN: "emit",
            UniversalConcept.IF: "event_horizon",
            UniversalConcept.ELIF: "or_horizon",
            UniversalConcept.ELSE: "vacuum",
            UniversalConcept.FOR: "orbit",
            UniversalConcept.IN: "around",
            UniversalConcept.WHILE: "spin_while",
            UniversalConcept.BREAK: "escape",
            UniversalConcept.CONTINUE: "slingshot",
            UniversalConcept.CLASS_DEF: "constellation",
            UniversalConcept.IMPORT: "beam",
            UniversalConcept.TRY: "probe",
            UniversalConcept.EXCEPT: "hawking_catch",
            UniversalConcept.FINALLY: "collapse",
            UniversalConcept.AND: "gravity_and",
            UniversalConcept.OR: "photon_or",
            UniversalConcept.NOT: "antimatter",
            UniversalConcept.TRUE: "lightspeed",
            UniversalConcept.FALSE: "darkness",
            UniversalConcept.NONE: "void",
            UniversalConcept.PRINT: "radiate",
            UniversalConcept.RANGE: "lightyears",
            UniversalConcept.LEN: "mass",
            UniversalConcept.LIST_APPEND: "accrete",
            UniversalConcept.LIST_REMOVE: "eject",
            UniversalConcept.CONTAINS: "captures",
            UniversalConcept.DICT_GET: "observe",
            UniversalConcept.DICT_SET: "chart",
            UniversalConcept.DICT_KEYS: "coordinates",
            UniversalConcept.DICT_VALUES: "readings",
            UniversalConcept.DICT_DELETE: "evaporate",
        },
    )
