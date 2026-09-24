import json

import httpx

from escalation_router.sources import JiraSource
from escalation_router.writeback import JiraWriteback, Routing, jira_comment


def recording_jira(status: dict[str, int] | None = None):
    status = status or {}
    calls: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        return httpx.Response(status.get(request.method, 200), json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return JiraSource("https://acme.atlassian.net", "bot@acme.org", "tok", http=http), calls


def routing(toolbox, **overrides):
    base = dict(
        team=toolbox.catalog.get("payments"),
        assignee="Ana Souza",
        experts=["Bruno Lima"],
        confirmed_by="luis",
        confidence=0.82,
        rationale="Matches ESC-115.",
        suggested_team=toolbox.catalog.get("payments"),
    )
    return Routing(**{**base, **overrides})


def test_comment_names_team_and_people_without_mentions(toolbox):
    comment = jira_comment(routing(toolbox))
    assert "*Team:* Payments" in comment
    assert "Ana Souza" in comment and "Bruno Lima" in comment
    assert "82%" in comment and "confirmed by luis" in comment
    assert "[~" not in comment and "accountid" not in comment.lower()


def test_comment_explains_a_correction(toolbox):
    comment = jira_comment(routing(toolbox, team=toolbox.catalog.get("reporting"), experts=[]))
    assert "*Team:* Reporting & Receipts" in comment
    assert "had suggested Payments" in comment


def test_default_writeback_only_comments(toolbox):
    jira, calls = recording_jira()
    errors = JiraWriteback(jira).apply("SUP-381", routing(toolbox))

    assert errors == []
    assert [(m, p) for m, p, _ in calls] == [("POST", "/rest/api/2/issue/SUP-381/comment")]


def test_field_updates_are_opt_in(toolbox):
    jira, calls = recording_jira()
    JiraWriteback(jira, update_fields=True).apply("SUP-381", routing(toolbox))

    method, path, body = calls[1]
    assert (method, path) == ("PUT", "/rest/api/2/issue/SUP-381")
    assert body["update"]["components"] == [{"set": [{"name": "Payments"}]}]


def test_errors_are_returned_not_raised(toolbox):
    jira, _ = recording_jira({"POST": 403})
    errors = JiraWriteback(jira).apply("SUP-381", routing(toolbox))
    assert "Could not comment on SUP-381: HTTP 403" in errors[0]
