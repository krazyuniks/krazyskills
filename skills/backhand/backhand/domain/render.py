"""Pure rendering: Handoff -> markdown. No I/O."""

from __future__ import annotations

import yaml

from .models import Handoff, ThreadItem


def _front_matter_yaml(handoff: Handoff) -> str:
    data = handoff.front_matter.model_dump(mode="json", exclude_none=True)
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False).strip()


def _thread_line(item: ThreadItem) -> str:
    line = f"- [{item.kind.value}] {item.statement}"
    if item.rationale:
        line += f" - why: {item.rationale}"
    if item.status:
        line += f" ({item.status})"
    return line


def render(handoff: Handoff) -> str:
    """Serialise a Handoff to the three-zone markdown document."""
    parts = [
        "---",
        _front_matter_yaml(handoff),
        "---",
        "",
        "## Intent (verbatim)",
        "",
        handoff.intent.strip() or "_(none captured)_",
        "",
        "## Thread (itemised)",
        "",
    ]
    if handoff.thread:
        parts.extend(_thread_line(i) for i in handoff.thread)
    else:
        parts.append("_(none captured)_")
    parts += ["", "## State", "", handoff.state.strip() or "_(none captured)_", ""]
    return "\n".join(parts)
