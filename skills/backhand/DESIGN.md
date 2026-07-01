# backhand - Design

Distil a long agent conversation into a compact, high-fidelity markdown handoff that a fresh session
re-imports. You call it at a planned stopping point in a long session, it writes the handoff, you
`/clear`, and the next session reads the handoff to resume with a clean, cheap context. You control
what survives a context reset instead of leaving it to lossy auto-compaction.

## Principle: fidelity by copy and link, not by "condense harder"

A model cannot losslessly "condense without summarising" - it regenerates, i.e. paraphrases. The only
lossless moves are copy and link. So backhand copies the parts that must be exact and links to
the full source, and only asks a model to compress the part that is safe to compress.

## The three-zone document

A fidelity gradient, not a flat summary:

1. Head - Intent (verbatim). The first substantive user prompt, copied exactly from the transcript
   after skipping Claude command-wrapper turns.
2. Middle - Thread (itemised, typed). The journey as a list of typed items, each condensed but
   never merged into a blob. Types: `decision`, `pivot`, `rejected`, `design-point`, `open`,
   `constraint`. Itemisation preserves the count and distinctness of ideas even when each is
   compressed - this is the anti-lossiness lever.
3. Tail - State (near-verbatim). The stopping point / transition: where we stopped, what was
   finalised, the immediate next step, and what is still uncertain. Lifted from the tail of the
   transcript with minimal paraphrase, including compact tool-use and tool-result traces.

Plus front-matter that links to the full session transcript - the lossless fallback you can always
re-expand from.

### Division of labour

- Deterministic (no model): front-matter, head (copied), tail (copied), assembly, file write.
- Model (one call): the middle excerpt only. The tmux backend drops command-wrapper turns, the
  copied head/tail zones, and verbose tool-result blobs before dispatch, which bounds cost and keeps
  the head and tail genuinely deterministic.

## Front-matter

```yaml
type: handoff
tool: claude-code            # claude-code | codex | gemini | pi
created: 2026-07-01T16:55:00Z
cwd: $HOME/src/example-project
git_branch: main
git_head: 64a00e46
model: claude-opus-4-8
session_ref: ~/.claude/projects/<slug>/<session-id>.jsonl
next_focus: "what the next session is for"
supersedes: <prior handoff path | null>
title: <ai-title if available>
```

`session_ref` is tool-specific (Claude JSONL; Codex SQLite/history.jsonl; Pi `~/.pi/agent/sessions`;
Gemini its own). It is the real "zip": the markdown is a lossy index into this exact original.

## Current implementation

The current working slice supports:

- Claude Code JSONL transcripts as the session source.
- deterministic extraction of head, tail, compact tool traces, title, model, cwd, and git branch
- tmux-dispatch as the middle-synthesis backend
- reproducible checks through uv, ruff, pyright, pytest, and skill validation

The Codex, Pi, Gemini, subagent, and API adapters are explicit contracts or planned adapters. They are
not presented as complete.

## Architecture: onion / hexagonal

Pydantic domain at the core; two ports; adapters at the edges. The core never imports an adapter and
never couples to the vault, dotfiles, or any specific harness.

```
domain/      Pydantic models (Handoff, FrontMatter, ThreadItem) + pure rendering. No I/O.
ports/       SessionSource, SummariserBackend  (abstract)
adapters/
  sources/     claude_jsonl, codex, pi, gemini      -> implement SessionSource
  summarisers/ subagent, tmux, api                  -> implement SummariserBackend
app/         HandoffService orchestrates: resolve -> extract head/tail -> summarise middle
             -> assemble -> render -> write -> return path
config.py    Pydantic Config (storage dir, default profile, backend selection)
cli.py       handoff / list / status
```

### Port 1 - SessionSource (per tool)

Locate the current session, read its transcript, extract the verbatim head and tail plus metadata.
`ClaudeJsonlSource` resolves the JSONL by scanning the project-slug dir and matching the first
substantive user prompt when a hint is supplied. Modified time is the fallback.

### Port 2 - SummariserBackend

Produce the itemised middle from a scoped transcript excerpt. Backend choice is a port because
different users can require subscription-backed local tooling, in-session subagents, or an explicit
metered API path.

- `tmux` is implemented. It shells out to `tmux-dispatch --harness ... --prompt-file ...`, asks for a
  JSON response, extracts the first JSON object from noisy harness output, validates that response
  with Pydantic, and returns `ThreadItem` models. `tmux-dispatch` is resolved from explicit config,
  `BACKHAND_TMUX_DISPATCH`, or `PATH`; it is not bundled with this repo.
- `subagent` is a planned host-driven backend for tools that can spawn a summariser agent inside the
  current session.
- `api` is a planned backend for users who explicitly want a metered API path.

"One skill calling another" happens at the model layer; at the code layer the reuse of
`tmux-harness` is this adapter calling the CLI that skill exposes.

## Backend choice depends on invocation context

The default config uses `tmux`, because that is the working non-metered backend. `subagent` and `api`
raise explicit not-implemented errors until their adapters are wired.

## Settled decisions

- One-shot, on explicit `/backhand`. Not continuous: the JSONL is already the continuous lossless
  record, so incremental synthesis only burns tokens on every session to duplicate it lossily.
- `/clear` is manual. A skill cannot invoke `/clear` (client-side, user-only; no tool or hook
  action). backhand prints the deterministic path; you clear when ready. A detached backend keeps
  writing after you clear (`/clear` wipes the conversation, not OS processes).
- Durable storage, not `/tmp`. Rich metadata (JSONL link, git SHA) implies a kept, browsable
  corpus of handoffs, not a file binned in five minutes. `list` / `status` browse it.
- Model/profile choice is passed through the CLI with `--profile`; backend-specific harness and
  effort options stay backend-specific.
- First-prompt JSONL match is the primary session key; mtime is the tiebreak.
- Claude-first, other source adapters follow.

## Prerequisites

UV is required. tmux and `tmux-dispatch` are required for the tmux backend. The `bin/backhand`
preflight checks local prerequisites and instructs the user on any gap; it never auto-installs and
never runs `sudo`.

## Non-goals

- Not a replacement for durable project docs. For project work the backlog/Overview is the handoff;
  for a real design phase, the reasoning belongs in ADRs. backhand captures a session's thread so you
  can resume its headspace, not the canonical design.
