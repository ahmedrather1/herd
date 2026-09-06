"""Fake Anthropic client for parser tests (D29 — mock the LLM, deterministically).

Mocks at the SDK boundary the parser actually calls: ``client.messages.parse(...)``. A
test queues the responses (or exceptions) the fake should return in order, and can inspect
``client.messages.calls`` to assert what was sent (model, system, output_format, message).

``make_response`` wraps a ``WireParsedIntent`` (the schema the model fills) in an object
shaped like the SDK's ``ParsedMessage``: ``.parsed_output``, ``.stop_reason``, ``.content``
(a list with one text block carrying the raw JSON).
"""

from __future__ import annotations

from types import SimpleNamespace

from rebalancer.parsing.parser import WireParsedIntent


def make_response(wire: WireParsedIntent | None, *, stop_reason: str = "end_turn") -> object:
    text = wire.model_dump_json() if wire is not None else "{}"
    block = SimpleNamespace(type="text", text=text, parsed_output=wire)
    return SimpleNamespace(
        parsed_output=wire, stop_reason=stop_reason, content=[block], model="fake-model"
    )


class _FakeMessages:
    def __init__(self, responses: tuple[object, ...]) -> None:
        self._queue = list(responses)
        self.calls: list[dict] = []

    def parse(self, **kwargs) -> object:
        self.calls.append(kwargs)
        if not self._queue:
            raise AssertionError("FakeAnthropic.messages.parse called more times than queued")
        result = self._queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeAnthropic:
    """Drop-in for ``anthropic.Anthropic`` exposing only ``.messages.parse``."""

    def __init__(self, *responses: object) -> None:
        self.messages = _FakeMessages(responses)
