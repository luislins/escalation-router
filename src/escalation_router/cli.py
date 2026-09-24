"""Route a bug report from the terminal, without Slack.

escalation-router "Donor says the receipt PDF has the wrong total"
echo "..." | escalation-router -
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import build_router


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Suggest which team should own a bug report.")
    parser.add_argument("report", help="Bug report text, or '-' to read from stdin")
    parser.add_argument("--trace", action="store_true", help="Also print the tool calls the agent made")
    args = parser.parse_args(argv)

    report = sys.stdin.read() if args.report == "-" else args.report
    result = build_router().route(report)
    output = result.decision.model_dump()
    if args.trace:
        output["tool_calls"] = result.tool_calls
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
