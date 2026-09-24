"""Agent mode (ROUTER_MODE=agent): a tool-use loop where Claude picks what to look up,
ending when it calls submit_routing.

Not the default. With the current knowledge sources every lookup can be done up front in code
(see SingleCallRouter), which is faster and cheaper. This mode earns its place once investigation
becomes open-ended, e.g. following a stack trace into code owners and recent commits.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from .redaction import redact
from .router import GUIDELINES, EscalationRouter, RoutingError, RoutingResult
from .tools import SUBMIT_TOOL, TOOL_DEFINITIONS, ToolError

log = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""\
You route bug reports written by customer support agents to the engineering team that owns the problem.

{GUIDELINES}

Search the ownership catalog and past escalations before deciding, then finish by calling \
submit_routing exactly once.
"""

MAX_TURNS = 10


class AgentRouter(EscalationRouter):
    def route(self, report: str) -> RoutingResult:
        report = redact(report)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": f"<bug_report>\n{report}\n</bug_report>"}
        ]
        tool_calls: list[dict[str, Any]] = []

        for turn in range(1, MAX_TURNS + 1):
            response = self._call_model(system=SYSTEM_PROMPT, tools=TOOL_DEFINITIONS, messages=messages)
            messages.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Please finish by calling {SUBMIT_TOOL} with your decision.",
                    }
                )
                continue

            results = []
            decision = None
            for block in tool_uses:
                tool_calls.append({"name": block.name, "input": block.input})
                try:
                    if block.name == SUBMIT_TOOL:
                        decision = self._finalize(block.input, report)
                        content = "Decision recorded."
                    else:
                        content = self.toolbox.run(block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
                except (ToolError, ValidationError, TypeError, KeyError) as exc:
                    log.info("tool %s failed: %s", block.name, exc)
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {exc}",
                            "is_error": True,
                        }
                    )

            if decision is not None:
                return RoutingResult(decision=decision, tool_calls=tool_calls, model_calls=turn)
            messages.append({"role": "user", "content": results})

        raise RoutingError(f"No decision after {MAX_TURNS} turns.")
