from __future__ import annotations

from enum import Enum


class ConceptSupport(Enum):
    FULL = "full"
    #: supported through a documented workaround (e.g. SQL classes are
    #: composite types + standalone functions)
    EMULATED = "emulated"
    UNSUPPORTED = "unsupported"
