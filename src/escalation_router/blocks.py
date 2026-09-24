"""Slack Block Kit layouts. Pure functions so they are easy to test.

Names are plain text on purpose: the bot tells support who is responsible,
it does not @mention or notify anyone.
"""

from __future__ import annotations

import json
from typing import Any

from .knowledge import OwnershipCatalog
from .models import RoutingDecision


def responsibles_text(assignee: str | None, experts: list[str]) -> list[str]:
    lines = [f"*On call:* {assignee or 'unknown'}"]
    if experts:
        lines.append(f"*Fixed similar bugs:* {', '.join(experts)}")
    return lines


def suggestion_blocks(
    decision: RoutingDecision, catalog: OwnershipCatalog, context: dict[str, Any]
) -> list[dict]:
    team = catalog.get(decision.team_id)
    if decision.fell_back:
        header = (
            f"*Not confident enough to pick a team.* Best place to ask: {team.name} ({team.slack_channel})"
        )
    else:
        header = f"*Team:* {team.name} ({team.slack_channel})"
    lines = [header, *responsibles_text(decision.assignee, decision.experts)]
    lines.append(f"*Confidence:* {decision.confidence:.0%}")
    if decision.alternative_team_ids:
        alts = ", ".join(catalog.get(t).name for t in decision.alternative_team_ids)
        lines.append(f"*Also possible:* {alts}")

    # Button values are capped at 2000 chars by Slack, so the rationale is trimmed.
    value = json.dumps(
        {
            **context,
            "team_id": decision.team_id,
            "assignee": decision.assignee,
            "experts": decision.experts,
            "confidence": decision.confidence,
            "rationale": decision.rationale[:800],
        }
    )
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"_Why:_ {decision.rationale}"}]},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "confirm_route",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Confirm"},
                    "value": value,
                },
                {
                    "type": "button",
                    "action_id": "correct_route",
                    "text": {"type": "plain_text", "text": "Pick another team"},
                    "value": value,
                },
            ],
        },
    ]


def resolved_blocks(blocks: list[dict], note: str) -> list[dict]:
    """The suggestion without its buttons, so the same answer cannot be confirmed twice."""
    kept = [b for b in blocks if b.get("type") != "actions"]
    return [*kept, {"type": "context", "elements": [{"type": "mrkdwn", "text": note}]}]


def correction_modal(catalog: OwnershipCatalog, private_metadata: str) -> dict:
    options = [
        {"text": {"type": "plain_text", "text": t.name}, "value": t.id} for t in catalog.teams.values()
    ]
    return {
        "type": "modal",
        "callback_id": "correct_route_submit",
        "private_metadata": private_metadata,
        "title": {"type": "plain_text", "text": "Pick the right team"},
        "submit": {"type": "plain_text", "text": "Save"},
        "blocks": [
            {
                "type": "input",
                "block_id": "team",
                "label": {"type": "plain_text", "text": "Which team owns this?"},
                "element": {"type": "static_select", "action_id": "team_id", "options": options},
            }
        ],
    }
