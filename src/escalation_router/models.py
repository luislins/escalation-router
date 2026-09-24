"""Data models shared by the catalog, the agent and the Slack layer."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

# YAML turns `401` or `500` into ints; keywords are always matched as text.
Keyword = Annotated[str, BeforeValidator(str)]


class Area(BaseModel):
    name: str
    keywords: list[Keyword] = Field(default_factory=list)
    services: list[Keyword] = Field(default_factory=list)


class Team(BaseModel):
    id: str
    name: str
    slack_channel: str
    description: str = ""
    areas: list[Area] = Field(default_factory=list)


class PastEscalation(BaseModel):
    id: str
    summary: str
    team: str
    resolved_by: str | None = None
    resolution: str | None = None


Severity = Literal["low", "medium", "high", "critical"]


class RoutingDecision(BaseModel):
    """What the agent hands back after investigating a bug report."""

    team_id: str
    assignee: str | None = None
    confidence: float = Field(ge=0, le=1)
    severity: Severity
    summary: str
    rationale: str
    alternative_team_ids: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    fell_back: bool = False
