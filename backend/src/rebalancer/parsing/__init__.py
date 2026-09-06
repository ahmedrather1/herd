"""NL understanding (Epic B): free-form request → structured intent via Claude (B-1).

Public surface: the ``IntentParser`` and the domain contract (``ParseResult`` /
``ParsedIntent`` / ``Intent`` and friends). The ``Wire*`` schema the model fills is an
implementation detail of ``parser`` and is not re-exported here.
"""

from __future__ import annotations

from .mapping import SymbolResolver
from .models import (
    Amount,
    AmountBasis,
    Constraint,
    Intent,
    MappingResult,
    Operation,
    ParsedIntent,
    ParseResult,
    ParseStatus,
    SymbolMapping,
)
from .parser import IntentParser

__all__ = [
    "IntentParser",
    "SymbolResolver",
    "ParseResult",
    "ParsedIntent",
    "ParseStatus",
    "Intent",
    "Operation",
    "Amount",
    "AmountBasis",
    "Constraint",
    "MappingResult",
    "SymbolMapping",
]
