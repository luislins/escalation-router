"""Measure routing accuracy on labeled cases. Needs ANTHROPIC_API_KEY and spends real tokens.

    python evals/run_eval.py                      # demo cases
    python evals/run_eval.py path/to/cases.jsonl  # your own (e.g. exported from feedback.jsonl)
    python evals/run_eval.py --baseline           # keyword-only baseline, no API calls

Top-1: the suggested team is the expected one.
Top-3: the expected team is the suggestion or one of the first two alternatives.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from escalation_router.agent import RoutingError
from escalation_router.config import build_router, build_toolbox

DEFAULT_CASES = Path(__file__).with_name("cases.jsonl")


def evaluate(case: dict, router) -> dict:
    try:
        decision = router.route(case["report"]).decision
    except RoutingError as exc:
        return {**case, "error": str(exc), "top1": False, "top3": False}
    ranked = [decision.team_id, *decision.alternative_team_ids][:3]
    return {
        **case,
        "predicted": decision.team_id,
        "confidence": decision.confidence,
        "top1": decision.team_id == case["expected_team"],
        "top3": case["expected_team"] in ranked,
    }


def evaluate_baseline(case: dict, catalog) -> dict:
    """What you get from keyword matching alone: the bar the agent has to beat."""
    ranked = list(dict.fromkeys(h["team_id"] for h in catalog.search(case["report"])))
    predicted = ranked[0] if ranked else catalog.fallback_team
    return {
        **case,
        "predicted": predicted,
        "top1": predicted == case["expected_team"],
        "top3": case["expected_team"] in (ranked[:3] or [predicted]),
    }


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else DEFAULT_CASES
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if "--baseline" in sys.argv:
        catalog = build_toolbox().catalog
        results = [evaluate_baseline(c, catalog) for c in cases]
    else:
        router = build_router()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda c: evaluate(c, router), cases))

    for r in results:
        mark = "ok  " if r["top1"] else "MISS"
        got = r.get("predicted", r.get("error"))
        print(f"{mark} expected={r['expected_team']:<20} got={got:<20} {r['report'][:60]}")
    n = len(results)
    print(f"\ntop-1: {sum(r['top1'] for r in results)}/{n} ({sum(r['top1'] for r in results) / n:.0%})")
    print(f"top-3: {sum(r['top3'] for r in results)}/{n} ({sum(r['top3'] for r in results) / n:.0%})")


if __name__ == "__main__":
    main()
