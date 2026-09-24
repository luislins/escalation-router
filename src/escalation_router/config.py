"""Build the router from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from .agent import AgentRouter
from .knowledge import EscalationHistory, OnCallSchedule, OwnershipCatalog
from .router import EscalationRouter, RouterConfig, SingleCallRouter
from .tools import Toolbox

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "demo"


def data_dir() -> Path:
    return Path(os.environ.get("ROUTER_DATA_DIR", DEFAULT_DATA_DIR))


def build_toolbox(directory: Path | None = None) -> Toolbox:
    directory = directory or data_dir()
    return Toolbox(
        catalog=OwnershipCatalog.from_yaml(directory / "ownership.yaml"),
        oncall=OnCallSchedule.from_yaml(directory / "oncall.yaml"),
        history=EscalationHistory.from_jsonl(directory / "history.jsonl"),
    )


ROUTERS = {"single": SingleCallRouter, "agent": AgentRouter}


def build_router(client=None, mode: str | None = None) -> EscalationRouter:
    """ROUTER_MODE=single (default, one model call) or agent (Claude chooses the lookups)."""
    mode = mode or os.environ.get("ROUTER_MODE", "single")
    if mode not in ROUTERS:
        raise ValueError(f"ROUTER_MODE must be one of {', '.join(ROUTERS)}, got '{mode}'")
    config = RouterConfig(
        model=os.environ.get("ROUTER_MODEL", RouterConfig.model),
        effort=os.environ.get("ROUTER_EFFORT", RouterConfig.effort),
        confidence_threshold=float(
            os.environ.get("ROUTER_CONFIDENCE_THRESHOLD", RouterConfig.confidence_threshold)
        ),
        use_fallbacks=os.environ.get("ROUTER_USE_FALLBACKS", "true").lower() == "true",
    )
    return ROUTERS[mode](build_toolbox(), client=client, config=config)
