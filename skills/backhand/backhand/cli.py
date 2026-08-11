"""backhand CLI: handoff / list / status."""

from __future__ import annotations

import argparse
import sys
from typing import get_args

from .adapters.sources.claude_jsonl import ClaudeJsonlSource
from .app.service import HandoffService
from .config import BackendName, Config
from .ports.session_source import SessionSource
from .ports.summariser import SummariserBackend


def _make_source(tool: str) -> SessionSource:
    if tool == "claude-code":
        return ClaudeJsonlSource()
    raise SystemExit(f"No source adapter for tool '{tool}' yet.")


def _make_backend(config: Config) -> SummariserBackend:
    if config.backend == "subagent":
        from .adapters.summarisers.subagent import SubagentBackend

        return SubagentBackend()
    if config.backend == "herdr":
        from .adapters.summarisers.herdr import HerdrBackend

        return HerdrBackend(
            dispatch_path=config.harness_dispatch_path,
            harness=config.harness_profile,
            effort=config.harness_effort,
            timeout_s=config.harness_timeout_s,
        )
    if config.backend == "api":
        from .adapters.summarisers.api import ApiBackend

        return ApiBackend()
    raise SystemExit(f"Unknown backend '{config.backend}'.")


def _config_with_overrides(config: Config, updates: dict[str, object]) -> Config:
    data = config.model_dump()
    data.update({key: value for key, value in updates.items() if value is not None})
    return Config.model_validate(data)


def cmd_handoff(args: argparse.Namespace) -> int:
    config = _config_with_overrides(
        Config.load(),
        {
            "backend": args.backend,
            "default_profile": args.profile,
            "harness_dispatch_path": args.harness_dispatch_path,
            "harness_profile": args.harness_profile,
            "harness_effort": args.harness_effort,
            "harness_timeout_s": args.timeout,
        },
    )
    service = HandoffService(_make_source(args.tool), _make_backend(config), config)
    handoff = service.build(
        focus=args.focus,
        first_prompt_hint=args.first_prompt_hint,
        profile=config.default_profile,
    )
    print(service.write(handoff))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    config = Config.load()
    if not config.storage_dir.is_dir():
        print("(no handoffs yet)")
        return 0
    for path in sorted(config.storage_dir.glob("*.md")):
        print(path)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(Config.load().model_dump_json(indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backhand", description="Session handoff tool.")
    sub = parser.add_subparsers(dest="command", required=True)

    ph = sub.add_parser("handoff", help="write a handoff for the current session")
    ph.add_argument("--focus", help="what the next session is for")
    ph.add_argument("--first-prompt-hint", help="text from the first user prompt to disambiguate")
    ph.add_argument("--profile", help="summariser model/profile name passed to the backend")
    ph.add_argument(
        "--backend",
        choices=list(get_args(BackendName)),
        help="summariser backend",
    )
    ph.add_argument("--tool", default="claude-code", help="host agent tool")
    ph.add_argument("--harness-dispatch-path", help="path to harness-dispatch")
    ph.add_argument("--harness-profile", help="harness-dispatch profile name")
    ph.add_argument("--harness-effort", help="harness-dispatch effort override")
    ph.add_argument("--timeout", type=int, help="backend completion timeout in seconds")
    ph.set_defaults(func=cmd_handoff)

    pl = sub.add_parser("list", help="list stored handoffs")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("status", help="show config and storage location")
    ps.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
