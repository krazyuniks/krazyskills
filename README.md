# krazyskills

Agent skills, kept small enough for humans to read and structured enough for agents to use.

The installable surface is `skills/`. Each child directory is a self-contained skill with a
`SKILL.md` file and any code it needs beside it.

## Skills

| Skill | Status | What it does |
|---|---|---|
| `backhand` | Working first slice | Writes a compact handoff from a Claude Code session transcript, with deterministic head/tail extraction and model-written middle synthesis through an external `tmux-dispatch` command. |

Planned backhand adapters for Codex, Pi, Gemini, and a metered API backend are tracked as GitHub
issues rather than hidden behind vague README promises.

## Install

Clone the repo:

```bash
mkdir -p "$HOME/src" && git clone https://github.com/krazyuniks/krazyskills.git "$HOME/src/krazyskills"
```

Symlink the skill you want into the agent that should see it:

```bash
ln -s "$HOME/src/krazyskills/skills/backhand" "$HOME/.codex/skills/backhand"
```

For Claude Code, use `~/.claude/skills/backhand` instead. If your agent sync tool can consume a
skills directory directly, point it at the cloned repo's `skills/` directory.

## Backhand

Backhand is for the point in a long agent session where the work is still live, but the context is
getting expensive. It writes a markdown handoff with:

- the first substantive user intent copied verbatim, skipping Claude command-wrapper turns
- typed middle items for decisions, pivots, rejected options, constraints, design points, and open work
- the current stopping state copied from the end of the transcript, including compact tool traces
- front matter linking back to the full transcript

The fresh session reads that handoff, then continues without hauling the whole old conversation back
into context.

### Backhand prerequisites

Backhand uses Python through `uv`.

```bash
uv --version
```

The current working backend also needs `tmux` and a `tmux-dispatch` command from a compatible
tmux-harness installation. Backhand resolves `tmux-dispatch` from this order:

1. `--tmux-dispatch-path`
2. `tmux_dispatch_path` in `~/.backhand/config.toml`
3. `BACKHAND_TMUX_DISPATCH`
4. `PATH`

Backhand checks local prerequisites and prints the missing command; it does not install packages or
run `sudo`. The `subagent` and `api` backends are planned contracts and currently raise explicit
not-implemented errors.

### Use from an agent

Ask the agent to use the skill:

```text
Use $backhand to write a handoff for the next session: finish the README and publish the repo.
```

### Use from a shell

```bash
"$HOME/src/krazyskills/skills/backhand/bin/backhand" handoff --focus "finish the README and publish the repo" --first-prompt-hint "I've just created a new repo" --backend tmux
```

The command prints the handoff path. You decide when to clear the old session.

### Configure

Optional config lives at `~/.backhand/config.toml`.

```toml
storage_dir = "~/.backhand/handoffs"
backend = "tmux"
tmux_dispatch_path = "/path/to/tmux-dispatch"
tmux_harness = "codex"
default_profile = "gpt-5.5"
tmux_effort = "high"
tmux_timeout_s = 900
```

## Development

Run the same checks as CI:

```bash
uv run --project skills/backhand python scripts/validate_skills.py
uv run --project skills/backhand --group dev ruff check skills/backhand scripts
uv run --project skills/backhand --group dev pyright
uv run --project skills/backhand --group dev pytest -q
```

The Python code follows a ports-and-adapters shape:

- `domain/` contains Pydantic models and pure rendering.
- `ports/` defines session-source and summariser contracts.
- `adapters/` holds Claude JSONL and tmux-dispatch integration code.
- `app/` wires the use case without importing concrete adapters.
