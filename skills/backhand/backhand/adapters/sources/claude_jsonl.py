"""Claude Code session source.

Reads ~/.claude/projects/<slug>/<session-id>.jsonl, where <slug> is the cwd with path
separators replaced by '-'. Resolves the current session by matching the first user prompt
(mtime as tiebreak), then extracts the verbatim head, a near-verbatim tail, and metadata.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...ports.session_source import ResolvedSession, SessionSource

TAIL_MESSAGES = 24
TOOL_TRACE_CHARS = 800


def _slug(cwd: str) -> str:
    return cwd.replace("/", "-")


def _compact(value: str, limit: int = TOOL_TRACE_CHARS) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _jsonish(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return str(value)


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for block in content:
            if isinstance(block, str):
                out.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    out.append(str(block.get("text", "")))
                elif "content" in block:
                    out.append(_content_text(block.get("content")))
        return "\n".join(t for t in out if t)
    if isinstance(content, dict):
        return _content_text(content.get("content", ""))
    return ""


def _tool_use_text(block: dict[str, Any]) -> str:
    name = str(block.get("name") or "tool")
    tool_input = block.get("input")
    if isinstance(tool_input, dict):
        for key in ("command", "cmd", "query", "pattern", "path", "file_path", "prompt"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                return f"[tool_use:{name}] {key}: {_compact(value)}"
    if tool_input:
        return f"[tool_use:{name}] {_compact(_jsonish(tool_input))}"
    return f"[tool_use:{name}]"


def _tool_result_text(block: dict[str, Any]) -> str:
    content = _content_text(block.get("content", ""))
    if content.strip():
        return f"[tool_result] {_compact(content)}"
    return "[tool_result]"


def _text(message: object, *, include_tool_traces: bool = False) -> str:
    """Flatten a message's content to plain text plus optional compact tool traces."""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            out: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    out.append(block.get("text", ""))
                elif include_tool_traces and isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        out.append(_tool_use_text(block))
                    elif block.get("type") == "tool_result":
                        out.append(_tool_result_text(block))
                elif isinstance(block, str):
                    out.append(block)
            return "\n".join(t for t in out if t)
    return ""


def _is_command_wrapper(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("<command-name>") or stripped.startswith("<local-command-")


def compact_middle_text(path: Path, *, tail_messages: int = TAIL_MESSAGES) -> str:
    """Return a model-safe middle excerpt from a Claude JSONL transcript.

    The excerpt drops command-wrapper turns, the first substantive user turn, the tail already
    copied by the source adapter, and verbose tool results. It keeps compact tool-use traces because
    commands often carry the useful transition detail without the full output blob.
    """
    events: list[tuple[str, str]] = []
    first_user_seen = False
    for rec in _iter_records(path):
        rtype = rec.get("type")
        if rtype not in ("user", "assistant"):
            continue
        if rec.get("isMeta") or rec.get("isSidechain"):
            continue
        text = _text(rec.get("message"), include_tool_traces=True)
        if not text.strip() or _is_command_wrapper(text):
            continue
        if rtype == "user" and not first_user_seen:
            first_user_seen = True
            continue
        if "[tool_result]" in text and not any(
            line.strip() != "[tool_result]" for line in text.splitlines()
        ):
            continue
        text_lines = [line for line in text.splitlines() if not line.startswith("[tool_result]")]
        if text_lines:
            events.append((str(rtype), "\n".join(text_lines)))

    middle = events[:-tail_messages] if tail_messages else events
    return "\n\n".join(f"{rtype}: {text}" for rtype, text in middle)


class ClaudeJsonlSource(SessionSource):
    tool = "claude-code"

    def __init__(self, cwd: str | None = None, projects_dir: str | None = None) -> None:
        self.cwd = cwd or os.getcwd()
        self.projects_dir = Path(projects_dir or os.path.expanduser("~/.claude/projects"))

    def _candidates(self) -> list[Path]:
        slug_dir = self.projects_dir / _slug(self.cwd)
        if not slug_dir.is_dir():
            return []
        return sorted(slug_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

    def _first_user_text(self, path: Path) -> str:
        for rec in _iter_records(path):
            if rec.get("type") == "user" and not rec.get("isMeta") and not rec.get("isSidechain"):
                text = _text(rec.get("message"))
                if text.strip() and not _is_command_wrapper(text):
                    return text
        return ""

    def _pick(self, first_prompt_hint: str | None) -> Path | None:
        candidates = self._candidates()
        if not candidates:
            return None
        if first_prompt_hint:
            needle = first_prompt_hint.strip()[:120]
            if needle:
                for path in candidates:
                    if needle in self._first_user_text(path):
                        return path
        return candidates[0]  # most recently modified

    def resolve(self, first_prompt_hint: str | None = None) -> ResolvedSession:
        path = self._pick(first_prompt_hint)
        if path is None:
            raise FileNotFoundError(f"No Claude session transcript found for cwd {self.cwd}")

        head = ""
        tail_msgs: list[str] = []
        cwd = self.cwd
        git_branch: str | None = None
        model: str | None = None
        title: str | None = None

        for rec in _iter_records(path):
            rtype = rec.get("type")
            if rtype == "ai-title":
                title = rec.get("aiTitle") or title
                continue
            if rtype not in ("user", "assistant"):
                continue
            if rec.get("isMeta") or rec.get("isSidechain"):
                continue
            cwd = rec.get("cwd", cwd)
            git_branch = rec.get("gitBranch", git_branch)
            message = rec.get("message")
            if rtype == "assistant" and model is None and isinstance(message, dict):
                model = message.get("model")
            text = _text(message, include_tool_traces=True)
            if not text.strip():
                continue
            if _is_command_wrapper(text):
                continue
            if rtype == "user" and not head:
                head = text
            tail_msgs.append(f"**{rtype}:** {text}")

        return ResolvedSession(
            tool=self.tool,
            session_ref=str(path),
            transcript_path=str(path),
            cwd=cwd,
            git_branch=git_branch,
            model=model,
            title=title,
            head=head,
            tail="\n\n".join(tail_msgs[-TAIL_MESSAGES:]),
        )


def _iter_records(path: Path):
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
