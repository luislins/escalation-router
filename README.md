# Escalation Router

**A Slack agent that tells customer support which engineering team owns a bug, and who is on call.**

Support agents are not engineers. When a customer reports "the donation button spins forever" or
"my receipt has the wrong total", the agent has to guess whether that belongs to Payments,
Donor Experience, Integrations or Reporting. Bugs sit in a generic channel, get bounced between teams,
and the customer waits.

Escalation Router reads the report, investigates with tools (the ownership catalog, similar past
escalations, the on-call schedule) and answers in the thread with a suggested team, the person on call,
a confidence score, and the bug rewritten for engineers. A human clicks **Escalate**, or picks another
team, and every correction is logged so it can become an evaluation case.

```
support agent ──@router──▶ Slack thread
                              │
                              ▼
                   ┌─────────────────────┐    search_ownership
                   │  Claude (tool use)  │──▶ search_past_escalations
                   │  adaptive thinking  │    get_team / get_oncall
                   └─────────┬───────────┘
                             │ submit_routing (strict JSON schema)
                             ▼
             team + on-call + confidence + summary + questions for the customer
                             │
                 [Escalate]  │  [Pick another team] ──▶ feedback.jsonl ──▶ evals
                             ▼
                     #team-payments etc.
```

## Design choices

- **A human stays in control.** The bot only suggests; nobody gets pinged until someone clicks Escalate.
- **Low confidence goes to people, not to a guess.** Below the threshold (default 0.5), the report goes
  to the triage rotation, with the agent's best guess listed as an alternative.
- **Personal data never reaches the model.** Emails, phone numbers, card numbers (Luhn-checked) and API
  keys are replaced with placeholders before the LLM call.
- **Structured output via a terminating tool.** The loop ends when Claude calls `submit_routing`, whose
  schema is enforced with `strict: true` and validated again with Pydantic. An unknown team id goes back
  to the model as a tool error so it can correct itself.
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

# Route from the terminal (no Slack needed)
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

Then mention `@router` in a bug thread, or use the **Escalate this** shortcut on a message.

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

## Roadmap

- [x] Agent with ownership catalog, past escalations and on-call tools
- [x] Slack app with Escalate / Pick another team
- [x] PII redaction, confidence fallback, feedback log, eval runner
- [ ] Connectors: Slack history search, GitHub CODEOWNERS and recent commits, Jira, PagerDuty
- [ ] Create the Jira ticket on escalation
- [ ] Expose the tools as an MCP server so engineers can ask "who owns this?" from their editor
