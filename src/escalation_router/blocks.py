"""Slack Block Kit layouts. Pure functions so they are easy to test."""

from __future__ import annotations

import json
from typing import Any

from .knowledge import OwnershipCatalog
from .models import RoutingDecision

SEVERITY_EMOJI = {
    "low": ":white_circle:",
    "medium": ":large_yellow_circle:",
    "high": ":large_orange_circle:",
    "critical": ":red_circle:",
}


def suggestion_blocks(
    decision: RoutingDecision, catalog: OwnershipCatalog, context: dict[str, Any]
) -> list[dict]:
    team = catalog.get(decision.team_id)
    header = f"*Suggested team:* {team.name} ({team.slack_channel})"
    if decision.fell_back:
        header = f"*Not confident enough to pick a team* — sending to {team.name} ({team.slack_channel})."
    lines = [
        header,
        f"*On call:* {decision.assignee or 'unknown'}",
        f"*Severity:* {SEVERITY_EMOJI[decision.severity]} {decision.severity}"
        f"   *Confidence:* {decision.confidence:.0%}",
    ]
    if decision.alternative_team_ids:
        alts = ", ".join(catalog.get(t).name for t in decision.alternative_team_ids)
        lines.append(f"*Also possible:* {alts}")

    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary for engineers*\n{decision.summary}"},
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"_Why:_ {decision.rationale}"}]},
    ]
    if decision.clarifying_questions:
        questions = "\n".join(f"• {q}" for q in decision.clarifying_questions)
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Ask the customer*\n{questions}"}}
        )

    # Button values are capped at 2000 chars by Slack, so the summary is trimmed.
    value = json.dumps(
        {
            **context,
            "team_id": decision.team_id,
            "assignee": decision.assignee,
            "summary": decision.summary[:1200],
        }
    )
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "escalate",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": f"Escalate to {team.name}"},
                    "value": value,
                },
                {
                    "type": "button",
                    "action_id": "correct_route",
                    "text": {"type": "plain_text", "text": "Pick another team"},
                    "value": value,
                },
            ],
        }
    )
    return blocks


def correction_modal(catalog: OwnershipCatalog, private_metadata: str) -> dict:
    options = [
        {"text": {"type": "plain_text", "text": t.name}, "value": t.id} for t in catalog.teams.values()
    ]
    return {
        "type": "modal",
        "callback_id": "correct_route_submit",
        "private_metadata": private_metadata,
        "title": {"type": "plain_text", "text": "Route to another team"},
        "submit": {"type": "plain_text", "text": "Escalate"},
        "blocks": [
            {
                "type": "input",
                "block_id": "team",
                "label": {"type": "plain_text", "text": "Which team owns this?"},
                "element": {"type": "static_select", "action_id": "team_id", "options": options},
            }
        ],
    }


def escalation_message(
    team_name: str, assignee: str | None, summary: str, permalink: str, by_user: str
) -> str:
    who = assignee or "on-call"
    return (
        f":rotating_light: *New escalation for {team_name}* (on call: {who})\n"
        f"{summary}\n<{permalink}|Original thread> · escalated by <@{by_user}>"
    )
