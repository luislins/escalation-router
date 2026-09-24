"""Measure routing accuracy on labeled cases, per approach.

    python evals/run_eval.py --mode baseline      # keyword matching only, free
    python evals/run_eval.py                      # single model call (default), needs ANTHROPIC_API_KEY
    python evals/run_eval.py --mode agent         # tool-use agent, needs ANTHROPIC_API_KEY
    python evals/run_eval.py path/to/cases.jsonl  # your own cases

Top-1: the answer is the expected team.
Top-3: the expected team is the answer or one of the first two alternatives.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from escalation_router.config import build_router, build_toolbox
from escalation_router.router import RoutingError

DEFAULT_CASES = Path(__file__).with_name("cases.jsonl")


def evaluate(case: dict, router) -> dict:
    start = time.perf_counter()
    try:
        result = router.route(case["report"])
    except RoutingError as exc:
        return {**case, "predicted": f"error: {exc}", "top1": False, "top3": False, "calls": 0, "seconds": 0}
    decision = result.decision
    ranked = [decision.team_id, *decision.alternative_team_ids][:3]
    return {
        **case,
        "predicted": decision.team_id,
        "top1": decision.team_id == case["expected_team"],
        "top3": case["expected_team"] in ranked,
        "calls": result.model_calls,
        "seconds": time.perf_counter() - start,
    }


def evaluate_baseline(case: dict, catalog) -> dict:
    """What you get from keyword matching alone: the bar a model has to beat."""
    ranked = list(dict.fromkeys(h["team_id"] for h in catalog.search(case["report"])))
    predicted = ranked[0] if ranked else catalog.fallback_team
    return {
        **case,
        "predicted": predicted,
        "top1": predicted == case["expected_team"],
        "top3": case["expected_team"] in (ranked[:3] or [predicted]),
        "calls": 0,
        "seconds": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", nargs="?", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--mode", choices=["baseline", "single", "agent"], default="single")
    parser.add_argument("--baseline", action="store_true", help="Same as --mode baseline")
    args = parser.parse_args()
    mode = "baseline" if args.baseline else args.mode

    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    if mode == "baseline":
        catalog = build_toolbox().catalog
        results = [evaluate_baseline(c, catalog) for c in cases]
    else:
        router = build_router(mode=mode)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda c: evaluate(c, router), cases))

    for r in results:
        mark = "ok  " if r["top1"] else "MISS"
        print(f"{mark} expected={r['expected_team']:<20} got={r['predicted']:<20} {r['report'][:60]}")
    n = len(results)
    top1 = sum(r["top1"] for r in results)
    top3 = sum(r["top3"] for r in results)
    print(f"\nmode: {mode}")
    print(f"top-1: {top1}/{n} ({top1 / n:.0%})")
    print(f"top-3: {top3}/{n} ({top3 / n:.0%})")
    if mode != "baseline":
        print(f"model calls per report: {statistics.mean(r['calls'] for r in results):.1f}")
        print(f"median seconds per report: {statistics.median(r['seconds'] for r in results):.1f}")


if __name__ == "__main__":
    main()
