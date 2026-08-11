"""herdr backend: dispatch the middle-synthesis to a chosen harness via harness-dispatch.

Thin adapter over the `harness-dispatch` CLI provided by the herdr-harness skill - backhand does
not reimplement herdr orchestration. The command is resolved from explicit config, the
`BACKHAND_HARNESS_DISPATCH` environment variable, or `PATH`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from ...domain.models import ItemKind, ThreadItem, ThreadSummary
from ...ports.summariser import SummariserBackend
from ..sources.claude_jsonl import compact_middle_text

MAX_MIDDLE_CHARS = 120_000


class Runner(Protocol):
    def __call__(
        self,
        args: Sequence[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]: ...


def find_harness_dispatch(explicit_path: str | None = None) -> str | None:
    for candidate in (explicit_path, os.environ.get("BACKHAND_HARNESS_DISPATCH")):
        if candidate:
            expanded = os.path.expanduser(candidate)
            if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
                return expanded
    which = shutil.which("harness-dispatch")
    if which:
        return which
    for path_dir in os.get_exec_path():
        candidate = os.path.join(path_dir, "harness-dispatch")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


class HerdrBackend(SummariserBackend):
    name = "herdr"

    def __init__(
        self,
        *,
        dispatch_path: str | None = None,
        harness: str = "codex",
        effort: str | None = None,
        timeout_s: int = 900,
        runner: Runner = subprocess.run,
    ) -> None:
        self.dispatch_path = dispatch_path
        self.harness = harness
        self.effort = effort
        self.timeout_s = timeout_s
        self.runner = runner

    def summarise_middle(
        self, transcript_path: str, *, profile: str | None = None
    ) -> list[ThreadItem]:
        dispatch = find_harness_dispatch(self.dispatch_path)
        if dispatch is None:
            raise RuntimeError(
                "harness-dispatch not found. Install a compatible herdr-harness provider, set "
                "BACKHAND_HARNESS_DISPATCH, or pass --harness-dispatch-path."
            )
        transcript = Path(transcript_path).expanduser()
        if not transcript.exists():
            raise FileNotFoundError(f"Transcript not found: {transcript}")

        with tempfile.TemporaryDirectory(prefix="backhand-herdr-") as tmp:
            prompt_path = Path(tmp) / "middle-synthesis.md"
            prompt_path.write_text(_prompt(transcript), encoding="utf-8")
            args = [
                dispatch,
                "--harness",
                self.harness,
                "--prompt-file",
                str(prompt_path),
                "--timeout",
                str(self.timeout_s),
            ]
            if profile:
                args.extend(["--model", profile])
            if self.effort:
                args.extend(["--effort", self.effort])

            completed = self.runner(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout_s + 30,
            )

        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise RuntimeError(f"harness-dispatch failed: {stderr or 'no stderr'}")

        return _parse_summary(completed.stdout)


def _bounded_middle(transcript_path: Path) -> str:
    middle = compact_middle_text(transcript_path)
    if len(middle) <= MAX_MIDDLE_CHARS:
        return middle
    omitted = len(middle) - MAX_MIDDLE_CHARS
    return (
        middle[:MAX_MIDDLE_CHARS]
        + f"\n\n[backhand omitted {omitted} characters from the middle excerpt. "
        "Use the linked transcript for lossless detail.]"
    )


def _prompt(transcript_path: Path) -> str:
    kinds = ", ".join(kind.value for kind in ItemKind)
    middle = _bounded_middle(transcript_path)
    if not middle.strip():
        middle = "(No middle excerpt captured.)"
    return f"""Summarise this middle excerpt from an agent transcript:

```text
{middle}
```

Return only a JSON object with this shape:
{{"items":[{{"kind":"decision","statement":"...","rationale":null,"status":null}}]}}

Allowed kind values: {kinds}.

Capture decisions, pivots, rejected options, constraints, design points, and open items. The
original intent and stopping state are already excluded because backhand copies those
deterministically. Keep each item concrete, do not merge unrelated points, and do not add Markdown
fences or commentary.
"""


def _parse_summary(output: str) -> list[ThreadItem]:
    try:
        body = _extract_json_object(_strip_json_fence(output.strip()))
        payload = json.loads(body)
        return ThreadSummary.model_validate(payload).items
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ValueError("harness-dispatch returned invalid backhand summary JSON") from exc


def _strip_json_fence(output: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", output, flags=re.DOTALL)
    if match:
        return match.group(1)
    return output


def _extract_json_object(output: str) -> str:
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        return output[index : index + end]
    raise ValueError("harness-dispatch returned no JSON object")
