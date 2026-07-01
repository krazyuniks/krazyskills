"""Pydantic domain models for a handoff document. Pure data - no I/O."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ItemKind(StrEnum):
    """The type of a middle-zone item. Typing preserves distinctness under compression."""

    decision = "decision"
    pivot = "pivot"
    rejected = "rejected"
    design_point = "design-point"
    open = "open"
    constraint = "constraint"


class ThreadItem(BaseModel):
    """One itemised point in the middle zone - condensed but never merged into a blob."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ItemKind
    statement: str = Field(min_length=1)
    rationale: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, min_length=1)


class ThreadSummary(BaseModel):
    """Structured summariser response from model-backed adapters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[ThreadItem] = Field(default_factory=list)


class FrontMatter(BaseModel):
    """Metadata header. `session_ref` links back to the full, lossless transcript."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["handoff"] = "handoff"
    tool: str
    created: datetime
    cwd: str | None = None
    git_branch: str | None = None
    git_head: str | None = None
    model: str | None = None
    session_ref: str | None = None
    next_focus: str | None = None
    supersedes: str | None = None
    title: str | None = None


class Handoff(BaseModel):
    """The whole three-zone document: head (verbatim), middle (itemised), tail (near-verbatim)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    front_matter: FrontMatter
    intent: str  # head - verbatim first prompt
    thread: list[ThreadItem] = Field(default_factory=list)  # middle
    state: str  # tail - near-verbatim stopping point
