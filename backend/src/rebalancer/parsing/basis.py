"""Deterministic basis resolution (B-2, D2/D52).

A pure guardrail layer over the parsed intent — no LLM, no account state, no dollar math.
B-1's LLM already classifies each amount's basis; C-1 does the dollar/share arithmetic on
*live* state (D19). B-2 sits between them and makes the reading safe and explicit:

1. **Ambiguity default (D2).** A percentage whose basis the user did not state
   (``basis_explicit=False``) resolves to ``PERCENT_SOURCE_POSITION`` — the safe default —
   and is flagged (``basis_defaulted=True``) and noted, so the assumption is never silent.
2. **Coherence validation.** Percentages must be in (0, 100]; ``set_allocation`` target
   weights must not sum to more than 100%. An incoherent reading routes to clarify rather
   than executing (D2 — no silent guessing).
3. **Record for confirm (D4).** Human-readable ``notes`` describe every assumption applied.
"""

from __future__ import annotations

from decimal import Decimal

from .models import (
    Amount,
    AmountBasis,
    Intent,
    Operation,
    ResolutionResult,
)

_PERCENT_BASES = {
    AmountBasis.TARGET_WEIGHT,
    AmountBasis.PERCENT_PORTFOLIO,
    AmountBasis.PERCENT_SOURCE_POSITION,
}
# The two bases that are genuinely ambiguous when unstated (D2): a bare "10%"/"half".
_AMBIGUOUS_BASES = {AmountBasis.PERCENT_PORTFOLIO, AmountBasis.PERCENT_SOURCE_POSITION}
_HUNDRED = Decimal("100")


def resolve_basis(intent: Intent) -> ResolutionResult:
    """Normalize + validate an intent's amounts; see module docstring for the rules."""
    problems: list[str] = []
    notes: list[str] = []
    resolved_ops: list[Operation] = []

    for op in intent.operations:
        amount = op.amount
        if amount is None:
            resolved_ops.append(op)  # whole-position op ("sell everything") — nothing to resolve
            continue

        resolved_amount, op_notes, op_problems = _resolve_amount(op, amount)
        notes.extend(op_notes)
        problems.extend(op_problems)
        resolved_ops.append(op.model_copy(update={"amount": resolved_amount}))

    problems.extend(_check_weight_sum(resolved_ops))

    normalized = Intent(operations=resolved_ops, constraints=list(intent.constraints))
    if problems:
        return ResolutionResult(
            ok=False,
            intent=normalized,
            needs_clarification="; ".join(problems),
            notes=tuple(notes),
        )
    return ResolutionResult(ok=True, intent=normalized, needs_clarification=None, notes=tuple(notes))


def _resolve_amount(op: Operation, amount: Amount) -> tuple[Amount, list[str], list[str]]:
    notes: list[str] = []
    problems: list[str] = []

    basis = amount.basis
    defaulted = False
    if not amount.basis_explicit and basis in _AMBIGUOUS_BASES:
        if basis is not AmountBasis.PERCENT_SOURCE_POSITION:
            basis = AmountBasis.PERCENT_SOURCE_POSITION
            defaulted = True
        else:
            defaulted = True  # already source%, but the user didn't say so — record the assumption
        phrase = amount.raw_phrase or "the amount"
        notes.append(
            f"Interpreted {phrase!r} for {op.target!r} as a percentage of your current "
            f"{op.target} position (assumed — you didn't say what it was a percentage of)."
        )

    if basis in _PERCENT_BASES and amount.value is not None:
        if amount.value <= 0 or amount.value > _HUNDRED:
            problems.append(
                f"{amount.value}% for {op.target!r} is out of range (expected between 0 and 100)"
            )

    resolved = amount.model_copy(update={"basis": basis, "basis_defaulted": defaulted})
    return resolved, notes, problems


def _check_weight_sum(ops: list[Operation]) -> list[str]:
    """set_allocation target weights should not sum past 100% (D2 coherence)."""
    total = Decimal("0")
    for op in ops:
        if (
            op.action == "set_allocation"
            and op.amount is not None
            and op.amount.basis is AmountBasis.TARGET_WEIGHT
            and op.amount.value is not None
        ):
            total += op.amount.value
    if total > _HUNDRED:
        return [f"target weights sum to {total}%, which is over 100%"]
    return []
