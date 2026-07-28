# Agent Memory Store

This directory holds per-run lessons for long-horizon AI agents (Claude Fable 5 / Mythos 5).
Agents read all files here before starting a run, and write one new file after completing
if they learned something the repo doesn't already capture.

## Format — one file per lesson

Filename: `YYYY-MM-DD-{short-slug}.md`

```markdown
# [one-line summary of the lesson]
Date: YYYY-MM-DD

## What happened
[specific event or finding that generated the lesson]

## What to do differently
[the corrected or confirmed approach]

## Why it matters
[what was at stake — why this is worth remembering]
```

## Rules

- **One lesson per file** — never bundle multiple lessons in one file
- **Record corrections and confirmed approaches alike** — both are useful
- **Don't duplicate** — if a lesson already exists, update it rather than creating a new file
- **Don't save what the repo or chat history already captures** — add net-new knowledge only
- **Delete wrong lessons** — a stale or incorrect lesson is worse than no lesson

## System prompt instruction (add to any Fable 5 agent)

```
Before starting, read all files in agent_memory/. After completing the task,
write one lesson file if you learned something the repo doesn't already capture.
Store it as agent_memory/YYYY-MM-DD-{slug}.md with a one-line summary at the top.
```

## Bootstrapping from prior sessions

```
Reflect on the previous sessions we've had together. Use subagents to identify
core themes and lessons, and store them in agent_memory/. Reference agent_memory/
at the start of future runs.
```
