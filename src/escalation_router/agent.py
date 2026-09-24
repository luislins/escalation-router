"""The routing agent: a tool-use loop that ends when Claude calls submit_routing."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic
from pydantic import ValidationError

from .models import RoutingDecision
from .redaction import redact
from .tools import SUBMIT_TOOL, TOOL_DEFINITIONS, Toolbox, ToolError

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You route bug reports written by customer support agents to the engineering team that owns the problem.

Reports usually come from a Zendesk ticket or a Jira issue (title, fields, description, latest \
comments), sometimes followed by a Slack discussion about it. Support agents are not engineers: reports \
can be vague, mix symptoms with guesses, or be written in Portuguese, Spanish or English. Personal data \
has already been replaced by placeholders like [EMAIL].

How to work:
- Search the ownership catalog and past escalations before deciding. Past escalations fixed by a team \
are the strongest evidence you have.
- When the symptom and the probable cause point to different teams (a receipt email with a wrong \
amount could be Reporting or Payments), route by the most likely root cause and list the other team \
as an alternative.
- Fields such as Jira components or Zendesk tags are useful hints, but they are often set by \
support, so weigh them against the description.
- Look up who is on call for the team you choose.
- If key facts are missing (which page, which integration, error message, when it started), still \
make your best routing guess, lower the confidence, and list what support should ask the customer.
- Finish by calling submit_routing exactly once. Write summary, rationale and questions in the same \
language as the report.
"""

MAX_TURNS = 10


@dataclass
class RouterConfig:
    model: str = "claude-opus-5"
    effort: str = "medium"
    max_tokens: int = 16000
    confidence_threshold: float = 0.5
    # Server-side refusal fallback: if the model declines, the API retries on a fallback model.
    use_fallbacks: bool = True


@dataclass
class RoutingResult:
    decision: RoutingDecision
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class RoutingError(Exception):
    pass


class EscalationRouter:
    def __init__(self, toolbox: Toolbox, client: Any | None = None, config: RouterConfig | None = None):
        self.toolbox = toolbox
        self.client = client or anthropic.Anthropic()
        self.config = config or RouterConfig()

    def route(self, report: str) -> RoutingResult:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": f"<bug_report>\n{redact(report)}\n</bug_report>"}
        ]
        tool_calls: list[dict[str, Any]] = []

        for _ in range(MAX_TURNS):
            response = self._call_model(messages)
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                raise RoutingError("The model declined to route this report.")
            if response.stop_reason == "max_tokens":
                raise RoutingError("The model ran out of output tokens before finishing.")

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Please finish by calling {SUBMIT_TOOL} with your decision.",
                    }
                )
                continue

            results = []
            decision = None
            for block in tool_uses:
                tool_calls.append({"name": block.name, "input": block.input})
                try:
                    if block.name == SUBMIT_TOOL:
                        decision = self._finalize(block.input)
                        content = "Decision recorded."
                    else:
                        content = self.toolbox.run(block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
                except (ToolError, ValidationError, TypeError) as exc:
                    log.info("tool %s failed: %s", block.name, exc)
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {exc}",
                            "is_error": True,
                        }
                    )

            if decision is not None:
                return RoutingResult(decision=decision, tool_calls=tool_calls)
            messages.append({"role": "user", "content": results})

        raise RoutingError(f"No decision after {MAX_TURNS} turns.")

    def _call_model(self, messages: list[dict[str, Any]]) -> Any:
        params: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": SYSTEM_PROMPT,
            "tools": TOOL_DEFINITIONS,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.config.effort},
            "cache_control": {"type": "ephemeral"},
        }
        if self.config.use_fallbacks:
            return self.client.beta.messages.create(
                **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
            )
        return self.client.messages.create(**params)

    def _finalize(self, raw: dict[str, Any]) -> RoutingDecision:
        self.toolbox.validate_team(raw["team_id"])
        decision = RoutingDecision(**raw)
        decision.alternative_team_ids = [
            t for t in decision.alternative_team_ids if t != decision.team_id and self.toolbox.catalog.get(t)
        ]
        if decision.confidence < self.config.confidence_threshold:
            fallback = self.toolbox.catalog.fallback_team
            if decision.team_id != fallback:
                decision.alternative_team_ids.insert(0, decision.team_id)
            decision.team_id = fallback
            decision.assignee = self.toolbox.oncall.current(fallback)
            decision.fell_back = True
        return decision
