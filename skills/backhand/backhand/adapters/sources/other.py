"""Session-source stubs for the remaining tools. Same port, not yet implemented.

Each documents where that tool keeps its sessions, so the implementation is a fill-in.
"""

from __future__ import annotations

from ...ports.session_source import ResolvedSession, SessionSource


class CodexSource(SessionSource):
    tool = "codex"

    def resolve(self, first_prompt_hint: str | None = None) -> ResolvedSession:
        raise NotImplementedError(
            "Codex session source not implemented. Codex stores sessions in "
            "~/.codex (history.jsonl + state_*.sqlite)."
        )


class PiSource(SessionSource):
    tool = "pi"

    def resolve(self, first_prompt_hint: str | None = None) -> ResolvedSession:
        raise NotImplementedError(
            "Pi session source not implemented. Pi stores sessions under ~/.pi/agent/sessions."
        )


class GeminiSource(SessionSource):
    tool = "gemini"

    def resolve(self, first_prompt_hint: str | None = None) -> ResolvedSession:
        raise NotImplementedError("Gemini session source not implemented.")
