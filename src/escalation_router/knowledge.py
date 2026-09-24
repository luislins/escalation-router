"""The sources the agent can consult: ownership catalog, on-call rotation and
past escalations. Each is a small class so a real deployment can swap the YAML
and JSONL files for Backstage, PagerDuty, Jira and so on.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from collections import Counter
from pathlib import Path

import yaml

from .models import PastEscalation, Team

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "i",
    "in",
    "is",
    "it",
    "its",
    "not",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "when",
    "with",
    "after",
    "they",
    "we",
    "can",
    "cannot",
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class OwnershipCatalog:
    def __init__(self, teams: list[Team], fallback_team: str):
        self.teams = {t.id: t for t in teams}
        if fallback_team not in self.teams:
            raise ValueError(f"fallback_team '{fallback_team}' is not a known team")
        self.fallback_team = fallback_team

    @classmethod
    def from_yaml(cls, path: str | Path) -> OwnershipCatalog:
        data = yaml.safe_load(Path(path).read_text())
        return cls([Team(**t) for t in data["teams"]], data["fallback_team"])

    def get(self, team_id: str) -> Team | None:
        return self.teams.get(team_id)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Rank product areas by how many of their keywords appear in the query."""
        text = " ".join(tokenize(query))
        tokens = set(text.split())
        hits = []
        for team in self.teams.values():
            for area in team.areas:
                matched = [
                    kw
                    for kw in area.keywords
                    if (" " in kw and " ".join(tokenize(kw)) in text) or kw.lower() in tokens
                ]
                matched += [s for s in area.services if s in tokens]
                if matched:
                    hits.append(
                        {
                            "team_id": team.id,
                            "team_name": team.name,
                            "area": area.name,
                            "matched_keywords": matched,
                            "score": len(matched),
                        }
                    )
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:limit]


class OnCallSchedule:
    def __init__(self, rotations: dict[str, list[str]]):
        self.rotations = rotations

    @classmethod
    def from_yaml(cls, path: str | Path) -> OnCallSchedule:
        return cls(yaml.safe_load(Path(path).read_text())["rotations"])

    def current(self, team_id: str, today: dt.date | None = None) -> str | None:
        people = self.rotations.get(team_id)
        if not people:
            return None
        week = (today or dt.date.today()).isocalendar().week
        return people[week % len(people)]


class EscalationHistory:
    """Past escalations with a small TF-IDF search, good enough for a few thousand rows."""

    def __init__(self, items: list[PastEscalation]):
        self.items = items
        self._docs = [Counter(tokenize(f"{i.summary} {i.resolution or ''}")) for i in items]
        df: Counter[str] = Counter()
        for doc in self._docs:
            df.update(doc.keys())
        n = max(len(items), 1)
        self._idf = {term: math.log((n + 1) / (count + 1)) + 1 for term, count in df.items()}

    @classmethod
    def from_jsonl(cls, path: str | Path) -> EscalationHistory:
        lines = Path(path).read_text().splitlines()
        return cls([PastEscalation(**json.loads(line)) for line in lines if line.strip()])

    def search(self, query: str, limit: int = 5) -> list[dict]:
        terms = tokenize(query)
        scored = []
        for item, doc in zip(self.items, self._docs, strict=True):
            score = sum(doc[t] * self._idf.get(t, 0) for t in terms)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [{**item.model_dump(), "score": round(score, 2)} for score, item in scored[:limit]]
