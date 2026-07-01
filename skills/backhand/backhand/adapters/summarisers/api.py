"""API backend.

Calls a metered model API for users who explicitly choose that path. Kept behind the same port as
the local backends so the CLI can expose it without changing the domain model.
"""

from __future__ import annotations

from ...domain.models import ThreadItem
from ...ports.summariser import SummariserBackend


class ApiBackend(SummariserBackend):
    name = "api"

    def summarise_middle(
        self, transcript_path: str, *, profile: str | None = None
    ) -> list[ThreadItem]:
        raise NotImplementedError(
            "ApiBackend calls a metered model API. Not implemented yet."
        )
