"""Application service: orchestrate a handoff end to end.

resolve session -> extract head/tail + metadata -> summarise the middle -> assemble -> render
-> write. The service depends only on the ports, never on a concrete adapter.
"""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ..config import Config
from ..domain.models import FrontMatter, Handoff
from ..domain.render import render
from ..ports.session_source import SessionSource
from ..ports.summariser import SummariserBackend


def _git(cwd: str | None, *args: str) -> str | None:
    if not cwd:
        return None
    try:
        out = subprocess.run(
            ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


class HandoffService:
    def __init__(
        self, source: SessionSource, summariser: SummariserBackend, config: Config
    ) -> None:
        self.source = source
        self.summariser = summariser
        self.config = config

    def build(
        self,
        *,
        focus: str | None,
        first_prompt_hint: str | None = None,
        profile: str | None = None,
        now: datetime | None = None,
    ) -> Handoff:
        session = self.source.resolve(first_prompt_hint=first_prompt_hint)
        transcript_path = session.transcript_path or session.session_ref
        if not transcript_path:
            raise RuntimeError(f"{session.tool} source did not provide a transcript path")
        thread = self.summariser.summarise_middle(
            transcript_path,
            profile=profile or self.config.default_profile,
        )
        fm = FrontMatter(
            tool=session.tool,
            created=now or datetime.now(UTC),
            cwd=session.cwd,
            git_branch=session.git_branch
            or _git(session.cwd, "rev-parse", "--abbrev-ref", "HEAD"),
            git_head=session.git_head or _git(session.cwd, "rev-parse", "--short", "HEAD"),
            model=session.model,
            session_ref=session.session_ref,
            next_focus=focus,
            title=session.title,
        )
        return Handoff(
            front_matter=fm, intent=session.head, thread=thread, state=session.tail
        )

    def write(self, handoff: Handoff, now: datetime | None = None) -> Path:
        now = now or datetime.now(UTC)
        self.config.storage_dir.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        label = _filename_label(handoff.front_matter.title)
        path = self.config.storage_dir / f"{stamp}-{label}.md"
        path.write_text(render(handoff), encoding="utf-8")
        return path


def _filename_label(title: str | None) -> str:
    if not title:
        return "session"
    label = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return label or "session"
