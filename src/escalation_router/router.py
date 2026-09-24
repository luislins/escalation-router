"""Routing a bug report to a team.

The default router makes a single model call: the code gathers everything the model needs
(ownership catalog, keyword matches, similar past escalations) and Claude only decides.
On-call and "who fixed similar bugs" are looked up by code afterwards.

The agent router (agent.py) lets Claude choose which lookups to make instead. It is kept for
when investigation gets open-ended (code owners, commits, error trackers) and for comparing
both approaches in the evals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import anthropic
from pydantic import ValidationError

from .models import RoutingDecision
from .redaction import redact
from .tools import Toolbox, ToolError

GUIDELINES = """\
Reports usually come from a Zendesk ticket or a Jira issue (title, fields, description, latest \
comments), sometimes followed by a Slack discussion about it. Support agents are not engineers: reports \
can be vague, mix symptoms with guesses, or be written in Portuguese, Spanish or English. Personal data \
has already been replaced by placeholders like [EMAIL].

- Past escalations fixed by a team are the strongest evidence you have.
- When the symptom and the probable cause point to different teams (a receipt email with a wrong \
amount could be Reporting or Payments), route by the most likely root cause and list the other team \
as an alternative.
- Fields such as Jira components or Zendesk tags are useful hints, but they are often set by \
support, so weigh them against the description.
- If key facts are missing (which page, which integration, error message, when it started), still \
make your best routing guess, lower the confidence (below 0.5 when several teams fit equally), and \
list what support should ask the customer.
- Write summary, rationale and questions in the same language as the report."""


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
    model_calls: int = 1


class RoutingError(Exception):
    pass


class EscalationRouter:
    """Shared plumbing: model calls and the deterministic post-processing of a decision."""

    def __init__(self, toolbox: Toolbox, client: Any | None = None, config: RouterConfig | None = None):
        self.toolbox = toolbox
        self.client = client or anthropic.Anthropic()
        self.config = config or RouterConfig()

    def route(self, report: str) -> RoutingResult:
        raise NotImplementedError

    def _call_model(self, **params: Any) -> Any:
        params = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "thinking": {"type": "adaptive"},
            "cache_control": {"type": "ephemeral"},
            **params,
        }
        params["output_config"] = {"effort": self.config.effort, **params.get("output_config", {})}
        if self.config.use_fallbacks:
            response = self.client.beta.messages.create(
                **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
            )
        else:
            response = self.client.messages.create(**params)
        if response.stop_reason == "refusal":
            raise RoutingError("The model declined to route this report.")
        if response.stop_reason == "max_tokens":
            raise RoutingError("The model ran out of output tokens before finishing.")
        return response

    def _finalize(self, raw: dict[str, Any], report: str) -> RoutingDecision:
        """Validate the model's answer, apply the confidence fallback, add the people responsible."""
        self.toolbox.validate_team(raw["team_id"])
        decision = RoutingDecision(**raw)
        catalog = self.toolbox.catalog
        decision.alternative_team_ids = [
            t
            for t in dict.fromkeys(decision.alternative_team_ids)
            if t != decision.team_id and catalog.get(t)
        ]
        if decision.confidence < self.config.confidence_threshold:
            if decision.team_id != catalog.fallback_team:
                decision.alternative_team_ids.insert(0, decision.team_id)
            decision.team_id = catalog.fallback_team
            decision.fell_back = True
        decision.assignee = self.toolbox.oncall.current(decision.team_id)
        decision.experts = self._experts(decision, report)
        return decision

    def _experts(self, decision: RoutingDecision, report: str, limit: int = 3) -> list[str]:
        """Who on the chosen team resolved the escalations cited as evidence, or similar ones."""
        if decision.fell_back:
            return []
        history = self.toolbox.history
        cited = [i for i in history.items if i.id in decision.evidence]
        similar = history.search(f"{decision.summary}\n{report}", limit=10)
        names = [i.resolved_by for i in cited if i.team == decision.team_id]
        names += [h["resolved_by"] for h in similar if h["team"] == decision.team_id]
        people = [n for n in dict.fromkeys(names) if n and n != decision.assignee]
        return people[:limit]


def decision_schema(team_ids: list[str]) -> dict:
    """JSON schema for the answer. Team ids are an enum, so the model cannot invent a team."""
    team = {"type": "string", "enum": team_ids}
    return {
        "type": "object",
        "properties": {
            "team_id": team,
            "confidence": {"type": "number", "description": "0 to 1"},
            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "summary": {
                "type": "string",
                "description": "The bug rewritten for engineers: what happens, where, impact.",
            },
            "rationale": {"type": "string", "description": "Why this team, citing the evidence."},
            "alternative_team_ids": {"type": "array", "items": team},
            "clarifying_questions": {"type": "array", "items": {"type": "string"}},
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ids of past escalations that support the decision.",
            },
        },
        "required": [
            "team_id",
            "confidence",
            "severity",
            "summary",
            "rationale",
            "alternative_team_ids",
            "clarifying_questions",
            "evidence",
        ],
        "additionalProperties": False,
    }


class SingleCallRouter(EscalationRouter):
    """One request: retrieval is done in code, the model only classifies."""

    SIMILAR_ESCALATIONS = 5

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        catalog = self.toolbox.catalog
        teams = [t.model_dump(exclude={"slack_channel", "jira_component"}) for t in catalog.teams.values()]
        # The catalog lives in the system prompt: it is identical across requests, so it gets cached.
        self.system = (
            "You route bug reports written by customer support agents to the engineering team that "
            "owns the problem.\n\n"
            f"{GUIDELINES}\n\n"
            f"If nothing fits, use the triage team '{catalog.fallback_team}' with low confidence.\n\n"
            f"<ownership_catalog>\n{json.dumps(teams, ensure_ascii=False)}\n</ownership_catalog>"
        )
        self.schema = decision_schema(list(catalog.teams))

    def build_prompt(self, report: str) -> str:
        keyword_hits = self.toolbox.catalog.search(report)
        similar = self.toolbox.history.search(report, limit=self.SIMILAR_ESCALATIONS)
        return (
            f"<bug_report>\n{report}\n</bug_report>\n\n"
            f"<catalog_keyword_matches>\n{json.dumps(keyword_hits, ensure_ascii=False)}\n"
            "</catalog_keyword_matches>\n\n"
            f"<similar_past_escalations>\n{json.dumps(similar, ensure_ascii=False)}\n"
            "</similar_past_escalations>\n\n"
            "Keyword matches are naive and miss other languages; use them as hints only."
        )

    def route(self, report: str) -> RoutingResult:
        report = redact(report)
        response = self._call_model(
            system=self.system,
            messages=[{"role": "user", "content": self.build_prompt(report)}],
            output_config={"format": {"type": "json_schema", "schema": self.schema}},
        )
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise RoutingError("The model returned no answer.")
        try:
            decision = self._finalize(json.loads(text), report)
        except (json.JSONDecodeError, KeyError, ToolError, ValidationError) as exc:
            raise RoutingError(f"Invalid answer from the model: {exc}") from exc
        return RoutingResult(decision=decision)
