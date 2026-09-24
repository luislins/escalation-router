"""Route a bug report from the terminal, without Slack.

escalation-router https://acme.zendesk.com/agent/tickets/1042
escalation-router SUP-381                     # Jira issue key
escalation-router zd:1042                     # Zendesk ticket id
escalation-router "Donor says the receipt PDF has the wrong total"
echo "..." | escalation-router -
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

from .config import build_router
from .sources import TicketLoader, TicketNotFound, parse_ref


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Suggest which team should own a bug report.")
    parser.add_argument(
        "report",
        help="Zendesk ticket URL or zd:<id>, Jira issue URL or key, free text, or '-' for stdin",
    )
    parser.add_argument("--trace", action="store_true", help="Also print the tool calls the agent made")
    args = parser.parse_args(argv)

    report = sys.stdin.read() if args.report == "-" else args.report
    ticket = None
    if ref := parse_ref(report):
        try:
            ticket = TicketLoader.from_env().load(ref)
        except (TicketNotFound, httpx.HTTPError) as exc:
            sys.exit(f"Could not load {ref.source} {ref.id}: {exc}")
        report = ticket.to_report()

    result = build_router().route(report)
    output = result.decision.model_dump()
    if ticket:
        output["ticket_url"] = ticket.url
    if args.trace:
        output["report_sent"] = report
        output["tool_calls"] = result.tool_calls
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
