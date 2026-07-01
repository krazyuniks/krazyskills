"""In-session subagent backend.

Usable only when backhand runs as a skill inside a host agent session that can spawn
subagents (Claude Code). The orchestrating session spawns a summariser subagent with the
chosen model, gives it the transcript path, and it returns the typed middle items. This class
documents the contract; the actual spawn is driven by the host session via the SKILL.md, so
it is not callable from a standalone process.
"""

from __future__ import annotations

from ...domain.models import ThreadItem
from ...ports.summariser import SummariserBackend


class SubagentBackend(SummariserBackend):
    name = "subagent"

    def summarise_middle(
        self, transcript_path: str, *, profile: str | None = None
    ) -> list[ThreadItem]:
        raise NotImplementedError(
            "The subagent backend is driven by the host Claude session, which spawns a "
            "summariser subagent (model=profile) to read the transcript and return items. "
            "It is not callable from a standalone process; use the tmux or api backend for that."
        )
