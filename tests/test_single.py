import json

import pytest

from escalation_router.router import RouterConfig, RoutingError, SingleCallRouter

from .fakes import FakeClient, response, text


def answer(**overrides):
    base = {
        "team_id": "reporting",
        "confidence": 0.8,
        "severity": "medium",
        "summary": "Year-end receipt ignores a refund.",
        "rationale": "Same as ESC-104.",
        "alternative_team_ids": ["payments", "reporting", "payments"],
        "clarifying_questions": [],
        "evidence": ["ESC-104"],
    }
    return text(json.dumps({**base, **overrides}))


def make_router(toolbox, responses, **config):
    client = FakeClient(responses)
    return SingleCallRouter(toolbox, client=client, config=RouterConfig(**config)), client


def test_one_call_with_retrieved_context_and_enum_schema(toolbox):
    router, client = make_router(toolbox, [response(answer())])

    result = router.route(
        "Recibo anual da doadora maria@example.com não desconta o reembolso (receipt refund)"
    )

    assert len(client.requests) == 1
    assert result.model_calls == 1
    params = client.requests[0]
    prompt = params["messages"][0]["content"]
    assert "maria@example.com" not in prompt
    assert "ESC-104" in prompt  # similar escalation retrieved by code
    assert "<ownership_catalog>" in params["system"]
    schema = params["output_config"]["format"]["schema"]
    assert schema["properties"]["team_id"]["enum"] == list(toolbox.catalog.teams)
    assert params["output_config"]["effort"] == "medium"
    assert "tools" not in params


def test_people_responsible_are_filled_by_code(toolbox):
    toolbox.oncall.rotations["reporting"] = ["Joao Pereira"]
    router, _ = make_router(toolbox, [response(answer())])

    d = router.route("year-end receipt wrong total after refund").decision

    assert d.team_id == "reporting"
    assert d.assignee == "Joao Pereira"
    assert d.experts == ["Isabela Nunes"]  # resolved ESC-104
    assert d.alternative_team_ids == ["payments"]  # deduplicated, chosen team removed


def test_low_confidence_goes_to_triage(toolbox):
    router, _ = make_router(toolbox, [response(answer(confidence=0.3))])

    d = router.route("customer says it's broken").decision

    assert d.fell_back and d.team_id == "support-escalations"
    assert d.alternative_team_ids[0] == "reporting"
    assert d.experts == []


@pytest.mark.parametrize(
    "bad",
    [response(stop_reason="refusal"), response(text("not json")), response(answer(team_id="nope"))],
)
def test_bad_answers_raise_routing_error(toolbox, bad):
    router, _ = make_router(toolbox, [bad])
    with pytest.raises(RoutingError):
        router.route("anything")


def test_system_prompt_is_stable_across_requests(toolbox):
    router, client = make_router(toolbox, [response(answer()), response(answer())])
    router.route("first report")
    router.route("second report")
    assert client.requests[0]["system"] == client.requests[1]["system"]
