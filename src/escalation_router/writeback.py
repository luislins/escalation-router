"""Write a confirmed routing decision back to the Jira issue as a comment.

Only called after a person confirms the answer, never straight from the agent. The comment
names the team and the people responsible without @mentioning anyone, so nobody is notified
besides the issue's usual watchers. Changing fields (component, label) is opt-in, since it can
trigger Jira automations and notifications.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from .models import Team
from .sources import JiraSource

LABEL = "escalation-router"


@dataclass
class Routing:
    team: Team
    assignee: str | None
    confirmed_by: str
    experts: list[str] = field(default_factory=list)
    confidence: float | None = None
    rationale: str | None = None
    suggested_team: Team | None = None  # set when a person picked a different team


def jira_comment(r: Routing) -> str:
    """Jira wiki markup."""
    lines = [
        f"*Team:* {r.team.name}",
        f"*On call:* {r.assignee or 'see team rotation'}",
    ]
    if r.experts:
        lines.append(f"*Fixed similar bugs:* {', '.join(r.experts)}")
    if r.suggested_team and r.suggested_team.id != r.team.id:
        lines += ["", f"_Set by {r.confirmed_by}. Escalation Router had suggested {r.suggested_team.name}._"]
    else:
        if r.rationale:
            lines += ["", f"_Why:_ {r.rationale}"]
        confidence = f" (confidence {r.confidence:.0%})" if r.confidence is not None else ""
        lines += ["", f"_Suggested by Escalation Router{confidence}, confirmed by {r.confirmed_by}._"]
    return "\n".join(lines)


@dataclass
class JiraWriteback:
    jira: JiraSource
    update_fields: bool = False

    @classmethod
    def from_env(cls) -> JiraWriteback | None:
        jira = JiraSource.from_env()
        if jira is None:
            return None
        return cls(jira, update_fields=os.environ.get("JIRA_UPDATE_FIELDS", "false").lower() == "true")

    def apply(self, key: str, routing: Routing) -> list[str]:
        """Returns problems instead of raising, so a failed field update does not hide the comment."""
        errors = []
        try:
            self.jira.add_comment(key, jira_comment(routing))
        except httpx.HTTPError as exc:
            errors.append(f"Could not comment on {key}: {_describe(exc)}")

        if self.update_fields:
            update: dict = {"labels": [{"add": LABEL}]}
            if routing.team.jira_component:
                update["components"] = [{"set": [{"name": routing.team.jira_component}]}]
            try:
                self.jira.update_issue(key, update)
            except httpx.HTTPError as exc:
                errors.append(f"Could not update fields on {key}: {_describe(exc)}")
        return errors


def _describe(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} {exc.response.text[:300]}"
    return str(exc)
