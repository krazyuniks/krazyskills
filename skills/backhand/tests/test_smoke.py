import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backhand import cli
from backhand.adapters.sources.claude_jsonl import ClaudeJsonlSource, compact_middle_text
from backhand.adapters.summarisers.api import ApiBackend
from backhand.adapters.summarisers.subagent import SubagentBackend
from backhand.adapters.summarisers.tmux import TmuxBackend, find_tmux_dispatch
from backhand.app.service import HandoffService
from backhand.config import Config
from backhand.domain.models import FrontMatter, Handoff, ItemKind, ThreadItem
from backhand.domain.render import render
from backhand.ports.session_source import ResolvedSession, SessionSource
from backhand.ports.summariser import SummariserBackend


def test_render_smoke() -> None:
    fm = FrontMatter(
        tool="claude-code",
        created=datetime(2026, 7, 1, tzinfo=UTC),
        title="Backhand handoff",
    )
    handoff = Handoff(
        front_matter=fm,
        intent="Design a session handoff tool.",
        thread=[
            ThreadItem(
                kind=ItemKind.decision,
                statement="Onion architecture with pluggable backends",
                rationale="cross-tool and public",
            ),
            ThreadItem(kind=ItemKind.rejected, statement="continuous logging via a hook"),
        ],
        state="Scaffolded; next implement the source adapter.",
    )
    out = render(handoff)
    assert out.startswith("---")
    assert "tool: claude-code" in out
    assert "## Intent (verbatim)" in out
    assert (
        "[decision] Onion architecture with pluggable backends - why: cross-tool and public" in out
    )
    assert "[rejected] continuous logging via a hook" in out
    assert "## State" in out


def test_claude_jsonl_source_extracts_head_tail_and_metadata(tmp_path: Path) -> None:
    cwd = "/tmp/backhand-demo"
    slug_dir = tmp_path / "-tmp-backhand-demo"
    slug_dir.mkdir()
    transcript = slug_dir / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                '{"type":"ai-title","aiTitle":"Demo handoff"}',
                '{"type":"user","cwd":"/tmp/backhand-demo","gitBranch":"main",'
                '"message":{"content":[{"type":"text","text":"First prompt"}]}}',
                '{"type":"assistant","cwd":"/tmp/backhand-demo","gitBranch":"main",'
                '"message":{"model":"claude-opus-4-8","content":[{"type":"text",'
                '"text":"Assistant reply"}]}}',
                '{"type":"user","isMeta":true,"message":{"content":"ignored"}}',
                '{"type":"user","cwd":"/tmp/backhand-demo","gitBranch":"main",'
                '"message":{"content":"Stopping point"}}',
            ]
        ),
        encoding="utf-8",
    )

    session = ClaudeJsonlSource(cwd=cwd, projects_dir=str(tmp_path)).resolve(
        first_prompt_hint="First"
    )

    assert session.session_ref == str(transcript)
    assert session.head == "First prompt"
    assert "Assistant reply" in session.tail
    assert "Stopping point" in session.tail
    assert "ignored" not in session.tail
    assert session.git_branch == "main"
    assert session.model == "claude-opus-4-8"
    assert session.title == "Demo handoff"


def test_claude_jsonl_source_skips_command_wrappers_for_head_and_hint(tmp_path: Path) -> None:
    cwd = "/tmp/backhand-demo"
    slug_dir = tmp_path / "-tmp-backhand-demo"
    slug_dir.mkdir()
    older = slug_dir / "older.jsonl"
    newer = slug_dir / "newer.jsonl"
    older.write_text(
        '{"type":"user","message":{"content":"Unrelated prompt"}}',
        encoding="utf-8",
    )
    newer.write_text(
        "\n".join(
            [
                '{"type":"user","message":{"content":"<command-name>/clear</command-name>\\n'
                '<command-message>clear</command-message>"}}',
                '{"type":"user","message":{"content":"Real handoff request"}}',
                '{"type":"assistant","message":{"content":"Working state"}}',
            ]
        ),
        encoding="utf-8",
    )

    session = ClaudeJsonlSource(cwd=cwd, projects_dir=str(tmp_path)).resolve(
        first_prompt_hint="Real handoff"
    )

    assert session.session_ref == str(newer)
    assert session.head == "Real handoff request"
    assert "/clear" not in session.tail


def test_claude_jsonl_tail_keeps_compact_tool_traces(tmp_path: Path) -> None:
    cwd = "/tmp/backhand-demo"
    slug_dir = tmp_path / "-tmp-backhand-demo"
    slug_dir.mkdir()
    transcript = slug_dir / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                '{"type":"user","message":{"content":"Build this"}}',
                '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash",'
                '"input":{"command":"git status --short"}}]}}',
                '{"type":"user","message":{"content":[{"type":"tool_result",'
                '"content":" M README.md\\n"}]}}',
            ]
        ),
        encoding="utf-8",
    )

    session = ClaudeJsonlSource(cwd=cwd, projects_dir=str(tmp_path)).resolve()

    assert "[tool_use:Bash] command: git status --short" in session.tail
    assert "[tool_result] M README.md" in session.tail


def test_service_keeps_focus_separate_from_session_resolution() -> None:
    class FakeSource(SessionSource):
        tool = "fake"

        def __init__(self) -> None:
            self.hint: str | None = None

        def resolve(self, first_prompt_hint: str | None = None) -> ResolvedSession:
            self.hint = first_prompt_hint
            return ResolvedSession(
                tool="fake",
                transcript_path="/tmp/transcript.jsonl",
                head="original ask",
                tail="current state",
            )

    class FakeSummariser(SummariserBackend):
        name = "fake"

        def summarise_middle(
            self, transcript_path: str, *, profile: str | None = None
        ) -> list[ThreadItem]:
            assert transcript_path == "/tmp/transcript.jsonl"
            assert profile == "strong-model"
            return [ThreadItem(kind=ItemKind.decision, statement="Keep the seam")]

    source = FakeSource()
    service = HandoffService(source, FakeSummariser(), Config(default_profile="strong-model"))

    handoff = service.build(focus="next slice", first_prompt_hint="original ask")

    assert source.hint == "original ask"
    assert handoff.front_matter.next_focus == "next slice"
    assert handoff.thread[0].statement == "Keep the seam"


def test_config_loads_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '\n'.join(
            [
                'storage_dir = "~/handoffs"',
                'backend = "tmux"',
                'tmux_dispatch_path = "/opt/bin/tmux-dispatch"',
                'default_profile = "gpt-5.5"',
                'tmux_harness = "codex"',
                'tmux_effort = "high"',
                'tmux_timeout_s = 1200',
            ]
        ),
        encoding="utf-8",
    )

    config = Config.load(config_path)

    assert config.storage_dir == Path.home() / "handoffs"
    assert config.tmux_dispatch_path == "/opt/bin/tmux-dispatch"
    assert config.default_profile == "gpt-5.5"
    assert config.tmux_effort == "high"
    assert config.tmux_timeout_s == 1200


def test_tmux_backend_parses_dispatch_json(tmp_path: Path) -> None:
    dispatch = tmp_path / "tmux-dispatch"
    dispatch.write_text("#!/bin/sh\n", encoding="utf-8")
    dispatch.chmod(0o755)
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                '{"type":"user","message":{"content":"Original intent"}}',
                '{"type":"assistant","message":{"content":"Middle decision"}}',
                '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash",'
                '"input":{"command":"uv run pytest"}}]}}',
                '{"type":"user","message":{"content":[{"type":"tool_result",'
                '"content":"very long output that should not enter the middle"}]}}',
                *[
                    f'{{"type":"assistant","message":{{"content":"Tail item {index}"}}}}'
                    for index in range(25)
                ],
            ]
        ),
        encoding="utf-8",
    )

    def runner(
        args: Sequence[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        assert args[:4] == [str(dispatch), "--harness", "codex", "--prompt-file"]
        prompt_path = Path(args[4])
        prompt = prompt_path.read_text(encoding="utf-8")
        assert "Original intent" not in prompt
        assert "very long output" not in prompt
        assert "Middle decision" in prompt
        assert "[tool_use:Bash] command: uv run pytest" in prompt
        assert "--model" in args
        assert "--effort" in args
        assert capture_output is True
        assert text is True
        assert timeout == 930
        return subprocess.CompletedProcess(
            args=list(args),
            returncode=0,
            stdout=(
                'status line\n{"items":[{"kind":"decision","statement":"Use a port",'
                '"rationale":null}]}\ntrailing text'
            ),
            stderr="",
        )

    backend = TmuxBackend(
        dispatch_path=str(dispatch),
        harness="codex",
        effort="high",
        timeout_s=900,
        runner=runner,
    )

    items = backend.summarise_middle(str(transcript), profile="gpt-5.5")

    assert items == [ThreadItem(kind=ItemKind.decision, statement="Use a port")]


def test_tmux_dispatch_resolves_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKHAND_TMUX_DISPATCH", "/bin/sh")

    assert find_tmux_dispatch() == "/bin/sh"


def test_tmux_dispatch_has_no_private_path_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BACKHAND_TMUX_DISPATCH", raising=False)
    monkeypatch.setenv("PATH", "/tmp/backhand-empty-path")

    assert find_tmux_dispatch() is None


def test_planned_backends_raise_explicit_contract_errors() -> None:
    with pytest.raises(NotImplementedError, match="metered model API"):
        ApiBackend().summarise_middle("/tmp/transcript.jsonl")

    with pytest.raises(NotImplementedError, match="host Claude session"):
        SubagentBackend().summarise_middle("/tmp/transcript.jsonl")


def test_cli_handoff_wires_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeSource(SessionSource):
        tool = "fake-tool"

        def resolve(self, first_prompt_hint: str | None = None) -> ResolvedSession:
            assert first_prompt_hint == "original ask"
            return ResolvedSession(
                tool="fake-tool",
                transcript_path="/tmp/transcript.jsonl",
                head="original ask",
                tail="current state",
                title="CLI handoff",
            )

    class FakeSummariser(SummariserBackend):
        name = "fake-backend"

        def summarise_middle(
            self, transcript_path: str, *, profile: str | None = None
        ) -> list[ThreadItem]:
            assert transcript_path == "/tmp/transcript.jsonl"
            assert profile == "strong-model"
            return [ThreadItem(kind=ItemKind.open, statement="Continue from CLI")]

    captured_config: Config | None = None

    def fake_make_source(tool: str) -> SessionSource:
        assert tool == "claude-code"
        return FakeSource()

    def fake_make_backend(config: Config) -> SummariserBackend:
        nonlocal captured_config
        captured_config = config
        return FakeSummariser()

    monkeypatch.setattr(cli.Config, "load", classmethod(lambda cls: Config(storage_dir=tmp_path)))
    monkeypatch.setattr(cli, "_make_source", fake_make_source)
    monkeypatch.setattr(cli, "_make_backend", fake_make_backend)

    result = cli.main(
        [
            "handoff",
            "--focus",
            "next slice",
            "--first-prompt-hint",
            "original ask",
            "--backend",
            "tmux",
            "--profile",
            "strong-model",
            "--tmux-dispatch-path",
            "/opt/tmux-dispatch",
            "--tmux-harness",
            "codex",
            "--tmux-effort",
            "high",
            "--timeout",
            "1200",
        ]
    )

    assert result == 0
    assert captured_config == Config(
        storage_dir=tmp_path,
        backend="tmux",
        default_profile="strong-model",
        tmux_dispatch_path="/opt/tmux-dispatch",
        tmux_harness="codex",
        tmux_effort="high",
        tmux_timeout_s=1200,
    )
    output_path = Path(capsys.readouterr().out.strip())
    assert output_path.parent == tmp_path
    assert output_path.name.endswith("-cli-handoff.md")
    assert "Continue from CLI" in output_path.read_text(encoding="utf-8")


def test_compact_middle_excludes_head_tail_and_tool_results(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                '{"type":"user","message":{"content":"Head prompt"}}',
                '{"type":"assistant","message":{"content":"Middle point"}}',
                '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash",'
                '"input":{"command":"git diff"}}]}}',
                '{"type":"user","message":{"content":[{"type":"tool_result",'
                '"content":"large diff"}}]}}',
                '{"type":"assistant","message":{"content":"Tail state"}}',
            ]
        ),
        encoding="utf-8",
    )

    middle = compact_middle_text(transcript, tail_messages=1)

    assert "Head prompt" not in middle
    assert "Middle point" in middle
    assert "[tool_use:Bash] command: git diff" in middle
    assert "large diff" not in middle
    assert "Tail state" not in middle
