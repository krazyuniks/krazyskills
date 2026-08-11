---
name: backhand
description: Distil the current long conversation into a compact, high-fidelity handoff file a fresh session can re-import, then you clear. Use at a planned stopping point in a long session before context bloats or auto-compaction, when the reasoning is not yet written to durable files. Final design decisions belong in ADRs.
---

Produce a session handoff with the `backhand` tool bundled in this skill.

## Output

Write a three-zone markdown handoff:

- Intent: the first substantive user prompt, copied verbatim from the transcript after skipping
  Claude command-wrapper turns.
- Thread: typed middle items for decisions, pivots, rejected options, constraints, design points, and
  open work.
- State: the stopping point from the end of the transcript, including compact tool-use and
  tool-result traces.

The front matter links to the full transcript so the next session can re-open the source if needed.

## Steps

1. If the user did not pass a focus argument, ask what the next session is for.
2. Resolve the directory that contains this `SKILL.md`.
3. Run the bundled preflight and CLI:
   `<skill-dir>/bin/backhand handoff --focus "<focus>" --backend herdr`
4. Add `--first-prompt-hint "<text from the first substantive user prompt>"` if the current working
   directory has many Claude transcripts and the first prompt is known.
5. Add `--profile`, `--harness-dispatch-path`, `--herdr-harness`, `--harness-effort`, or `--timeout` only
   when the user asked for a specific model, harness, or dispatch command.
6. Print the exact output path the tool reports. Remind the user that clearing the old session is their
   action; the handoff is already written.

Do not paste the whole transcript into the tool; backhand reads it from the session file itself.

The current working path is Claude Code JSONL source plus the herdr backend. If another source or
backend is requested and the CLI reports it is not implemented, state that plainly and stop.
