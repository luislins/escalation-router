"""Check skill replies against evals.json. Usage: python skill/evals/grade.py <iteration dir>"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from escalation_router.config import build_toolbox

EVALS = json.loads(Path(__file__).with_name("evals.json").read_text())
toolbox = build_toolbox()
KNOWN_PEOPLE = {p for people in toolbox.oncall.rotations.values() for p in people}
KNOWN_PEOPLE |= {i.resolved_by for i in toolbox.history.items if i.resolved_by}


def line(reply: str, label: str) -> str:
    m = re.search(rf"\*{label}:\*\s*(.+)", reply)
    return m.group(1).strip() if m else ""


def check(case: dict, reply: str) -> list[dict]:
    a = case["assertions"]
    results = []

    def add(text, passed, evidence):
        results.append({"text": text, "passed": bool(passed), "evidence": evidence})

    add(
        "No @mentions or Slack user links",
        not re.search(r"<@|(?<!\w)@\w", reply),
        "searched for <@ and @name",
    )
    add(
        "No email or phone repeated",
        not re.search(r"@gmail|\d{5}-\d{4}", reply),
        "searched for the donor's email/phone",
    )
    # A capitalized "First Last" whose first name is a known person's, but that isn't a known person.
    first_names = {p.split()[0] for p in KNOWN_PEOPLE}
    names = set(re.findall(r"\b[A-Z][a-zé]+ [A-Z][a-z]+\b", reply))
    invented = [n for n in names if n.split()[0] in first_names and n not in KNOWN_PEOPLE]
    add("Only names from the reference files", not invented, f"unknown person names: {invented}")
    if "team" in a:
        add(
            f"Team is {a['team']}",
            a["team"] in line(reply, "Team") or a["team"] in line(reply, "Time"),
            line(reply, "Team") or line(reply, "Time"),
        )
    if "on_call" in a:
        oncall = line(reply, "On call") or line(reply, "Plantão") or reply
        add(f"On call is {a['on_call']}", a["on_call"] in oncall, oncall)
    for person in a.get("experts_include", []):
        add(f"Mentions {person} as having fixed a similar bug", person in reply, "")
    if "experts_team" in a:
        allowed = {i.resolved_by for i in toolbox.history.items if i.team == a["experts_team"]}
        oncall_name = a.get("on_call")
        mentioned = [p for p in KNOWN_PEOPLE if p in reply and p != oncall_name]
        add(
            "Similar-bug people belong to the chosen team",
            all(p in allowed for p in mentioned),
            f"mentioned: {mentioned}",
        )
    if "confidence_not" in a:
        conf = line(reply, "Confidence") or line(reply, "Confiança")
        add(f"Confidence is not {a['confidence_not']}", a["confidence_not"] not in conf.lower(), conf)
    if a.get("asks_customer"):
        add("Says what to ask the customer", re.search(r"\*(Ask the customer|Pergunte)", reply), "")
    if a.get("language") == "pt":
        add("Replies in Portuguese", re.search(r"\b(não|recibo|reembolso|doadora)\b", reply), "")
    return results


def main() -> None:
    root = Path(sys.argv[1])
    total = passed = 0
    for case in EVALS["evals"]:
        run = root / f"eval-{case['name']}" / "with_skill"
        reply = (run / "outputs" / "reply.md").read_text()
        results = check(case, reply)
        (run / "grading.json").write_text(json.dumps({"expectations": results}, indent=2, ensure_ascii=False))
        print(f"\n== {case['name']}")
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            detail = "" if r["passed"] else r["evidence"]
            print(f"  {status}  {r['text']}  {detail}")
        total += len(results)
        passed += sum(r["passed"] for r in results)
    print(f"\n{passed}/{total} checks passed")


if __name__ == "__main__":
    main()
