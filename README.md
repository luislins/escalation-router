# Escalation Router

**An agent that reads a Zendesk ticket or Jira issue and tells support which engineering team owns the bug, and who is responsible.**

Support agents are not engineers. When a customer reports "the donation button spins forever" or
"my receipt has the wrong total", the agent has to guess whether that belongs to Payments,
Donor Experience, Integrations or Reporting. Bugs sit in a generic channel, get bounced between teams,
and the customer waits.

Escalation Router takes the ticket support already wrote (Zendesk ticket or Jira issue: title, fields,
description, latest comments), investigates with tools (the ownership catalog, similar past
escalations, the on-call schedule) and answers in the thread with the owning team, the person on call,
the people who fixed similar bugs before, and a confidence score. It does not ping anyone: names are
plain text, nothing is posted in team channels. A person clicks **Confirm** or picks another team; the
answer is logged (so it can become an evaluation case) and, for Jira issues, left as a comment.

```
Zendesk ticket / Jira issue
          │  "@router https://acme.zendesk.com/agent/tickets/1042"  (Slack)
          │  escalation-router SUP-381                               (CLI)
          ▼
   ticket → plain text (title, components/tags, description, comments) → PII redaction
                              │
                              ▼
                   ┌─────────────────────┐    search_ownership
                   │  Claude (tool use)  │──▶ search_past_escalations
                   │  adaptive thinking  │    get_team / get_oncall
                   └─────────┬───────────┘
                             │ submit_routing (strict JSON schema)
                             ▼
        team + on call + people who fixed similar bugs + confidence   (no @mentions)
                             │
                 [Confirm]   │  [Pick another team] ──▶ feedback.jsonl ──▶ evals
                             ▼
                 comment on the Jira issue (team + people responsible)
```

## Design choices

- **Nobody gets pinged.** The bot answers with the team and people responsible, without @mentions.
  Support decides what to do next. On Jira, the confirmed answer is a plain comment; changing
  component/labels is opt-in (`JIRA_UPDATE_FIELDS=true`) because it can trigger automations.
- **Low confidence goes to people, not to a guess.** Below the threshold (default 0.5), the report goes
  to the triage rotation, with the agent's best guess listed as an alternative.
- **Personal data never reaches the model.** Emails, phone numbers, card numbers (Luhn-checked) and API
  keys are replaced with placeholders before the LLM call.
- **Structured output via a terminating tool.** The loop ends when Claude calls `submit_routing`, whose
  schema is enforced with `strict: true` and validated again with Pydantic. An unknown team id goes back
  to the model as a tool error so it can correct itself.
- **Starts from the ticket, not a retyped summary.** Zendesk and Jira are fetched through their REST
  APIs. Jira components and Zendesk tags are passed along as hints, weighed against the description
  since support often sets them.
- **Pluggable knowledge sources.** Ownership, on-call and history are plain YAML/JSONL files in the demo.
  In a real deployment each one is a small class you can back with Backstage, PagerDuty, Jira, etc.
- **Measurable.** `evals/run_eval.py` reports top-1 and top-3 routing accuracy on labeled cases.
  Corrections made in Slack are logged in the same shape.

## Demo data

`demo/` holds a fictional online fundraising platform, **Acme Giving**, with seven teams, a weekly on-call
rotation and sixteen past escalations. Everything in it is synthetic.

## Quick start

```bash
uv venv && uv pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...
# Ticket sources: set the ones you use (see .env.example)
export ZENDESK_SUBDOMAIN=acme ZENDESK_EMAIL=bot@acme.org ZENDESK_API_TOKEN=...
export JIRA_BASE_URL=https://acme.atlassian.net JIRA_EMAIL=bot@acme.org JIRA_API_TOKEN=...

# Route a ticket from the terminal (no Slack needed)
.venv/bin/escalation-router https://acme.zendesk.com/agent/tickets/1042   # or zd:1042
.venv/bin/escalation-router SUP-381                                       # Jira key or URL
.venv/bin/escalation-router SUP-381 --write-back                          # + comment on the issue
.venv/bin/escalation-router --trace "Donor says the year-end receipt PDF is missing her refund"

# Measure accuracy on the labeled cases (spends real tokens)
.venv/bin/python evals/run_eval.py
# Keyword-matching baseline on the same cases (free): the number the agent has to beat
.venv/bin/python evals/run_eval.py --baseline

# Unit tests (no API calls, uses a scripted fake client)
.venv/bin/pytest
```

## Running in Slack

1. Create an app at <https://api.slack.com/apps> → **From an app manifest** and paste
   [`slack-manifest.yml`](slack-manifest.yml).
2. Install it to the workspace and copy the **Bot token** (`xoxb-...`). Under *Basic Information*, create
   an **App-level token** with the `connections:write` scope (`xapp-...`).
3. Invite the bot to the support channel and to each team channel listed in `ownership.yaml`.
4. Run it:

```bash
cp .env.example .env   # fill in the tokens
set -a && source .env && set +a
.venv/bin/escalation-router-slack
# or: docker build -t escalation-router . && docker run --env-file .env escalation-router
```

Socket Mode is used, so no public URL is needed.

Then paste a ticket link and mention the bot, e.g. `@router https://acme.zendesk.com/agent/tickets/1042`
or `@router https://acme.atlassian.net/browse/SUP-381`. Every Zendesk/Jira link in the thread is fetched
(up to three), and the rest of the thread is included as context. The **Who owns this?** message
shortcut does the same for a single message. **Confirm** (or picking another team) leaves the answer as a
comment on the linked Jira issue.

## Using your own company's data

Point `ROUTER_DATA_DIR` at a folder with your own `ownership.yaml`, `oncall.yaml` and `history.jsonl`
(same format as `demo/`). Keep that folder out of this repository.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ROUTER_DATA_DIR` | `demo/` | Folder with the three knowledge files |
| `ROUTER_MODEL` | `claude-opus-5` | Claude model |
| `ROUTER_EFFORT` | `medium` | `low` / `medium` / `high` reasoning effort |
| `ROUTER_CONFIDENCE_THRESHOLD` | `0.5` | Below this, route to the fallback team |
| `ROUTER_USE_FALLBACKS` | `true` | Server-side fallback model if a request is declined |
| `ROUTER_FEEDBACK_FILE` | `feedback.jsonl` | Where escalations and corrections are logged |
| `JIRA_UPDATE_FIELDS` | `false` | Also set the team's Jira component and an `escalation-router` label |
| `ZENDESK_SUBDOMAIN` / `ZENDESK_EMAIL` / `ZENDESK_API_TOKEN` | | Zendesk API token auth |
| `JIRA_BASE_URL` / `JIRA_EMAIL` / `JIRA_API_TOKEN` | | Jira Cloud API token auth |

## Roadmap

- [x] Agent with ownership catalog, past escalations and on-call tools
- [x] Input from Zendesk tickets and Jira issues (CLI and Slack links)
- [x] Slack app with Confirm / Pick another team, no pings
- [x] Confirmed answer written to the Jira issue as a comment (`--write-back` on the CLI)
- [x] PII redaction, confidence fallback, feedback log, eval runner
- [ ] Connectors: Slack history search, GitHub CODEOWNERS and recent commits, Jira, PagerDuty
- [ ] Same for Zendesk (internal note); optionally assign group or component
- [ ] Trigger automatically from a Zendesk trigger or Jira automation webhook
- [ ] Expose the tools as an MCP server so engineers can ask "who owns this?" from their editor
