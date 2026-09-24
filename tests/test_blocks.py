import json

from escalation_router.blocks import correction_modal, resolved_blocks, suggestion_blocks
from escalation_router.models import RoutingDecision


def make_decision(**overrides):
    base = dict(
        team_id="payments",
        assignee="Ana Souza",
        confidence=0.9,
        severity="high",
        summary="Refund stuck.",
        rationale="x" * 3000,
        alternative_team_ids=["reporting"],
        experts=["Bruno Lima"],
    )
    return RoutingDecision(**{**base, **overrides})


def test_suggestion_shows_team_and_responsibles_without_mentions(toolbox):
    context = {"channel": "C1", "thread_ts": "1.2", "suggested_team": "payments", "jira_key": "SUP-1"}
    blocks = suggestion_blocks(make_decision(), toolbox.catalog, context)

    text = blocks[0]["text"]["text"]
    assert "*Team:* Payments" in text
    assert "Ana Souza" in text and "Bruno Lima" in text
    assert "Reporting & Receipts" in text
    assert "<@" not in json.dumps(blocks)

    value = blocks[-1]["elements"][0]["value"]
    assert len(value) <= 2000
    assert json.loads(value)["jira_key"] == "SUP-1"


def test_fallback_is_worded_as_uncertain(toolbox):
    blocks = suggestion_blocks(
        make_decision(team_id="support-escalations", fell_back=True), toolbox.catalog, {}
    )
    assert "Not confident" in blocks[0]["text"]["text"]


def test_resolved_blocks_drop_buttons():
    blocks = [{"type": "section"}, {"type": "actions"}]
    out = resolved_blocks(blocks, "done")
    assert [b["type"] for b in out] == ["section", "context"]


def test_correction_modal_lists_every_team(toolbox):
    modal = correction_modal(toolbox.catalog, "{}")
    options = modal["blocks"][0]["element"]["options"]
    assert len(options) == len(toolbox.catalog.teams)
