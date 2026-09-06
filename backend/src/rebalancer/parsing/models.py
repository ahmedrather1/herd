"""Domain contract for the parser (B-1, D6/D50).

These are the app's own types — the structured meaning of a free-form request, before any
resolution of category words to symbols (B-3) or of the %-basis math (B-2). Everything
downstream (Epic C planner, Epic D proposal) consumes this contract, and the persistence
``Intent`` table (D49) expands to match it.

Money/quantities are ``Decimal`` (D45). The parser's *outcome* is a discriminated result
so that low-confidence and unsupported requests route to clarify/refuse rather than silent
action (D4/D10) — never an "execute anyway" path.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ParseStatus(str, Enum):
    """How the model understood the request (the outcome discriminator)."""

    PARSED = "parsed"  # understood confidently → propose (still confirm-gated, D4)
    NEEDS_CLARIFICATION = "needs_clarification"  # ambiguous / low confidence (D4)
    UNSUPPORTED = "unsupported"  # out of scope / unsatisfiable as stated (D10)


class AmountBasis(str, Enum):
    """What a number means (D2). Resolution to concrete shares/dollars happens in B-2/C."""

    TARGET_WEIGHT = "target_weight"  # "60/40" → 60% target weight
    PERCENT_PORTFOLIO = "percent_portfolio"  # "10% of my portfolio"
    PERCENT_SOURCE_POSITION = "percent_source_position"  # "half my tech" (default if vague)
    ABSOLUTE_CASH = "absolute_cash"  # "$5,000"
    SHARES = "shares"  # "10 shares"


ActionType = Literal["buy", "sell", "set_allocation"]
ConstraintKind = Literal["cash_floor", "exclude_asset", "only_new_deposits", "other"]


class Amount(BaseModel):
    """A quantity plus what it is measured against (D2)."""

    model_config = ConfigDict(frozen=True)

    value: Decimal | None = None
    basis: AmountBasis
    raw_phrase: str = ""  # the original words ("half", "10%", "$5k") — for confirm/audit


class Operation(BaseModel):
    """A single thing the user wants done to a target (raw term; unresolved until B-3)."""

    model_config = ConfigDict(frozen=True)

    action: ActionType
    target: str  # "bonds", "AAPL", "my tech" — a category word or symbol, not yet mapped
    amount: Amount | None = None


class Constraint(BaseModel):
    """A restriction the plan must respect (D8)."""

    model_config = ConfigDict(frozen=True)

    kind: ConstraintKind
    target: str | None = None  # e.g. "AAPL" for an exclusion
    value: Decimal | None = None  # e.g. cash-floor dollars
    raw_phrase: str = ""


class Intent(BaseModel):
    """The structured meaning of a request: what to do (operations) under what limits."""

    model_config = ConfigDict(frozen=True)

    operations: list[Operation] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)


class ParsedIntent(BaseModel):
    """The model's understanding: a status plus (when parsed) the structured intent."""

    model_config = ConfigDict(frozen=True)

    status: ParseStatus
    confidence: float  # 0..1, the model's own confidence
    summary: str  # plain-language restatement shown at confirm (D4)
    intent: Intent | None = None  # present when status == PARSED
    clarification_question: str | None = None  # when NEEDS_CLARIFICATION
    explanation: str | None = None  # when UNSUPPORTED — what couldn't be satisfied (D10)


@dataclass(frozen=True)
class ParseResult:
    """What the parser returns to callers.

    ``ok`` is False when the LLM call failed, refused, or produced output we could not
    validate — a *parse failure* that must route to clarify/retry, never execute (B-1/D4).
    ``raw_prompt`` / ``raw_response`` are always captured for the audit trail (D21).
    """

    ok: bool
    parsed: ParsedIntent | None
    error: str | None
    raw_prompt: str
    raw_response: str | None
    model: str


@dataclass(frozen=True)
class SymbolMapping:
    """One resolved operation target → concrete tradable symbols (B-3, D5).

    ``source`` records how it was resolved: ``literal`` (the target already was a ticker),
    ``holdings`` (a sell/reduce category resolved to the user's matching positions), or
    ``proposed`` (a buy/allocation category the model mapped to representative symbols).
    """

    target: str
    action: str
    symbols: tuple[str, ...]
    source: str  # "literal" | "holdings" | "proposed"
    note: str = ""


@dataclass(frozen=True)
class MappingResult:
    """Outcome of resolving every category term in an intent (B-3).

    ``ok`` is False in two distinct ways: ``refusal`` is set when a term is unmappable or
    untradable (D10 — refuse the whole request, never map partially); ``error`` is set when
    the LLM call itself failed. Alpaca-unavailable is not represented here — it propagates
    as ``AlpacaUnavailableError`` for the caller's A-5 handling.
    """

    ok: bool
    mappings: tuple[SymbolMapping, ...]
    refusal: str | None
    error: str | None
    raw_prompt: str | None
    raw_response: str | None
    model: str
