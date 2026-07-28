---
ire_doc:
  type: knowledge
  area: platform
  perspective: developer
  intent: knowledge-capture
  author: "jmonroe"
  created: "2026-07-28"
  updated: "2026-07-28"
  status: draft
  schema_version: "1.1"
  ai_index:
    summary_prompt: "Summarize this as a how-to for giving the 'Weekly Summary Writer' M365 Copilot agent a SharePoint-publish action."
    tags: ["m365-copilot", "declarative-agent", "copilot-studio", "power-automate", "sharepoint", "weekly-report", "openapi", "graph"]
    do_not_summarize: false
---

# Publishing the IRE Weekly from the "Weekly Summary Writer" M365 Copilot Agent

## Overview

`run_weekly.py` publishes the IRE weekly to SharePoint from a workstation using
Microsoft Graph (delegated `Sites.ReadWrite.All` + `Mail.Send`). The manager wants
the same *publish-to-SharePoint* outcome driven from a **Microsoft 365 Copilot
agent** ("Weekly Summary Writer", authored by Kyle Harris) instead of the CLI.

The key fact that drives the whole design:

> A Copilot agent (declarative agent or Copilot Studio agent) **generates text and
> reads knowledge sources**. It cannot write a file to SharePoint by itself. To make
> it publish, you attach an **action**. Everything below is about building that action.

| Agent capability | Writes to SharePoint? | Role |
|---|---|---|
| Instructions | No | Shapes the drafted summary |
| Knowledge (SharePoint / Graph connector) | No — **read-only** grounding | Lets it *read* prior weeklies for context |
| **Action** (Power Platform connector / flow **or** API plugin) | **Yes** | The publish mechanism you add |

Two supported routes are documented here. **Route A (Power Automate flow)** is
recommended: no hosted code, runs as the signed-in user (sidesteps the
Notes/Graph admin-consent blocker), and can render a real Word doc. **Route B
(API plugin)** reuses this repo's existing Graph upload code but requires a hosted,
authenticated endpoint.

---

## Detail

### Which builder is the agent in?

The exact menu names differ; the concept (add an action) is identical.

| Signal | Builder | Where you add the action |
|---|---|---|
| Opened at `copilotstudio.microsoft.com`, topics/actions canvas | **Copilot Studio** | *Actions → + Add an action → Connector / Flow* |
| Built inside Copilot chat via "Create agent", tabs = Instructions / Knowledge / Actions | **Agent Builder (declarative)** | *Actions → Add → (API plugin from OpenAPI)* |

Because the agent was created by Kyle, either share it with edit rights, or Kyle
applies the action change and republishes. The invoking user's SharePoint
permissions to `IRE > Shared Documents > weeklies` still apply at run time.

---

### Route A — Power Automate flow action (recommended)

No hosted code. The flow does the doc rendering and the SharePoint write; the agent
only drafts the summary text and calls the flow.

**A1. Create the flow**
- Trigger: **When a Copilot skill is invoked** (Copilot Studio) *or* **When an
  HTTP request is received** (standalone flow you attach as a connector action).
- Request JSON schema (agent → flow):

```json
{
  "type": "object",
  "properties": {
    "ww":        { "type": "string", "description": "Work week label, e.g. WW31" },
    "year":      { "type": "integer" },
    "author":    { "type": "string" },
    "progress":  { "type": "array", "items": { "type": "string" } },
    "blockers":  { "type": "array", "items": { "type": "string" } },
    "next_week": { "type": "array", "items": { "type": "string" } }
  },
  "required": ["ww", "progress"]
}
```

**A2. Render the document** (keep formatting identical to the CLI output)
- Add **Word Online (Business) → Populate a Word template**.
- Store a `WeeklyTemplate.docx` in the site with repeating-section content controls
  for Progress / Blockers / Next Week (mirror `weekly_report.py` layout).
- *Simpler alternative:* skip Word and write Markdown/`.txt` with **Compose**.

**A3. Write to SharePoint**
- **SharePoint → Create file**
  - Site Address: the IRE site
  - Folder Path: `/Shared Documents/weeklies`
  - File Name: `@{concat(triggerBody()?['ww'], '-JohnMonroe-Weekly.docx')}`
  - File Content: output of *Populate a Word template* (or the Compose text)
- Capture **`Link to item`** from the Create file output.

**A4. (Optional) Email** — Office 365 Outlook → **Send an email (V2)**, include the
`Link to item` in the body (parity with the CLI, which now injects the SharePoint
link — see `run_weekly.py`).

**A5. Respond to the agent** — return `{ "sharepoint_url": "<Link to item>",
"file_name": "<name>" }` so the agent can show the user the link.

**A6. Attach to the agent**
- Copilot Studio: *Actions → + Add an action → Flow* → pick this flow → map inputs.
- Agent Builder: add as a **Power Platform connector action**.

**A7. Instruction snippet for the agent** (paste into its Instructions):

```
When the user asks to publish or upload the weekly, first draft the summary with
Progress, Blockers/Risks, and Next Week bullets. Then call the PublishWeekly action
with ww, author, progress, blockers, and next_week. Return the sharepoint_url it
responds with as a clickable link. Never claim it is published unless the action
returns a sharepoint_url.
```

---

### Route B — API plugin action (reuse this repo's Graph code)

Wrap the existing upload path (`graph_auth.py` / `GraphClient.upload_to_library`,
as used by `run_weekly.py`) behind **one REST endpoint**, describe it with OpenAPI,
and register it as an API plugin.

- Endpoint contract + schema: **`docs/m365-agent/openapi-publish-weekly.yaml`**
- Declarative-agent action manifest: **`docs/m365-agent/weekly-publish-action.json`**

Hosting/security requirements:
- Host the endpoint (Azure Function or the existing IRE FastAPI). It must be
  reachable from the Microsoft 365 service (public HTTPS or an approved gateway).
- Authenticate. The OpenAPI spec uses an API key header (`X-API-Key`) for a quick
  start; for production prefer **Microsoft Entra ID (OAuth 2.0)** so the call runs
  as the user and inherits SharePoint permissions.
- The service — not the agent — renders the `.docx` and calls Graph, exactly like
  `run_weekly.py` does today.

---

## Examples

**User → agent:** "Publish my WW31 weekly to SharePoint and email me the link."

**Agent (either route):**
1. Drafts Progress / Blockers / Next Week.
2. Calls `PublishWeekly` (flow or API plugin).
3. Action writes `WW31-JohnMonroe-Weekly.docx` to `weeklies`, returns the URL.
4. Agent replies: "Published — [WW31-JohnMonroe-Weekly.docx](<sharepoint_url>). Email sent."

---

## Related

- `run_weekly.py` — the CLI equivalent (build → upload → email, now with the link in the email body).
- `weekly_report.py`, `weekly_auto/report_builder.py` — the exact Progress/Blockers/Next-Week format to mirror in the Word template.
- `graph_auth.py` — `GraphClient.upload_to_library` / `send_mail` (Route B backing logic).
- `Graph-API-SharePoint.md` — Graph SharePoint upload reference.
- `docs/m365-agent/openapi-publish-weekly.yaml` — Route B OpenAPI spec.
- `docs/m365-agent/weekly-publish-action.json` — Route B declarative-agent action manifest.

> **Verification note (VERIFIED/INFERRED):** The "agents need an action to write; knowledge is
> read-only" model and the Route A/B mechanics are INFERRED from current Microsoft 365 Copilot /
> Copilot Studio / Power Platform behavior and may shift as those products update. Confirm exact
> menu labels in your tenant before building; the request/response contracts here are stable and
> tool-agnostic.
