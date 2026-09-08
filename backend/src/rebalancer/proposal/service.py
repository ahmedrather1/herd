"""Proposal assembly (D-1, D4/D2/D5/D20).

Orchestrates the whole read-side pipeline into a single proposal:

    parse (B-1) → resolve basis (B-2) → map symbols (B-3) → plan under constraints (C-1/C-2)
    → validate (D-2) → current-vs-target (C-3) → market clock (D-3) → restatement

Any step that can't proceed short-circuits to a non-proposal outcome (clarify / refuse /
unavailable / error) so nothing ambiguous or invalid reaches confirm (D4/D10/D18). A closed
market is still a proposal, carrying a warning (D17/D-3). Alpaca-unreachable becomes the A-5
"try again" outcome. When an ``AuditStore`` is supplied the request, LLM calls, and proposal
are persisted (D20); F-1 completes the full end-to-end record.

Confirm-time re-validation (D-4) and execution (Epic E) consume this proposal separately.
"""

from __future__ import annotations

from ..alpaca import AlpacaUnavailableError
from ..alpaca.client import AlpacaClient
from ..parsing import IntentParser, ParseStatus, SymbolResolver, resolve_basis
from ..planning import (
    ConstraintSolver,
    OrderValidator,
    compute_allocation,
)
from ..store import AuditStore, ProposedLeg, RequestStatus
from .models import Proposal, ProposalOutcome, ProposalStatus

_MARKET_CLOSED_WARNING = (
    "The market is closed — nothing is submitted now; confirm and it will be placed when the "
    "market is open."
)


class ProposalService:
    """Builds a :class:`ProposalOutcome` from a free-form request (D-1)."""

    def __init__(
        self,
        parser: IntentParser,
        resolver: SymbolResolver,
        alpaca: AlpacaClient,
        store: AuditStore | None = None,
    ) -> None:
        self._parser = parser
        self._resolver = resolver
        self._alpaca = alpaca
        self._store = store

    @classmethod
    def from_settings(cls, settings, alpaca, *, store=None, client=None):
        parser = IntentParser.from_settings(settings, client=client)
        resolver = SymbolResolver.from_settings(settings, alpaca, client=client)
        return cls(parser, resolver, alpaca, store)

    def propose(self, request_text, *, conversation_id=None, context=None) -> ProposalOutcome:
        request_id = self._begin(request_text, conversation_id)
        try:
            return self._propose(request_text, request_id, context)
        except AlpacaUnavailableError:
            return self._finish(
                request_id,
                ProposalStatus.UNAVAILABLE,
                RequestStatus.FAILED,
                message="Can't reach Alpaca right now — please try again in a moment.",
            )

    # --- pipeline ------------------------------------------------------------

    def _propose(self, request_text, request_id, context) -> ProposalOutcome:
        parse = self._parser.parse(request_text, context=context)
        self._persist_llm(request_id, "parse", parse)
        if not parse.ok:
            return self._finish(request_id, ProposalStatus.ERROR, RequestStatus.FAILED, message=parse.error)

        parsed = parse.parsed
        if parsed.status is ParseStatus.NEEDS_CLARIFICATION:
            return self._finish(
                request_id, ProposalStatus.CLARIFY, RequestStatus.RECEIVED,
                message=parsed.clarification_question or parsed.summary,
            )
        if parsed.status is ParseStatus.UNSUPPORTED:
            return self._finish(
                request_id, ProposalStatus.REFUSE, RequestStatus.REFUSED,
                message=parsed.explanation or parsed.summary,
            )

        intent = parsed.intent
        if intent is None or not intent.operations:
            return self._finish(
                request_id, ProposalStatus.CLARIFY, RequestStatus.RECEIVED,
                message="I couldn't identify a concrete action to take. Could you rephrase?",
            )

        resolution = resolve_basis(intent)
        if not resolution.ok:
            return self._finish(
                request_id, ProposalStatus.CLARIFY, RequestStatus.RECEIVED,
                message=resolution.needs_clarification,
            )
        intent = resolution.intent

        mapping = self._resolver.resolve(intent)
        self._persist_llm(request_id, "category_map", mapping)
        if not mapping.ok:
            if mapping.error is not None:
                return self._finish(request_id, ProposalStatus.ERROR, RequestStatus.FAILED, message=mapping.error)
            return self._finish(request_id, ProposalStatus.REFUSE, RequestStatus.REFUSED, message=mapping.refusal)

        plan_result = ConstraintSolver(self._alpaca).solve(intent, mapping.mappings)
        if not plan_result.ok:
            return self._finish(request_id, ProposalStatus.REFUSE, RequestStatus.REFUSED, message=plan_result.refusal)
        plan = plan_result.plan

        validation = OrderValidator(self._alpaca).validate(plan)
        if not validation.ok:
            return self._finish(
                request_id, ProposalStatus.REFUSE, RequestStatus.REFUSED,
                message="The proposed orders aren't valid as-is — adjust the request:",
                problems=tuple(p.reason for p in validation.problems),
            )

        allocation = compute_allocation(plan, self._alpaca)
        clock = self._alpaca.get_clock()
        proposal = Proposal(
            restatement=_restate(parsed.summary, resolution.notes, mapping.mappings, plan_result.applied),
            basis_notes=resolution.notes,
            mappings=mapping.mappings,
            orders=plan.orders,
            allocation=allocation,
            applied_constraints=plan_result.applied,
            market_open=clock.is_open,
            market_warning=None if clock.is_open else _MARKET_CLOSED_WARNING,
        )
        self._persist_proposal(request_id, proposal)
        return self._finish(request_id, ProposalStatus.PROPOSAL, RequestStatus.PROPOSED, proposal=proposal)

    # --- persistence (D20) ---------------------------------------------------

    def _begin(self, request_text, conversation_id) -> str | None:
        if self._store is None:
            return None
        if conversation_id is None:
            conversation_id = self._store.start_conversation(self._store.create_session())
        return self._store.record_request(conversation_id, request_text)

    def _persist_llm(self, request_id, purpose, result) -> None:
        if self._store is None or request_id is None:
            return
        raw_prompt = getattr(result, "raw_prompt", None)
        if not raw_prompt:
            return
        self._store.record_llm_call(
            request_id, purpose=purpose, model=result.model,
            prompt=raw_prompt, response=getattr(result, "raw_response", None) or "",
        )

    def _persist_proposal(self, request_id, proposal: Proposal) -> None:
        if self._store is None or request_id is None:
            return
        legs = [
            ProposedLeg(
                symbol=o.symbol, side=o.side.value, sequence_index=i, qty=o.qty, notional=o.notional
            )
            for i, o in enumerate(proposal.orders)
        ]
        self._store.record_proposal(request_id, summary=proposal.restatement, legs=legs)

    def _finish(self, request_id, status, request_status, *, proposal=None, message=None, problems=()):
        if self._store is not None and request_id is not None:
            self._store.set_request_status(request_id, request_status)
        return ProposalOutcome(
            status=status, proposal=proposal, message=message, problems=tuple(problems), request_id=request_id
        )


def _restate(summary, notes, mappings, applied) -> str:
    """Plain-English restatement surfacing the basis (D2) and mapping (D5)."""
    lines = [summary]
    lines.extend(notes)
    if mappings:
        mapped = "; ".join(f"{m.target} → {', '.join(m.symbols)}" for m in mappings)
        lines.append(f"Symbols: {mapped}")
    if applied:
        lines.append("Constraints: " + "; ".join(applied))
    return "\n".join(lines)
