"""NL request → structured intent via Claude (B-1, D14/D50).

Uses ``client.messages.parse(output_format=...)`` so the SDK validates the model's JSON
against a Pydantic schema; anything malformed surfaces as a parse failure rather than an
executed order (B-1). The Anthropic client is injected so unit/integration tests mock the
LLM deterministically (D29); the semantic golden-set eval (H-3) uses the real model.

**Wire vs. domain.** The schema the model fills (``Wire*`` below) carries amount values as
*strings*, never numbers: Pydantic renders ``Decimal`` as a number|string union, which
would invite a float and reintroduce binary error (D45). We keep the wire value a string
and rebuild an exact ``Decimal`` when mapping to the domain contract in ``models``.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, ValidationError

from ..config import Settings
from .models import (
    ActionType,
    Amount,
    AmountBasis,
    Constraint,
    ConstraintKind,
    Intent,
    Operation,
    ParsedIntent,
    ParseResult,
    ParseStatus,
)

MAX_TOKENS = 2000

SYSTEM_PROMPT = """\
You convert a single free-form portfolio-rebalancing request into a structured intent.
You do NOT place trades, do math, or resolve category words to ticker symbols — you only
capture what the user means, exactly as stated.

Set `status`:
- "parsed" when you understand the request well enough to propose against it.
- "needs_clarification" when it is genuinely ambiguous or you are unsure — put a single
  concrete question in `clarification_question`.
- "unsupported" when it asks for something out of scope (anything other than trading
  US-listed equities/ETFs — e.g. crypto, options, forex) or is unsatisfiable as stated;
  put what could not be satisfied in `explanation`.

Always write `summary`: a one-sentence plain restatement of your understanding.
Give an honest `confidence` from 0 to 1.

When status is "parsed", fill `intent`:
- `operations`: each is an action ("buy" | "sell" | "set_allocation"), a `target` (the
  user's raw word: "bonds", "tech", "AAPL" — do NOT convert to symbols), and an optional
  `amount`.
- `amount.basis` is one of:
  - "target_weight"            e.g. "make it 60/40" → 60
  - "percent_portfolio"        e.g. "10% of my portfolio"
  - "percent_source_position"  e.g. "sell half my tech" → 50 (use this when a percentage
                               is vague about what it is a percentage of)
  - "absolute_cash"            e.g. "$5,000" → 5000
  - "shares"                   e.g. "10 shares"
- `amount.value` is a STRING number (e.g. "60", "5000", "0.5"); omit it only if there is
  truly no number. `amount.raw_phrase` is the original words.
- `constraints`: cash floors ("cash_floor"), exclusions ("exclude_asset", with the
  symbol/word in `target`), "only using new deposits" ("only_new_deposits"), else "other".
  `value` (a STRING number) and `raw_phrase` as applicable.

Never invent operations, amounts, or constraints the user did not express. If unsure
between readings, prefer "needs_clarification" over guessing.
"""


# --- wire schema the model fills (strings for amounts; see module docstring) -------------


class WireAmount(BaseModel):
    value: str | None = None
    basis: AmountBasis
    raw_phrase: str = ""


class WireOperation(BaseModel):
    action: ActionType
    target: str
    amount: WireAmount | None = None


class WireConstraint(BaseModel):
    kind: ConstraintKind
    target: str | None = None
    value: str | None = None
    raw_phrase: str = ""


class WireIntent(BaseModel):
    operations: list[WireOperation] = Field(default_factory=list)
    constraints: list[WireConstraint] = Field(default_factory=list)


class WireParsedIntent(BaseModel):
    status: ParseStatus
    confidence: float
    summary: str
    intent: WireIntent | None = None
    clarification_question: str | None = None
    explanation: str | None = None


# --- wire -> domain mapping (str -> exact Decimal, D45) ----------------------------------


def _dec(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(value)  # exact; raises InvalidOperation on garbage -> parse failure


def _to_amount(wire: WireAmount | None) -> Amount | None:
    if wire is None:
        return None
    return Amount(value=_dec(wire.value), basis=wire.basis, raw_phrase=wire.raw_phrase)


def _to_domain(wire: WireParsedIntent) -> ParsedIntent:
    intent: Intent | None = None
    if wire.intent is not None:
        intent = Intent(
            operations=[
                Operation(action=op.action, target=op.target, amount=_to_amount(op.amount))
                for op in wire.intent.operations
            ],
            constraints=[
                Constraint(
                    kind=c.kind, target=c.target, value=_dec(c.value), raw_phrase=c.raw_phrase
                )
                for c in wire.intent.constraints
            ],
        )
    return ParsedIntent(
        status=wire.status,
        confidence=wire.confidence,
        summary=wire.summary,
        intent=intent,
        clarification_question=wire.clarification_question,
        explanation=wire.explanation,
    )


def _extract_text(response: object) -> str | None:
    """Return the model's raw JSON text (for the audit trail, D21)."""
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    return None


class IntentParser:
    """Turns a request into a :class:`ParseResult`. LLM client is injected (D29)."""

    def __init__(self, client: object, *, model: str, max_tokens: int = MAX_TOKENS) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    @classmethod
    def from_settings(cls, settings: Settings, *, client: object | None = None) -> "IntentParser":
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return cls(client, model=settings.anthropic_model)

    def parse(self, request_text: str, *, context: str | None = None) -> ParseResult:
        user_message = _build_user_message(request_text, context)
        raw_prompt = f"{SYSTEM_PROMPT}\n\n--- request ---\n{user_message}"

        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                output_format=WireParsedIntent,
            )
        except Exception as exc:  # anthropic API/connection errors, SDK validation, etc.
            return self._failure(f"LLM call failed: {exc}", raw_prompt, None)

        raw_response = _extract_text(response)
        if getattr(response, "stop_reason", None) == "refusal":
            return self._failure("model declined the request", raw_prompt, raw_response)

        wire = getattr(response, "parsed_output", None)
        if wire is None:
            return self._failure("model returned no structured output", raw_prompt, raw_response)

        try:
            parsed = _to_domain(wire)
        except (ValidationError, InvalidOperation, ValueError) as exc:
            return self._failure(f"malformed intent: {exc}", raw_prompt, raw_response)

        return ParseResult(
            ok=True,
            parsed=parsed,
            error=None,
            raw_prompt=raw_prompt,
            raw_response=raw_response,
            model=self._model,
        )

    def _failure(self, error: str, raw_prompt: str, raw_response: str | None) -> ParseResult:
        return ParseResult(
            ok=False,
            parsed=None,
            error=error,
            raw_prompt=raw_prompt,
            raw_response=raw_response,
            model=self._model,
        )


def _build_user_message(request_text: str, context: str | None) -> str:
    """Assemble the user turn. ``context`` seeds conversational follow-ups (B-4)."""
    if context:
        return (
            "Prior context (most recent proposal in this conversation):\n"
            f"{context}\n\n"
            f"New request:\n{request_text}"
        )
    return request_text
