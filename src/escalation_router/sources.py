"""Load bug reports from where support already writes them: Zendesk tickets and Jira issues.

A ticket is turned into plain text for the agent. Structured fields (Jira components,
Zendesk tags and group) go in too, since they are often the strongest routing hint.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import httpx

MAX_COMMENTS = 10
MAX_CHARS_PER_COMMENT = 2000

_ZENDESK_URL = re.compile(
    r"https://([a-z0-9-]+)\.zendesk\.com/(?:agent/tickets|hc/[^/]+/requests)/(\d+)", re.IGNORECASE
)
_JIRA_URL = re.compile(r"(https://[a-z0-9.-]+)/browse/([A-Z][A-Z0-9_]+-\d+)")
_JIRA_KEY = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


class TicketNotFound(Exception):
    pass


@dataclass
class Ticket:
    source: str
    id: str
    url: str
    title: str
    description: str
    fields: dict[str, str] = field(default_factory=dict)
    comments: list[str] = field(default_factory=list)

    def to_report(self) -> str:
        parts = [f"Source: {self.source} {self.id}", f"Title: {self.title}"]
        parts += [f"{name}: {value}" for name, value in self.fields.items() if value]
        parts += ["", "Description:", self.description.strip() or "(empty)"]
        recent = self.comments[-MAX_COMMENTS:]
        if recent:
            parts += ["", f"Latest comments ({len(recent)} of {len(self.comments)}):"]
            parts += [f"- {c.strip()[:MAX_CHARS_PER_COMMENT]}" for c in recent if c.strip()]
        return "\n".join(parts)


class ZendeskSource:
    """Zendesk Support API with an API token (Admin Center > Apps and integrations > Zendesk API)."""

    def __init__(self, subdomain: str, email: str, api_token: str, http: httpx.Client | None = None):
        self.subdomain = subdomain
        self.http = http or httpx.Client(timeout=20)
        self.auth = (f"{email}/token", api_token)

    @classmethod
    def from_env(cls) -> ZendeskSource | None:
        keys = ("ZENDESK_SUBDOMAIN", "ZENDESK_EMAIL", "ZENDESK_API_TOKEN")
        if not all(os.environ.get(k) for k in keys):
            return None
        return cls(*(os.environ[k] for k in keys))

    def _get(self, path: str) -> dict:
        url = f"https://{self.subdomain}.zendesk.com/api/v2/{path}"
        response = self.http.get(url, auth=self.auth)
        if response.status_code == 404:
            raise TicketNotFound(f"Zendesk ticket not found: {path}")
        response.raise_for_status()
        return response.json()

    def fetch(self, ticket_id: str) -> Ticket:
        ticket = self._get(f"tickets/{ticket_id}.json")["ticket"]
        comments = self._get(f"tickets/{ticket_id}/comments.json")["comments"]
        # The first comment is the ticket description; the rest is the conversation.
        bodies = [c.get("plain_body") or c.get("body", "") for c in comments[1:]]
        return Ticket(
            source="Zendesk",
            id=f"#{ticket['id']}",
            url=f"https://{self.subdomain}.zendesk.com/agent/tickets/{ticket['id']}",
            title=ticket.get("subject") or "",
            description=ticket.get("description") or "",
            fields={
                "Priority": ticket.get("priority") or "",
                "Type": ticket.get("type") or "",
                "Tags": ", ".join(ticket.get("tags") or []),
            },
            comments=bodies,
        )


class JiraSource:
    """Jira Cloud REST API v2 (plain-text bodies) with an Atlassian API token."""

    def __init__(self, base_url: str, email: str, api_token: str, http: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=20)
        self.auth = (email, api_token)

    @classmethod
    def from_env(cls) -> JiraSource | None:
        keys = ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
        if not all(os.environ.get(k) for k in keys):
            return None
        return cls(*(os.environ[k] for k in keys))

    def fetch(self, key: str) -> Ticket:
        response = self.http.get(
            f"{self.base_url}/rest/api/2/issue/{key}",
            params={"fields": "summary,description,priority,issuetype,labels,components,comment"},
            auth=self.auth,
        )
        if response.status_code == 404:
            raise TicketNotFound(f"Jira issue not found: {key}")
        response.raise_for_status()
        f = response.json()["fields"]
        return Ticket(
            source="Jira",
            id=key,
            url=f"{self.base_url}/browse/{key}",
            title=f.get("summary") or "",
            description=f.get("description") or "",
            fields={
                "Type": (f.get("issuetype") or {}).get("name", ""),
                "Priority": (f.get("priority") or {}).get("name", ""),
                "Components": ", ".join(c["name"] for c in f.get("components") or []),
                "Labels": ", ".join(f.get("labels") or []),
            },
            comments=[c.get("body", "") for c in (f.get("comment") or {}).get("comments", [])],
        )


@dataclass
class TicketRef:
    source: str  # "zendesk" or "jira"
    id: str


def find_ticket_refs(text: str) -> list[TicketRef]:
    """Zendesk and Jira links mentioned in free text (e.g. a Slack thread)."""
    refs = [TicketRef("zendesk", m.group(2)) for m in _ZENDESK_URL.finditer(text)]
    refs += [TicketRef("jira", m.group(2)) for m in _JIRA_URL.finditer(text)]
    return refs


def parse_ref(value: str) -> TicketRef | None:
    """A ticket URL, a Jira key (SUP-123) or a Zendesk id prefixed with zd: or #."""
    refs = find_ticket_refs(value)
    if refs:
        return refs[0]
    value = value.strip()
    if _JIRA_KEY.match(value):
        return TicketRef("jira", value)
    if m := re.fullmatch(r"(?:zd:|#)(\d+)", value):
        return TicketRef("zendesk", m.group(1))
    return None


@dataclass
class TicketLoader:
    zendesk: ZendeskSource | None = None
    jira: JiraSource | None = None

    @classmethod
    def from_env(cls) -> TicketLoader:
        return cls(zendesk=ZendeskSource.from_env(), jira=JiraSource.from_env())

    def load(self, ref: TicketRef) -> Ticket:
        source = self.zendesk if ref.source == "zendesk" else self.jira
        if source is None:
            name = ref.source.upper()
            raise TicketNotFound(f"{ref.source.title()} is not configured (set the {name}_* variables).")
        return source.fetch(ref.id)


MAX_TICKETS_PER_REPORT = 3


@dataclass
class ComposedReport:
    text: str
    ticket_urls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def compose_report(discussion: str, loader: TicketLoader) -> ComposedReport:
    """Tickets linked in a discussion (e.g. a Slack thread), followed by the discussion itself."""
    parts, urls, errors = [], [], []
    seen: set[tuple[str, str]] = set()
    for ref in find_ticket_refs(discussion):
        if (ref.source, ref.id) in seen or len(seen) >= MAX_TICKETS_PER_REPORT:
            continue
        seen.add((ref.source, ref.id))
        try:
            ticket = loader.load(ref)
        except (TicketNotFound, httpx.HTTPError) as exc:
            errors.append(str(exc) or f"Could not load {ref.source} {ref.id}")
            continue
        parts.append(ticket.to_report())
        urls.append(ticket.url)
    if discussion.strip():
        parts.append(f"Slack discussion:\n{discussion.strip()}")
    return ComposedReport(text="\n\n---\n\n".join(parts), ticket_urls=urls, errors=errors)
