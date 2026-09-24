import pytest

from escalation_router.agent import EscalationRouter, RouterConfig, RoutingError
from escalation_router.tools import SUBMIT_TOOL

from .fakes import FakeClient, response, text, tool_use


def decision(**overrides):
    base = {
        "team_id": "integrations",
        "assignee": "Gabriela Costa",
        "confidence": 0.85,
        "severity": "medium",
        "summary": "Salesforce sync duplicates contacts for returning donors.",
        "rationale": "Matches ESC-103, fixed by Integrations.",
        "alternative_team_ids": ["reporting"],
        "clarifying_questions": [],
        "evidence": ["ESC-103"],
    }
    return {**base, **overrides}


def make_router(toolbox, responses, **config):
    client = FakeClient(responses)
    return EscalationRouter(toolbox, client=client, config=RouterConfig(**config)), client


def test_runs_tools_then_returns_decision(toolbox):
    router, client = make_router(
        toolbox,
        [
            response(
                tool_use("search_past_escalations", query="salesforce duplicate"),
                tool_use("search_ownership", query="salesforce"),
            ),
            response(tool_use("get_oncall", team_id="integrations")),
            response(tool_use(SUBMIT_TOOL, **decision())),
        ],
    )

    result = router.route("Salesforce has duplicate contacts for donor ana@example.org")

    assert result.decision.team_id == "integrations"
    assert not result.decision.fell_back
    assert [c["name"] for c in result.tool_calls] == [
        "search_past_escalations",
        "search_ownership",
        "get_oncall",
        SUBMIT_TOOL,
    ]
    # PII never reaches the model.
    assert "ana@example.org" not in client.requests[0]["messages"][0]["content"]
    # Both parallel tool results go back in a single user message.
    second_turn = client.requests[1]["messages"][-1]["content"]
    assert [r["type"] for r in second_turn] == ["tool_result", "tool_result"]
    assert "ESC-103" in second_turn[0]["content"]


def test_unknown_team_is_returned_as_tool_error_and_model_retries(toolbox):
    router, client = make_router(
        toolbox,
        [
            response(tool_use(SUBMIT_TOOL, **decision(team_id="crm-team"))),
            response(tool_use(SUBMIT_TOOL, **decision())),
        ],
    )

    result = router.route("Salesforce duplicates")

    error = client.requests[1]["messages"][-1]["content"][0]
    assert error["is_error"] is True
    assert "Known teams" in error["content"]
    assert result.decision.team_id == "integrations"


def test_low_confidence_falls_back_to_triage_rotation(toolbox):
    router, _ = make_router(
        toolbox,
        [
            response(tool_use(SUBMIT_TOOL, **decision(confidence=0.3, alternative_team_ids=[]))),
        ],
    )

    d = router.route("customer says it's broken").decision

    assert d.fell_back
    assert d.team_id == "support-escalations"
    assert d.alternative_team_ids == ["integrations"]
    assert d.assignee in toolbox.oncall.rotations["support-escalations"]


def test_nudges_model_when_it_answers_without_submitting(toolbox):
    router, client = make_router(
        toolbox,
        [
            response(text("I think this is Integrations.")),
            response(tool_use(SUBMIT_TOOL, **decision())),
        ],
    )

    router.route("Salesforce duplicates")

    assert SUBMIT_TOOL in client.requests[1]["messages"][-1]["content"]


def test_refusal_raises(toolbox):
    router, _ = make_router(toolbox, [response(stop_reason="refusal")])
    with pytest.raises(RoutingError):
        router.route("anything")


def test_request_uses_fallbacks_and_adaptive_thinking(toolbox):
    router, client = make_router(toolbox, [response(tool_use(SUBMIT_TOOL, **decision()))])
    router.route("Salesforce duplicates")

    params = client.requests[0]
    assert params["model"] == "claude-opus-5"
    assert params["thinking"] == {"type": "adaptive"}
    assert params["fallbacks"] == "default"
    assert params["betas"] == ["server-side-fallback-2026-07-01"]
