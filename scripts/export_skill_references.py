"""Generate the Claude skill's reference files from the router's data files.

The skill and the router read the same ownership catalog, on-call rotation and escalation
history, so they never disagree. Re-run this whenever the data changes, and at least before
the on-call table expires.

    python scripts/export_skill_references.py                      # demo data
    ROUTER_DATA_DIR=~/router-data python scripts/export_skill_references.py --weeks 12
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections import defaultdict
from pathlib import Path

from escalation_router.config import build_toolbox

OUT = Path(__file__).resolve().parents[1] / "skill" / "escalation-router" / "references"


def teams_md(toolbox) -> str:
    catalog = toolbox.catalog
    lines = [
        "# Teams and what they own",
        "",
        f"Triage team when nothing fits or confidence is low: `{catalog.fallback_team}`.",
        "",
    ]
    for team in catalog.teams.values():
        lines += [f"## {team.name} (`{team.id}`)", "", f"Slack channel: {team.slack_channel}", ""]
        if team.description:
            lines += [team.description, ""]
        for area in team.areas:
            lines.append(f"- **{area.name}**: {', '.join(area.keywords)}")
            if area.services:
                lines.append(f"  - services: {', '.join(area.services)}")
        lines.append("")
    return "\n".join(lines)


def oncall_md(toolbox, start: dt.date, weeks: int) -> str:
    monday = start - dt.timedelta(days=start.weekday())
    until = monday + dt.timedelta(weeks=weeks, days=-1)
    teams = list(toolbox.catalog.teams.values())
    lines = [
        "# On-call by week",
        "",
        f"Generated {start.isoformat()}. **Valid until {until.isoformat()}.** After that date this table is",
        "stale: do not guess who is on call, say the table expired and point to the team's channel.",
        "",
        "Weeks run Monday to Sunday.",
        "",
        "| Week | " + " | ".join(t.name for t in teams) + " |",
        "| --- | " + " | ".join("---" for _ in teams) + " |",
    ]
    for i in range(weeks):
        week_start = monday + dt.timedelta(weeks=i)
        week_end = week_start + dt.timedelta(days=6)
        people = [toolbox.oncall.current(t.id, week_start) or "-" for t in teams]
        lines.append(f"| {week_start.isoformat()} to {week_end.isoformat()} | " + " | ".join(people) + " |")
    return "\n".join(lines) + "\n"


def history_md(toolbox) -> str:
    by_team = defaultdict(list)
    for item in toolbox.history.items:
        by_team[item.team].append(item)
    lines = [
        "# Past escalations",
        "",
        "Bugs that were escalated before, grouped by the team that fixed them. The people listed",
        'under "resolved by" are the only names you may give as "fixed similar bugs".',
        "",
    ]
    for team in toolbox.catalog.teams.values():
        items = by_team.get(team.id)
        if not items:
            continue
        lines += [f"## {team.name} (`{team.id}`)", ""]
        for i in items:
            who = f" — resolved by {i.resolved_by}" if i.resolved_by else ""
            cause = f" Root cause: {i.resolution}" if i.resolution else ""
            lines.append(f"- **{i.id}**: {i.summary}{who}.{cause}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=8, help="How many weeks of on-call to include")
    parser.add_argument("--start", type=dt.date.fromisoformat, default=dt.date.today())
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    toolbox = build_toolbox()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "teams.md").write_text(teams_md(toolbox))
    (args.out / "oncall.md").write_text(oncall_md(toolbox, args.start, args.weeks))
    (args.out / "past-escalations.md").write_text(history_md(toolbox))
    print(f"Wrote teams.md, oncall.md, past-escalations.md to {args.out}")


if __name__ == "__main__":
    main()
