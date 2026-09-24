"""Tool definitions the agent can call, and the code that runs them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .knowledge import EscalationHistory, OnCallSchedule, OwnershipCatalog

SUBMIT_TOOL = "submit_routing"

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_ownership",
        "description": (
            "Search the ownership catalog for product areas that match a query. Returns "
            "team ids, area names and which keywords matched. Use short queries with the "
            "product terms from the bug (e.g. 'refund stripe', 'salesforce duplicate')."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_team",
        "description": "Full description of one team: what it owns, its areas, services and Slack channel.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"team_id": {"type": "string"}},
            "required": ["team_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_past_escalations",
        "description": (
            "Search previously escalated bugs that look similar. Each result says which team "
            "fixed it, who resolved it and what the root cause was. Strong evidence for routing."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_oncall",
        "description": "Who is on call for a team right now.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"team_id": {"type": "string"}},
            "required": ["team_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": SUBMIT_TOOL,
        "description": (
            "Submit the final routing decision. Call exactly once, after investigating. "
            "confidence is 0-1: use below 0.5 when the report is too vague or fits several "
            "teams equally. On-call and the people responsible are added automatically."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "confidence": {"type": "number"},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "summary": {
                    "type": "string",
                    "description": "The bug rewritten for engineers: what happens, where, impact.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this team, citing the evidence found.",
                },
                "alternative_team_ids": {"type": "array", "items": {"type": "string"}},
                "clarifying_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Information support should collect, if anything important is missing.",
                },
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ids of past escalations or catalog areas that support the decision.",
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
        },
    },
]


class ToolError(Exception):
    """A tool failed in a way the model can recover from (e.g. unknown team id)."""


@dataclass
class Toolbox:
    catalog: OwnershipCatalog
    oncall: OnCallSchedule
    history: EscalationHistory

    def run(self, name: str, args: dict[str, Any]) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            raise ToolError(f"Unknown tool '{name}'")
        return json.dumps(handler(**args), ensure_ascii=False)

    def validate_team(self, team_id: str) -> None:
        if self.catalog.get(team_id) is None:
            known = ", ".join(self.catalog.teams)
            raise ToolError(f"Unknown team_id '{team_id}'. Known teams: {known}")

    def _tool_search_ownership(self, query: str) -> list[dict]:
        return self.catalog.search(query)

    def _tool_get_team(self, team_id: str) -> dict:
        self.validate_team(team_id)
        return self.catalog.get(team_id).model_dump()

    def _tool_search_past_escalations(self, query: str) -> list[dict]:
        return self.history.search(query)

    def _tool_get_oncall(self, team_id: str) -> dict:
        self.validate_team(team_id)
        return {"team_id": team_id, "on_call": self.oncall.current(team_id)}
