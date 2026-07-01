"""Configuration."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BackendName = Literal["subagent", "tmux", "api"]


class Config(BaseModel):
    """Runtime configuration, optionally loaded from ~/.backhand/config.toml."""

    model_config = ConfigDict(extra="forbid")

    storage_dir: Path = Field(default_factory=lambda: Path("~/.backhand/handoffs").expanduser())
    default_profile: str | None = None
    backend: BackendName = "tmux"
    tmux_dispatch_path: str | None = None
    tmux_harness: str = "codex"
    tmux_effort: str | None = None
    tmux_timeout_s: int = Field(default=900, ge=30)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        config_path = path or Path("~/.backhand/config.toml").expanduser()
        if not config_path.exists():
            return cls()
        with config_path.open("rb") as fh:
            return cls.model_validate(tomllib.load(fh))

    @field_validator("storage_dir", mode="before")
    @classmethod
    def expand_storage_dir(cls, value: object) -> Path:
        if isinstance(value, Path):
            return value.expanduser()
        return Path(os.path.expanduser(str(value)))
