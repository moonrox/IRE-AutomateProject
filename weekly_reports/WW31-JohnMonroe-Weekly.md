# WW31 - Week of Jul 26-Aug 01, 2026
John Monroe | Infrastructure Reliability Engineering
_Generated 2026-07-30 07:13 by weekly_auto_

## Progress

- IRE Dashboard - 13 change(s) this week (across askiredata, ui, catalog, guide, ire-sla, ire-observability):
  - feat(askiredata): show only working models across providers in picker (2026-07-29)
  - feat(askiredata): replace opus 4.8 with gpt-5.5 model option (2026-07-29)
  - refactor(ui): add prominent section headers to discovery tables (2026-07-29)
  - ...and 10 more
- crg-mcp-service - 2 change(s) this week (docs):
  - docs: add Phase-2 execution backlog (2026-07-29)
  - Initial commit: hosted CRG MCP service for Intel MCP Registry (2026-07-29)
- IRE-AutomateProject - 9 change(s) this week (across weekly, graph, WW31, m365):
  - feat(weekly): organize report - per-source summary + top 3 sub-bullets, filter personal/marketing noise (2026-07-30)
  - feat(graph): add delete_from_library; publish WW31 weekly as md (2026-07-29)
  - feat(weekly): make Markdown the weekly deliverable (drop DOCX) (2026-07-29)
  - ...and 6 more
- IRE-python-template - 2 change(s) this week (ci, skills):
  - ci: replace blocked CRG third-party action with pinned pip install (#2) (2026-07-29)
  - skills: add continuous-learning-teach (governed Teach control plane) + identity/prompt-security callouts (#1) (2026-07-29)
- skills_analysis - 7 change(s) this week (across public):
  - journey: add v1.51 master - new S15 production hosting, durability & portable guardrails (2026-07-29)
  - journey(public): sync public doc v1.46 -> v1.50 (2026-07-29)
  - chore: archive AI_Enabled_Journey_v1.49.docx (2026-07-29)
  - ...and 4 more
- Key meetings this week (28 total):
  - Review  network IRE Resiliency slides for Network Engineering - Belvadi, Santhosh @ Microsoft Teams Meeting (2026-07-27)
  - IRE - Team Connect Session- Weekly - Belvadi, Santhosh @ Microsoft Teams Meeting (2026-07-27)
  - Intel Company Meeting - Employee Communications @ Live webcast (link below) (2026-07-27)
  - ...and 25 more
- Notable email activity this week (22 total):
  - [Inbox] IRE Weekly Status - WWWW31 (2026) - john.monroe@intel.com (2026-07-30)
  - [Inbox] Intel + BigPanda Bi-Weekly Sync Follow-Up - jmantri@bigpanda.io (2026-07-29)
  - [Inbox] IRE Sergio Analytics - Session Summary 2026-07-29 - sergio.sanchez.ramos@intel.com (2026-07-29)
  - ...and 19 more

## Blockers / Risks

- OneNote automation blocked by admin-consent gap: posting to the IRE team OneNote notebook requires the Microsoft Graph Notes.ReadWrite.All application scope, which IT has not approved (confirmed via a Graph 403). Workaround in place: weeklies publish as Word docs to IRE > Shared Documents > weeklies. Ask: approve Notes.ReadWrite.All, or bless the OneNote desktop COM alternative (no admin scope).

## Next Week

- Extend app-to-host mapping coverage on the remaining unresolved Dynatrace nodes; curate approved mappings via the review UI.
- AI Adoption Exploration: initialize git, widen snapshot cadence to surface real week-over-week deltas.
- Publish the plan-before-code and last-mile-authorization skills to the team.
