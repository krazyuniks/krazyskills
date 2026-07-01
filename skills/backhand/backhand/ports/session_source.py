"""Port: locate and read the current session, extract head/tail + metadata."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ResolvedSession(BaseModel):
    """What a SessionSource returns: verbatim head/tail plus metadata and a transcript path."""

    tool: str
    session_ref: str | None = None  # path/id of the session transcript (for front-matter)
    transcript_path: str | None = None  # a file the summariser backend can read for the middle
    cwd: str | None = None
    git_branch: str | None = None
    git_head: str | None = None
    model: str | None = None
    title: str | None = None
    head: str  # verbatim first user prompt
    tail: str  # near-verbatim tail


class SessionSource(ABC):
    """Adapter for one agent tool's session store (Claude JSONL, Codex, Pi, Gemini)."""

    tool: str = "unknown"

    @abstractmethod
    def resolve(self, first_prompt_hint: str | None = None) -> ResolvedSession:
        """Find the current session and return its head, tail, and metadata.

        `first_prompt_hint` disambiguates the current session among many by matching its
        first user message.
        """
        raise NotImplementedError
