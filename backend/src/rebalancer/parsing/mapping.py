"""Category word → concrete tradable symbol resolution (B-3, D5/D51).

Turns an ``Intent``'s raw operation targets ("tech", "bonds", "AAPL") into validated
Alpaca-tradable symbols. Rules (D51):

- A target that is already a tradable ticker maps to itself (``source="literal"``).
- A **sell/reduce** category is holdings-aware: resolved only to the user's current
  positions that fit the category (``source="holdings"``) — you can only sell what you
  hold; nothing held → the request is refused.
- A **buy/allocation** category is mapped by the LLM to a representative US-listed symbol,
  leaning to a single liquid ETF (``source="proposed"``).
- Every proposed symbol is validated tradable via the A-4 ``get_asset``. Any unmappable or
  untradable term refuses the whole request with an explanation (D10 — no partial mapping).

Alpaca being unreachable propagates as ``AlpacaUnavailableError`` (A-5), not a refusal.
The Anthropic client is injected so tests mock the LLM (D29); the Alpaca client is the A-4
boundary (the H-2 fake in tests). Raw prompt/response are captured for confirm/audit (D21).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ..alpaca import AlpacaRequestError
from ..alpaca.client import AlpacaClient
from ..config import Settings
from .models import Intent, MappingResult, SymbolMapping

MAX_TOKENS = 1500

# A target worth checking as a literal ticker: 1–5 letters (optionally with a dot class,
# e.g. BRK.B). Phrases like "my tech" never match, so they skip the get_asset probe.
_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")

SYSTEM_PROMPT = """\
You map category words in a portfolio request to concrete, currently tradable US-listed
symbols (equities or ETFs only — never crypto, options, forex, or non-US listings).

You are given a list of targets, each with an action ("buy", "sell", or "set_allocation"),
and the user's current holdings (ticker symbols).

For each target:
- If the action is "sell": choose ONLY from the user's current holdings — the symbols that
  belong to the category. If none of the holdings fit, return an empty list for that target.
- If the action is "buy" or "set_allocation": propose a representative symbol, strongly
  preferring a SINGLE liquid, well-known US-listed ETF for the category (e.g. broad tech →
  one tech-sector ETF, bonds → one aggregate-bond ETF). Only return multiple/individual
  names if the user clearly named specific companies.

For a broad theme prefer the category's well-known ETF, not a same-named stock — e.g. "gold"
→ a gold ETF like GLD or IAU, NOT the ticker GOLD (which is a mining company).

Return concrete ticker symbols only (uppercase). Do not invent tickers. If you cannot map a
target to a real tradable US symbol, return an empty list for it. Add a short `note`
explaining each mapping (shown to the user at confirmation).
"""


class WireMappedTarget(BaseModel):
    target: str
    symbols: list[str] = Field(default_factory=list)
    note: str = ""


class WireMapping(BaseModel):
    mappings: list[WireMappedTarget] = Field(default_factory=list)


def _looks_like_symbol(token: str) -> bool:
    return bool(_SYMBOL_RE.match(token))


_CASH_WORDS = {"cash", "money", "cash reserve", "cash reserves", "cash position", "usd", "dollars"}


def _is_cash(target: str) -> bool:
    """A "cash" bucket is literal uninvested cash, never a security (even though CASH is a
    real ticker). It is reserved, not bought."""
    return target.strip().lower() in _CASH_WORDS


class SymbolResolver:
    """Resolves an intent's category targets to tradable symbols (B-3)."""

    def __init__(
        self, client: object, alpaca: AlpacaClient, *, model: str, max_tokens: int = MAX_TOKENS
    ) -> None:
        self._client = client
        self._alpaca = alpaca
        self._model = model
        self._max_tokens = max_tokens

    @classmethod
    def from_settings(
        cls, settings: Settings, alpaca: AlpacaClient, *, client: object | None = None
    ) -> "SymbolResolver":
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return cls(client, alpaca, model=settings.anthropic_model)

    def resolve(self, intent: Intent) -> MappingResult:
        held = {p.symbol.upper() for p in self._alpaca.get_positions()}  # AlpacaUnavailable → propagates

        resolved: list[SymbolMapping] = []
        unmappable: list[str] = []
        category_targets: list[tuple[str, str]] = []  # (target, action)

        for op in intent.operations:
            target = op.target.strip()
            if _is_cash(target):  # "cash" is the residual, not a security to buy
                resolved.append(SymbolMapping(target, op.action, (), "cash", "left uninvested as cash"))
                continue
            ticker = target.upper()
            if _looks_like_symbol(ticker):
                asset = self._get_asset(ticker)
                if asset is not None:
                    if asset.tradable:
                        resolved.append(
                            SymbolMapping(target, op.action, (ticker,), "literal")
                        )
                    else:
                        unmappable.append(f"{target!r} is not tradable")
                    continue
            category_targets.append((target, op.action))

        raw_prompt = raw_response = None
        if category_targets:
            outcome = self._map_categories(category_targets, sorted(held))
            if outcome.error is not None:
                return outcome.as_error_result(self._model)  # LLM call failed → error result
            raw_prompt, raw_response = outcome.raw_prompt, outcome.raw_response
            by_target = {m.target.lower(): m for m in outcome.wire.mappings}

            for target, action in category_targets:
                proposed = [s.strip().upper() for s in _lookup(by_target, target)]
                note = _lookup_note(by_target, target)
                if action == "sell":
                    valid = [s for s in proposed if s in held and self._tradable(s)]
                    source = "holdings"
                    if not valid:
                        unmappable.append(f"you don't hold anything matching {target!r}")
                        continue
                else:
                    valid = [s for s in proposed if self._tradable(s)]
                    source = "proposed"
                    if not valid:
                        unmappable.append(f"couldn't map {target!r} to a tradable symbol")
                        continue
                resolved.append(
                    SymbolMapping(target, action, tuple(dict.fromkeys(valid)), source, note)
                )

        if unmappable:  # D10: refuse the whole request, never map partially
            return MappingResult(
                ok=False,
                mappings=(),
                refusal="Couldn't resolve: " + "; ".join(unmappable),
                error=None,
                raw_prompt=raw_prompt,
                raw_response=raw_response,
                model=self._model,
            )
        return MappingResult(
            ok=True,
            mappings=tuple(resolved),
            refusal=None,
            error=None,
            raw_prompt=raw_prompt,
            raw_response=raw_response,
            model=self._model,
        )

    # --- helpers -------------------------------------------------------------

    def _get_asset(self, symbol: str):
        try:
            return self._alpaca.get_asset(symbol)
        except AlpacaRequestError:
            return None  # unknown to Alpaca → treat as a category word

    def _tradable(self, symbol: str) -> bool:
        asset = self._get_asset(symbol)
        return asset is not None and asset.tradable

    def _map_categories(self, targets: list[tuple[str, str]], held: list[str]) -> "_MapOutcome":
        lines = "\n".join(f"- target: {t!r}, action: {a}" for t, a in targets)
        user_message = (
            f"Targets to map:\n{lines}\n\n"
            f"Current holdings: {', '.join(held) if held else '(none)'}"
        )
        raw_prompt = f"{SYSTEM_PROMPT}\n\n--- request ---\n{user_message}"
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                output_format=WireMapping,
            )
        except Exception as exc:  # noqa: BLE001 - any SDK/API/validation error → error result
            return _MapOutcome(
                wire=WireMapping(),
                error=f"symbol-mapping LLM call failed: {exc}",
                raw_prompt=raw_prompt,
                raw_response=None,
            )
        raw_response = _extract_text(response)
        if getattr(response, "stop_reason", None) == "refusal":
            return _MapOutcome(WireMapping(), "model declined to map symbols", raw_prompt, raw_response)
        wire = getattr(response, "parsed_output", None)
        if wire is None:
            return _MapOutcome(WireMapping(), "model returned no mapping", raw_prompt, raw_response)
        return _MapOutcome(wire, None, raw_prompt, raw_response)


class _MapOutcome:
    def __init__(self, wire: WireMapping, error: str | None, raw_prompt: str, raw_response: str | None):
        self.wire = wire
        self.error = error
        self.raw_prompt = raw_prompt
        self.raw_response = raw_response

    def as_error_result(self, model: str) -> MappingResult:
        return MappingResult(
            ok=False, mappings=(), refusal=None, error=self.error,
            raw_prompt=self.raw_prompt, raw_response=self.raw_response, model=model,
        )


def _lookup(by_target: dict, target: str) -> list[str]:
    entry = by_target.get(target.lower())
    return list(entry.symbols) if entry is not None else []


def _lookup_note(by_target: dict, target: str) -> str:
    entry = by_target.get(target.lower())
    return entry.note if entry is not None else ""


def _extract_text(response: object) -> str | None:
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    return None
