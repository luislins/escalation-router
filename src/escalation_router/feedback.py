"""Record what humans did with each suggestion. Corrections become eval cases."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path


def feedback_path() -> Path:
    return Path(os.environ.get("ROUTER_FEEDBACK_FILE", "feedback.jsonl"))


def record(reference: str, suggested_team: str, final_team: str, user: str, path: Path | None = None) -> None:
    entry = {
        "at": dt.datetime.now(dt.UTC).isoformat(),
        "reference": reference,
        "suggested_team": suggested_team,
        "final_team": final_team,
        "accepted": suggested_team == final_team,
        "user": user,
    }
    with (path or feedback_path()).open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
