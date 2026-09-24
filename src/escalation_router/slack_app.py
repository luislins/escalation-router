"""Slack entry point (Socket Mode, so no public URL is needed).

The bot answers in the thread with the owning team and the people responsible. It does not
@mention anyone or post in team channels: support decides what to do with the answer.

Flows:
- Mention @router in a thread: the whole thread is read and routed. Zendesk ticket and
  Jira issue links found in it are fetched, so "@router https://acme.atlassian.net/browse/SUP-381"
  is enough.
- "Who owns this?" message shortcut: that single message (and any ticket it links) is routed.
- Confirm / Pick another team: records feedback and, when a Jira issue is linked, leaves a comment
  on it with the team and the people responsible.
"""

from __future__ import annotations

import json
import logging
import os

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from . import feedback
from .blocks import correction_modal, resolved_blocks, responsibles_text, suggestion_blocks
from .config import build_router
from .router import EscalationRouter, RoutingError
from .sources import TicketLoader, compose_report
from .writeback import JiraWriteback, Routing

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
        "jira_key": report.jira_keys[0] if report.jira_keys else None,
    }
    client.chat_update(
        channel=channel,
        ts=placeholder["ts"],
        text=f"Team: {router.toolbox.catalog.get(result.decision.team_id).name}",
        blocks=suggestion_blocks(result.decision, router.toolbox.catalog, context),
    )


def confirm(
    client,
    router: EscalationRouter,
    writeback: JiraWriteback | None,
    ctx: dict,
    team_id: str,
    assignee: str | None,
    experts: list[str],
    user: dict,
) -> str:
    """Record the confirmed team and write it to the linked Jira issue. Returns a note for the thread."""
    catalog = router.toolbox.catalog
    team = catalog.get(team_id)
    note = f":white_check_mark: {team.name} confirmed by <@{user['id']}>."
    if ctx.get("jira_key") and writeback:
        accepted = team_id == ctx["suggested_team"]
        errors = writeback.apply(
            ctx["jira_key"],
            Routing(
                team=team,
                assignee=assignee,
                experts=experts,
                confirmed_by=user.get("name") or user["id"],
                confidence=ctx.get("confidence") if accepted else None,
                rationale=ctx.get("rationale") if accepted else None,
                suggested_team=catalog.get(ctx["suggested_team"]),
            ),
        )
        for error in errors:
            client.chat_postMessage(
                channel=ctx["channel"], thread_ts=ctx["thread_ts"], text=f":warning: {error}"
            )
        if not errors:
            note += f" Noted on Jira {ctx['jira_key']}."
    reference = ctx.get("jira_key") or ctx.get("ticket_url") or ctx.get("rationale", "")
    feedback.record(reference, ctx["suggested_team"], team_id, user["id"])
    return note


def create_app(router: EscalationRouter | None = None, loader: TicketLoader | None = None) -> App:
    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    router = router or build_router()
    loader = loader or TicketLoader.from_env()
    writeback = JiraWriteback.from_env()

    @app.event("app_mention")
    def on_mention(event, client, context):
        thread_ts = event.get("thread_ts") or event["ts"]
        report = thread_text(client, event["channel"], thread_ts, context["bot_user_id"])
        post_suggestion(client, router, loader, event["channel"], thread_ts, report)

    @app.shortcut("route_message")
    def on_shortcut(ack, shortcut, client):
        ack()
        message = shortcut["message"]
        thread_ts = message.get("thread_ts") or message["ts"]
        post_suggestion(client, router, loader, shortcut["channel"]["id"], thread_ts, message.get("text", ""))

    @app.action("confirm_route")
    def on_confirm(ack, body, client):
        ack()
        ctx = json.loads(body["actions"][0]["value"])
        message = body["message"]
        # Remove the buttons first, so a double click cannot write to Jira twice.
        client.chat_update(
            channel=ctx["channel"],
            ts=message["ts"],
            text="Saving...",
            blocks=resolved_blocks(message["blocks"], ":hourglass: Saving..."),
        )
        note = confirm(
            client, router, writeback, ctx, ctx["team_id"], ctx["assignee"], ctx["experts"], body["user"]
        )
        client.chat_update(
            channel=ctx["channel"],
            ts=message["ts"],
            text=note,
            blocks=resolved_blocks(message["blocks"], note),
        )

    @app.action("correct_route")
    def on_correct(ack, body, client):
        ack()
        ctx = json.loads(body["actions"][0]["value"])
        ctx["suggestion_ts"] = body["message"]["ts"]
        client.views_open(
            trigger_id=body["trigger_id"],
            view=correction_modal(router.toolbox.catalog, json.dumps(ctx)),
        )

    @app.view("correct_route_submit")
    def on_correct_submit(ack, body, client, view):
        ack()
        ctx = json.loads(view["private_metadata"])
        team_id = view["state"]["values"]["team"]["team_id"]["selected_option"]["value"]
        team = router.toolbox.catalog.get(team_id)
        oncall = router.toolbox.oncall.current(team_id)
        note = confirm(client, router, writeback, ctx, team_id, oncall, [], body["user"])
        suggested = router.toolbox.catalog.get(ctx["suggested_team"]).name
        lines = [f"*Team:* {team.name} ({team.slack_channel})", *responsibles_text(oncall, [])]
        client.chat_update(
            channel=ctx["channel"],
            ts=ctx["suggestion_ts"],
            text=note,
            blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"{note} _I had suggested {suggested}._"}],
                },
            ],
        )

    return app


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    SocketModeHandler(create_app(), os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
