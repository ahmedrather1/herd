"""Constraint-solving (C-2, D8/D10).

Honors the constraints the parser captured on an intent, producing either a constrained
plan or a refusal (D10 — no partial orders on an unsatisfiable/unsupported constraint set).

Supported (D8), with the default readings recorded in D55 and flagged in QUESTIONS.md:

- **cash_floor** ("keep $5k in cash") → reduces the **investable** base to ``equity − floor``
  so a rebalance leaves exactly the floor in cash.
- **exclude_asset** ("don't sell AAPL") → the holding is **set aside**: never sold, and its
  value removed from the investable base so the rest rebalances around it. (Exclusion targets
  are treated as symbols; a category exclusion is not resolved to symbols in v1.)
- **only_new_deposits** → **unsupported in v1** (deposits aren't tracked) → refuse + explain.

Unsatisfiable numeric cases (floor ≥ equity, nothing left to invest) also refuse. The set of
constraints actually applied is returned for display at confirm (D8).

Alpaca-unavailable propagates (A-5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..alpaca.client import AlpacaClient
from ..parsing import Intent
from .models import Plan
from .planner import Planner


@dataclass(frozen=True)
class ConstraintSet:
    excluded: frozenset[str] = frozenset()
    cash_floor: Decimal | None = None
    only_new_deposits: bool = False


@dataclass(frozen=True)
class PlanResult:
    """Constrained-planning outcome. ``ok=False`` with ``refusal`` when unsatisfiable (D10)."""

    ok: bool
    plan: Plan | None = None
    refusal: str | None = None
    applied: tuple[str, ...] = field(default_factory=tuple)


def parse_constraints(intent: Intent) -> ConstraintSet:
    excluded: set[str] = set()
    cash_floor: Decimal | None = None
    only_new_deposits = False
    for c in intent.constraints:
        if c.kind == "exclude_asset" and c.target:
            excluded.add(c.target.strip().upper())
        elif c.kind == "cash_floor" and c.value is not None:
            cash_floor = c.value if cash_floor is None else max(cash_floor, c.value)
        elif c.kind == "only_new_deposits":
            only_new_deposits = True
    return ConstraintSet(frozenset(excluded), cash_floor, only_new_deposits)


class ConstraintSolver:
    """Applies an intent's constraints to produce a constrained plan or a refusal (C-2)."""

    def __init__(self, alpaca: AlpacaClient) -> None:
        self._alpaca = alpaca

    def solve(self, intent: Intent, mappings) -> PlanResult:
        constraints = parse_constraints(intent)

        if constraints.only_new_deposits:
            return PlanResult(
                ok=False,
                refusal=(
                    "This version can't restrict trading to only new deposits (it doesn't track "
                    "deposits). Try phrasing it as a dollar amount to invest instead."
                ),
            )

        account = self._alpaca.get_account()  # AlpacaUnavailable → propagates (A-5)
        positions = {p.symbol.upper(): p for p in self._alpaca.get_positions()}
        equity = account.equity

        excluded_value = sum(
            (positions[s].market_value for s in constraints.excluded if s in positions),
            Decimal("0"),
        )
        floor = constraints.cash_floor or Decimal("0")
        investable = equity - floor - excluded_value

        if floor > equity:
            return PlanResult(
                ok=False,
                refusal=f"Can't keep ${floor} in cash — the account is only worth ${equity}.",
            )
        if investable <= 0:
            return PlanResult(
                ok=False,
                refusal=(
                    "After keeping the requested cash aside and protecting excluded holdings, "
                    "there's nothing left to invest."
                ),
            )

        plan = Planner(self._alpaca).plan_from_state(
            intent,
            mappings,
            account=account,
            positions=positions,
            investable_equity=investable if (floor or excluded_value) else None,
            protected=constraints.excluded,
        )
        return PlanResult(ok=True, plan=plan, applied=_describe(constraints))


def _describe(constraints: ConstraintSet) -> tuple[str, ...]:
    applied = []
    if constraints.cash_floor is not None:
        applied.append(f"keep ${constraints.cash_floor} in cash")
    for sym in sorted(constraints.excluded):
        applied.append(f"don't sell {sym}")
    return tuple(applied)
