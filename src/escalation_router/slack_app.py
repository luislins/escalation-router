"""Slack entry point (Socket Mode, so no public URL is needed).

Flows:
- Mention @router in a thread: the whole thread is read and routed. Zendesk ticket and
  Jira issue links found in it are fetched, so "@router https://acme.zendesk.com/agent/tickets/1042"
  is enough.
- "Escalate this" message shortcut: that single message (and any ticket it links) is routed.
- Buttons on the suggestion: escalate as suggested, or pick another team.
"""

from __future__ import annotations

import json
import logging
import os

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from . import feedback
from .agent import EscalationRouter, RoutingError
from .blocks import correction_modal, escalation_message, suggestion_blocks
from .config import build_router
from .sources import TicketLoader, compose_report

log = logging.getLogger(__name__)


def thread_text(client, channel: str, thread_ts: str, bot_user_id: str) -> str:
    replies = client.conversations_replies(channel=channel, ts=thread_ts, limit=50)
    lines = [
        m.get("text", "").replace(f"<@{bot_user_id}>", "").strip()
        for m in replies["messages"]
        if m.get("user") != bot_user_id
    ]
    return "\n\n".join(line for line in lines if line)


def post_suggestion(
    client, router: EscalationRouter, loader: TicketLoader, channel: str, thread_ts: str, discussion: str
) -> None:
    placeholder = client.chat_postMessage(
        channel=channel, thread_ts=thread_ts, text=":mag: Looking into who owns this..."
    )
    report = compose_report(discussion, loader)
    for error in report.errors:
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=f":warning: {error}")
    try:
        result = router.route(report.text)
    except RoutingError as exc:
        client.chat_update(
            channel=channel,
            ts=placeholder["ts"],
            text=f":warning: I couldn't route this one ({exc}). Please use #support-escalations.",
        )
        return
    context = {
        "channel": channel,
        "thread_ts": thread_ts,
        "suggested_team": result.decision.team_id,
        "ticket_url": report.ticket_urls[0] if report.ticket_urls else None,
    }
    client.chat_update(
        channel=channel,
        ts=placeholder["ts"],
        text=f"Suggested team: {result.decision.team_id}",
        blocks=suggestion_blocks(result.decision, router.toolbox.catalog, context),
    )


def escalate(
    client, router: EscalationRouter, ctx: dict, team_id: str, assignee: str | None, user_id: str
) -> None:
    team = router.toolbox.catalog.get(team_id)
    permalink = client.chat_getPermalink(channel=ctx["channel"], message_ts=ctx["thread_ts"])["permalink"]
    client.chat_postMessage(
        channel=team.slack_channel,
        text=escalation_message(
            team.name, assignee, ctx["summary"], permalink, user_id, ctx.get("ticket_url")
        ),
    )
    client.chat_postMessage(
        channel=ctx["channel"],
        thread_ts=ctx["thread_ts"],
        text=f":white_check_mark: Escalated to {team.name} ({team.slack_channel}) by <@{user_id}>.",
    )
    feedback.record(ctx["summary"], ctx["suggested_team"], team_id, user_id)


def create_app(router: EscalationRouter | None = None, loader: TicketLoader | None = None) -> App:
    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    router = router or build_router()
    loader = loader or TicketLoader.from_env()

    @app.event("app_mention")
    def on_mention(event, client, context):
        thread_ts = event.get("thread_ts") or event["ts"]
        report = thread_text(client, event["channel"], thread_ts, context["bot_user_id"])
        post_suggestion(client, router, loader, event["channel"], thread_ts, report)

    @app.shortcut("escalate_message")
    def on_shortcut(ack, shortcut, client):
        ack()
        message = shortcut["message"]
        thread_ts = message.get("thread_ts") or message["ts"]
        post_suggestion(client, router, loader, shortcut["channel"]["id"], thread_ts, message.get("text", ""))

    @app.action("escalate")
    def on_escalate(ack, body, client):
        ack()
        ctx = json.loads(body["actions"][0]["value"])
        escalate(client, router, ctx, ctx["team_id"], ctx["assignee"], body["user"]["id"])

    @app.action("correct_route")
    def on_correct(ack, body, client):
        ack()
        client.views_open(
            trigger_id=body["trigger_id"],
            view=correction_modal(router.toolbox.catalog, body["actions"][0]["value"]),
        )

    @app.view("correct_route_submit")
    def on_correct_submit(ack, body, client, view):
        ack()
        ctx = json.loads(view["private_metadata"])
        team_id = view["state"]["values"]["team"]["team_id"]["selected_option"]["value"]
        escalate(client, router, ctx, team_id, router.toolbox.oncall.current(team_id), body["user"]["id"])

    return app


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    SocketModeHandler(create_app(), os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
