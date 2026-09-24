import httpx
import pytest

from escalation_router.sources import (
    JiraSource,
    TicketLoader,
    TicketNotFound,
    ZendeskSource,
    compose_report,
    find_ticket_refs,
    parse_ref,
)

ZENDESK_TICKET = {
    "ticket": {
        "id": 1042,
        "subject": "Recibo anual sem o reembolso",
        "description": "Doadora diz que o recibo de 2025 não desconta o reembolso de março.",
        "priority": "high",
        "type": "problem",
        "tags": ["receipts", "refund"],
    }
}
ZENDESK_COMMENTS = {
    "comments": [
        {"plain_body": "Doadora diz que o recibo de 2025 não desconta o reembolso de março."},
        {"plain_body": "Confirmei no painel: o reembolso aparece como concluído."},
    ]
}
JIRA_ISSUE = {
    "fields": {
        "summary": "Salesforce sync duplicating contacts",
        "description": "Org reports duplicate contacts after every recurring donation.",
        "issuetype": {"name": "Bug"},
        "priority": {"name": "Medium"},
        "components": [{"name": "Salesforce"}],
        "labels": ["crm"],
        "comment": {"comments": [{"body": "Happens only for returning donors."}]},
    }
}


def mock_http(routes: dict[str, dict]) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = routes.get(request.url.path)
        return httpx.Response(200, json=body) if body else httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def zendesk():
    http, seen = mock_http(
        {
            "/api/v2/tickets/1042.json": ZENDESK_TICKET,
            "/api/v2/tickets/1042/comments.json": ZENDESK_COMMENTS,
        }
    )
    return ZendeskSource("acme", "bot@acme.org", "tok", http=http), seen


def jira():
    http, seen = mock_http({"/rest/api/2/issue/SUP-381": JIRA_ISSUE})
    return JiraSource("https://acme.atlassian.net/", "bot@acme.org", "tok", http=http), seen


def test_zendesk_ticket_becomes_report_without_repeating_description():
    source, seen = zendesk()
    ticket = source.fetch("1042")

    report = ticket.to_report()
    assert ticket.url == "https://acme.zendesk.com/agent/tickets/1042"
    assert "Tags: receipts, refund" in report
    assert report.count("não desconta o reembolso") == 1
    assert "Confirmei no painel" in report
    assert seen[0].headers["authorization"].startswith("Basic ")


def test_jira_issue_includes_components_and_comments():
    source, _ = jira()
    ticket = source.fetch("SUP-381")

    report = ticket.to_report()
    assert ticket.url == "https://acme.atlassian.net/browse/SUP-381"
    assert "Components: Salesforce" in report
    assert "returning donors" in report


def test_missing_ticket_raises():
    source, _ = jira()
    with pytest.raises(TicketNotFound):
        source.fetch("SUP-999")


@pytest.mark.parametrize(
    ("value", "source", "id_"),
    [
        ("https://acme.zendesk.com/agent/tickets/1042", "zendesk", "1042"),
        ("<https://acme.zendesk.com/agent/tickets/1042|#1042>", "zendesk", "1042"),
        ("zd:1042", "zendesk", "1042"),
        ("#1042", "zendesk", "1042"),
        ("https://acme.atlassian.net/browse/SUP-381", "jira", "SUP-381"),
        ("SUP-381", "jira", "SUP-381"),
    ],
)
def test_parse_ref(value, source, id_):
    ref = parse_ref(value)
    assert (ref.source, ref.id) == (source, id_)


def test_free_text_is_not_a_ticket_ref():
    assert parse_ref("Donor says the receipt has the wrong total") is None


def test_compose_report_fetches_linked_tickets_once_and_keeps_discussion():
    zd, _ = zendesk()
    jr, _ = jira()
    thread = (
        "Can someone look at <https://acme.zendesk.com/agent/tickets/1042>?\n"
        "Maybe related to https://acme.atlassian.net/browse/SUP-381 and again "
        "https://acme.zendesk.com/agent/tickets/1042"
    )

    report = compose_report(thread, TicketLoader(zendesk=zd, jira=jr))

    assert report.ticket_urls == [
        "https://acme.zendesk.com/agent/tickets/1042",
        "https://acme.atlassian.net/browse/SUP-381",
    ]
    assert "Recibo anual" in report.text and "Salesforce sync" in report.text
    assert report.text.endswith(thread)


def test_compose_report_reports_unconfigured_source_and_still_routes_on_text():
    report = compose_report("see https://acme.atlassian.net/browse/SUP-1", TicketLoader())

    assert report.ticket_urls == []
    assert "not configured" in report.errors[0]
    assert "Slack discussion" in report.text


def test_find_refs_in_slack_markup():
    refs = find_ticket_refs("<https://acme.atlassian.net/browse/PAY-12|PAY-12> and zd link")
    assert [(r.source, r.id) for r in refs] == [("jira", "PAY-12")]
