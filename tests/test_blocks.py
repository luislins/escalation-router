import json

from escalation_router.blocks import correction_modal, suggestion_blocks
from escalation_router.models import RoutingDecision


def test_suggestion_blocks_carry_context_for_buttons(toolbox):
    decision = RoutingDecision(
        team_id="payments",
        assignee="Ana Souza",
        confidence=0.9,
        severity="high",
        summary="x" * 3000,
        rationale="Matches ESC-115.",
        alternative_team_ids=["reporting"],
        clarifying_questions=["Which gateway?"],
    )
    blocks = suggestion_blocks(
        decision, toolbox.catalog, {"channel": "C1", "thread_ts": "1.2", "suggested_team": "payments"}
    )

    actions = blocks[-1]["elements"]
    value = actions[0]["value"]
    assert len(value) <= 2000
    assert json.loads(value)["team_id"] == "payments"
    assert "Reporting & Receipts" in blocks[0]["text"]["text"]
    assert any("Which gateway?" in b.get("text", {}).get("text", "") for b in blocks)


def test_correction_modal_lists_every_team(toolbox):
    modal = correction_modal(toolbox.catalog, "{}")
    options = modal["blocks"][0]["element"]["options"]
    assert len(options) == len(toolbox.catalog.teams)
