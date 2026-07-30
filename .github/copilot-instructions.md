# Copilot Instructions

## Project Overview
Describe the project purpose here so Copilot has context.

## Language & Runtime
- Python 3.11+
- Virtual environment at `.venv/`

## Conventions
- Source code lives in `src/`
- Tests live in `tests/`
- Use `test_runner.py` for input/output script tests; use `pytest` for unit tests
- Keep secrets in `.env` (never commit)

## Key Files
- `requirements.txt` — runtime dependencies
- `requirements-dev.txt` — dev/test tools
- `pyproject.toml` — project metadata and tool config
- `assess_skills.py` — skills scanner CLI (run `python assess_skills.py`)

## Code Quality Stack

Two tools, one job each — never swap their roles:

| Tool | Role | Command | Config section |
|------|------|---------|----------------|
| **Black** | **Format** — rewrites whitespace, quotes, trailing commas. Opinionated, zero per-rule config. | `black .` | `[tool.black]` |
| **Ruff** | **Lint** — catches errors, unused imports, naming, upgrades. Fast, rule-based. | `ruff check .` | `[tool.ruff.lint]` |
| **mypy** | **Type check** — enforces type annotations. | `mypy src/` | `[tool.mypy]` |

### Run order (always format before lint)
```powershell
black .          # 1. format first — removes style noise from lint output
ruff check .     # 2. lint second — flags real problems
mypy src/        # 3. type-check last
```

### Rules
- **Do not run `ruff format`** — Black owns formatting. `ruff format` and `black` conflict.
- **Do not add `[tool.ruff.format]`** to `pyproject.toml` — same reason.
- Black `line-length = 100` and Ruff `line-length = 100` must always match.
- All three tools are declared in `requirements-dev.txt` and `[project.optional-dependencies].dev`.

## Engineering Skills (`.github/skills/`)
This project ships Matt Pocock's engineering skills — available to Claude, Copilot, and any AI tool that reads this repo:

> ### ⛔ Plan-Before-Code Gate (mandatory, non-negotiable)
> **Never write or modify production code before an approved plan exists.** An
> approved plan is an issue, an approved PRD, an ADR, or a plan the user
> **explicitly approved** in the conversation. A vague request is not a plan.
> If no approved plan exists, **STOP**, invoke `plan-before-code`, write the plan,
> and wait for explicit user approval before coding. The only exceptions are
> `prototype` (throwaway code, clearly labelled) and trivial user-requested fixes
> (typo, one-line doc/format change). When in doubt, stop and ask.

| Skill | When to invoke |
|-------|---------------|
| `plan-before-code` | **BEFORE any production code** — hard gate confirming an approved plan (issue/PRD/ADR/approved conversation plan) exists |
| `codebase-design` | Designing or improving a module's interface, finding deepening opportunities |
| `diagnosing-bugs` | Hard bugs, performance regressions — "diagnose this" / "debug this" |
| `domain-modeling` | Pinning down domain terminology, writing CONTEXT.md or ADRs |
| `implement` | Implementing a planned task |
| `improve-codebase-architecture` | Architecture improvement analysis and HTML report |
| `prototype` | Rapid prototyping before committing to an approach |
| `resolving-merge-conflicts` | Resolving merge conflicts |
| `tdd` | Test-driven development workflow |
| `to-issues` | Breaking a PRD into actionable GitHub issues |
| `to-prd` | Converting an idea or brief into a Product Requirements Document |
| `triage` | Triaging and labelling incoming issues |
| `avoiding-agent-conflicts` | Multi-agent conflict prevention — goal alignment, deadlock detection, kill switches |
| `knowledge-identity` | Reading/writing/drafting docs with IRE Knowledge Identity front matter and author profiles |
| `analytical-integrity` | Verifiable claims standard — VERIFIED/INFERRED/UNVERIFIED tagging, citation, exportable evidence |
| `paginating-api-fetches` | Pagination pattern for any API returning total/count — prevents silent data truncation |
| `singapore-ai-governance` | IMDA 4-dimension governance: risk bound, human accountability, technical controls, deskilling prevention |
| `fable5-agentic-patterns` | Claude Fable 5/Mythos 5 scaffolding: effort levels, memory system, send_to_user, progress grounding, boundary instructions |
| `last-mile-authorization` | Any agent data read/write, action, or external API call — validate authorization at the moment of use via a central Policy Decision Point (Zero Trust); cached decisions are never permanent |
| `mcp-server-security` | Building/deploying/reviewing an MCP server — deployment-model-driven auth, pass-through JWT authz, TLS, secret vaulting, prompt-injection/hallucination defenses, tool-poisoning & DoS controls, audit logging (approved for internal use; includes a quick-start checklist) |

Source: [mattpocock/skills](https://github.com/mattpocock/skills) — Skills for Real Engineers.

## Skills Scanner (`src/skills/`)

A separate but complementary system that **detects engineering practice evidence** in the codebase:
- `registry.py` — built-in skills (AI, Python, M365, SRE, Governance, …)
- `loader.py` — merges built-in skills with any `*.yaml` skill definitions
- `*.yaml` — drop additional skill YAML files here; auto-discovered

Run the scanner:
```powershell
python assess_skills.py              # scan this project
python assess_skills.py --list-skills  # see all available skills
python assess_skills.py --domain "SRE" # filter by domain
```

> **Two systems, one purpose:** `.github/skills/` tells AI *how to work*. `src/skills/` measures *how well the code reflects* good engineering.

## Deferred Skills — Add Only When Triggered

These skills were analyzed and deliberately **not added** to the registry. The scanner must
detect real evidence — adding a skill with no codebase evidence breaks the zero-gap record.
Add the skill YAML **only when the trigger condition is met**.

### Batch Processing

**Decision (2026-06-27):** Not added. Current pipelines process all data in memory at once.
No chunking, queue, retry, or checkpoint patterns exist. Adding the skill now would create a
Not Detected gap with zero value.

**Add `batch_processing.yaml` when ANY of these conditions is true:**

| Trigger | Signal | Action |
|---|---|---|
| Pipeline hits `MemoryError` | Dataset no longer fits in memory | Add `batch_size` chunking to that pipeline |
| API calls get rate-limited | HTTP 429 / throttle errors from lake, Graph, or LLM endpoints | Add batch loop + exponential backoff + retry queue |
| Pipeline fails mid-run and must restart from scratch | Reprocessing costs > 5 minutes | Add checkpointing (write last-processed ID to disk) |
| Processing 10K+ records and need visibility | Long-running pipeline with no progress signal | Add `tqdm` progress bar + chunk loop |
| Chunks can be processed independently | No cross-chunk dependencies | Wire into `Orchestrator.run_parallel()` — sub-agent scaffold already handles this |

**Patterns to detect when adding the skill:**
```python
batch_size       # chunk sizing parameter
for chunk in     # chunked iteration
checkpoint(      # resumable state write
retry_queue      # dead-letter / retry
tqdm(            # progress tracking
run_parallel(    # parallel chunk execution (already in src/agents/)
```

**Related skills already active:** Sub-agent Orchestration (`run_parallel`), Dynamic Context
Injection (token-aware trimming is a form of batching for LLM inputs).

---

## Model Selection Framework

Choose the right model for the task — the larger the context window, the higher the cost.

| Tier | Model | When to use |
|------|-------|-------------|
| Triage | `claude-haiku-4.5` | Status checks, file searches, log reads, config edits |
| Analysis | `claude-sonnet-4.6` | **Default** — code, debugging, endpoints, investigations |
| Decision | `claude-opus-4.8` | ADRs, architecture changes, security review, trade-offs |

### Switching models mid-session
```
/model claude-haiku-4.5    # switch to Haiku for cheap tasks
/model claude-opus-4.8     # switch to Opus for high-stakes decisions
/model auto                # let Copilot choose
```

### Per-subagent defaults
| Agent type | Default model |
|------------|--------------|
| `explore`, `task` | Haiku — background scans and builds |
| `general-purpose`, `code-review` | Sonnet — default analysis |
| `security-review`, `rubber-duck` | Opus — high-stakes review |

Configure subagent defaults persistently with `/subagents`.

## Knowledge Identity Layer (Optional)

If `docs/ire-knowledge-schema.yaml` exists in this project with `enabled: true`,
the IRE Knowledge Identity Layer is active. Apply it when writing, reviewing,
or ingesting any documentation.

| File | Purpose |
|------|---------|
| `docs/ire-knowledge-schema.yaml` | Feature toggle + project config |
| `docs/ire-taxonomy.yaml` | Valid values for all front matter fields |
| `docs/authors/{username}.md` | Author writing profiles (voice + attribution) |
| `docs/knowledge/_doc-template.md` | Front matter template for new documents |

**When writing a new `.md` doc:** copy `_doc-template.md`, fill in the `ire_doc`
front matter, and use `docs/ire-taxonomy.yaml` for valid field values.

**When drafting for an author:** load `docs/authors/{username}.md` first and
match their `tone`, `structure`, and `vocabulary` exactly.

**Full instructions:** invoke the `knowledge-identity` skill
(`/skill knowledge-identity` or see `.github/skills/knowledge-identity.md`).

**To disable:** set `enabled: false` in `docs/ire-knowledge-schema.yaml`,
or delete the file. Scanner will report "Not Detected" — this is not a gap.

## code-review-graph (Optional) — token reduction

This template ships an **opt-in** `code-review-graph` (CRG) integration and, when
scaffolding, offers to install it. CRG builds a local Tree-sitter code graph so AI
assistants can query callers, callees, tests, affected flows, and blast radius
**before** reading whole files — cutting token usage on reviews and debugging.

**Availability vs. activation — two separate things:**
- *Available (always):* CRG is declared in the `dev` dependency group, documented
  in `docs/knowledge/crg-token-reduction.md`, and wired into the optional
  `.github/workflows/crg-pr-review.yml`. Nothing runs automatically.
- *Active (opt-in):* the scaffolder prompts *"Install and activate CRG now?"*
  (or pass `--install-crg` / `--no-install-crg`). Activation pip-installs CRG into
  the new `.venv`, registers a local MCP server, and builds `.code-review-graph/`.
  It always uses `--no-skills --no-hooks` so CRG never overwrites `.github/skills/`.

**When CRG is active** (a `.code-review-graph/` graph exists and
`.github/code-review-graph.instruction.md` is present), **prefer the graph tools
FIRST** for code exploration and review: `query_graph_tool`,
`get_minimal_context_tool`, `detect_changes_tool`, `get_impact_radius_tool`,
`get_affected_flows_tool`, `semantic_search_nodes_tool`,
`get_architecture_overview_tool`. Fall back to file/search tools only when the
graph does not cover what you need. Keep it fresh with `code-review-graph update`
(git repos) or `code-review-graph build`.

**Full setup, air-gapped caveats, and the PR-review workflow:**
see `docs/knowledge/crg-token-reduction.md`.

## GitHub Repo Creation via Inventory (`C:\scripts\inventory`)

New Intel GitHub repos are created by adding an entry to the inventory repo and raising a PR.
The inventory lives at `C:\scripts\inventory` (org: `intel-innersource`).

### Namespace for IRE projects
`organizations/intel-innersource/repos/applications/services/resiliency/repos.yml`

### ⚠️ GUID Rule — never forget this
Every new repo entry **MUST** include `guid:` as a **blank placeholder with no value**.

```yaml
name: applications.services.resiliency.your-repo-name
guid:
description: Short description of the repo.
owners:
- john.monroe@intel.com
- kyle.r.harris@intel.com
topics:
- resiliency
- python
permissions:
  owners-as-admins: true
  maintain:
  - IRE Resiliency Maintainers
```

**DO NOT** generate or invent a GUID value.  
**DO NOT** omit the `guid:` field entirely.  
The inventory-cli automation detects the blank placeholder and fills it in automatically
during the PR workflow ("Auto-formatting inventory and adding GUIDs to new entities").
Providing a value or omitting the field will break automation.

### Inventory Local Path
The inventory can be cloned to any location. The IRE team convention is
`C:\scripts\inventory`. Use `$inventory = "<your-path>"` in PowerShell
to make all commands portable. Check if it exists before cloning:

```powershell
$inventory = "C:\scripts\inventory"   # IRE convention — change if needed
if (-not (Test-Path $inventory)) {
    git clone https://github.com/intel-innersource/inventory.git $inventory
}
```

### ⚠️ Fork Requirement — why a plain `origin` push fails
`intel-innersource/inventory` enforces a branch-protection ruleset that blocks new
branches on `origin` (`git push origin` fails with **"Cannot create ref due to
creations being restricted"**). All contributions go through **your personal fork**.
Set it up **once**:

```powershell
cd $inventory
# One-time: create the fork and register it as a remote named `fork`
gh repo fork intel-innersource/inventory --remote --remote-name fork
git remote -v   # expect: origin → intel-innersource/inventory, fork → <you>/inventory
```

### Workflow
1. **First time only:** clone inventory **and create the fork** (see above)
2. `cd $inventory; git checkout master; git pull`  ← **always pull first — inventory moves fast** (PowerShell has no `&&`; use `;`)
3. Create a branch: `git checkout -b add-<repo-name>`
4. Append the entry (with blank `guid:`) to the correct `repos.yml`
5. Stage **only** that file: `git add <path>/repos.yml` — **never `git add .`** (keep unrelated working-tree changes out of the PR)
6. Commit: `git commit -m "add: applications.services.resiliency.<repo-name>"`
7. **Pull-before-push:** `git fetch origin; git rebase origin/master`  ← rebase onto latest so the push is clean
8. Push to your **fork**, not origin: `git push -u fork add-<repo-name>`
9. Open the PR from the fork branch against upstream:
   `gh pr create --repo intel-innersource/inventory --base master --head <your-gh-user>:add-<repo-name> --title "add: ..." --body "..."`
10. Governance + namespace governors review and merge — **you cannot self-merge**
11. Once PR is merged → automation provisions the repo **and writes the GUID back into repos.yml**
12. `git checkout master; git pull`  ← **pull again to get the auto-generated GUID**
13. Then `git init` the local folder, **pull-before-push**, and push `main` to the newly provisioned repo

## Weekly Status Report (`run_weekly.py`)

The automated weekly (`python run_weekly.py [--ww WWnn] [--dry-run]`) collects git
commits, ADRs, Outlook mail (Graph Mail.Read), and Outlook meetings (local COM /
pywin32 — no Graph Calendars scope), then publishes a **Markdown** deliverable to
the IRE SharePoint `weeklies` library and emails a copy. Keep this format —
it is the agreed house style.

### Reporting window — Thursday AM → Wednesday PM
The report is **due on Wednesday**, so its window is the trailing 7 days:
**Thursday AM → Wednesday PM**. The Wednesday anchor is the Wednesday that falls
inside the WW's Intel Sun–Sat span; the window runs back to the prior Thursday.
Consecutive work weeks tile without overlap, e.g.:

| WW | Reporting window |
|----|------------------|
| WW30 | Thu Jul 16 → Wed Jul 22, 2026 |
| WW31 | Thu Jul 23 → Wed Jul 29, 2026 |

This is implemented in `weekly_auto/util._report_window()`; `work_week()` and
`work_week_from_label()` both return this Thu–Wed window. Do **not** revert to a
Sun–Sat window.

### Progress formatting — summary line + top 3 sub-bullets
Each source is **one summary bullet** (name · change count · themed
conventional-commit scopes) with the **top 3 items as nested sub-bullets** and an
`...and N more` roll-up. Sources are capped at 3 sub-bullets each (commits, ADRs,
meetings, emails). Example:

```markdown
## Progress

- IRE Dashboard - 13 change(s) this week (across askiredata, ui, catalog):
  - feat(askiredata): show only working models across providers (2026-07-29)
  - refactor(ui): add prominent section headers to tables (2026-07-29)
  - ...and 10 more
- Key meetings this week (28 total):
  - IRE - Team Connect Session - Weekly (2026-07-27)
  - ...and 25 more
```

Then `## Blockers / Risks` and `## Next Week` (narrative, from `weekly_notes.md`).

### Email body vs. Markdown deliverable
- The **Markdown file** (SharePoint + attachment) keeps the full detail
  (summary line **plus** top-3 sub-bullets).
- The **email body** shows Progress **summary lines only** — sub-bullets are
  stripped via `report_builder.summary_markdown()`. Blockers / Next Week bullets
  stay.

### Noise filtering
Personal / marketing items are excluded via `exclude_keywords` in
`weekly_sources.json` (calendar: `karate`, `silicon forest`; email: marketing /
social senders). Add new noise terms there — do not hard-code filters in the
collectors.
