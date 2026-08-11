"""Port: turn a transcript into the itemised middle zone."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import ThreadItem


class SummariserBackend(ABC):
    """Produces the typed middle-zone items. Implementations: subagent, herdr, api."""

    name: str = "unknown"

    @abstractmethod
    def summarise_middle(
        self, transcript_path: str, *, profile: str | None = None
    ) -> list[ThreadItem]:
        """Read the transcript and return typed thread items for the middle zone."""
        raise NotImplementedError
