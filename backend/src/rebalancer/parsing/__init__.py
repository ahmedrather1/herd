"""NL understanding (Epic B): free-form request → structured intent via Claude (B-1).

Public surface: the ``IntentParser`` and the domain contract (``ParseResult`` /
``ParsedIntent`` / ``Intent`` and friends). The ``Wire*`` schema the model fills is an
implementation detail of ``parser`` and is not re-exported here.
"""

from __future__ import annotations

from .models import (
    Amount,
    AmountBasis,
    Constraint,
    Intent,
    Operation,
    ParsedIntent,
    ParseResult,
    ParseStatus,
)
from .parser import IntentParser

__all__ = [
    "IntentParser",
    "ParseResult",
    "ParsedIntent",
    "ParseStatus",
    "Intent",
    "Operation",
    "Amount",
    "AmountBasis",
    "Constraint",
]
