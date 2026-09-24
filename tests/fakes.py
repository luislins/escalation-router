"""A scripted stand-in for the Anthropic client, so tests never hit the API."""

from __future__ import annotations

from itertools import count
from types import SimpleNamespace

_ids = count(1)


def tool_use(name: str, **inputs):
    return SimpleNamespace(type="tool_use", id=f"toolu_{next(_ids)}", name=name, input=inputs)


def text(value: str):
    return SimpleNamespace(type="text", text=value)


def response(*blocks, stop_reason: str | None = None):
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        # Snapshot the message list: the router keeps appending to the same list.
        self.requests.append({**params, "messages": list(params["messages"])})
        return self._responses.pop(0)
