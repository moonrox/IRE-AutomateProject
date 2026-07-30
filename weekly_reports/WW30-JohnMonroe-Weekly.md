# WW30 - Reporting window Thu Jul 16 - Wed Jul 22, 2026
John Monroe | Infrastructure Reliability Engineering
_Generated 2026-07-30 07:32 by weekly_auto_

## Progress

- IRE Dashboard - 24 change(s) this week (across adr, rca):
  - Add ADR-038: incident-centric tool navigation (RCA/ProgramLevelRCA/NearMiss/Forensics) (2026-07-17)
  - Split Program-Level RCA metrics into own page; add Forensics cross-links (2026-07-17)
  - Add direct ticket-number jump link on /view/forensics (2026-07-17)
  - ...and 21 more
- IRE-python-template - 6 change(s) this week (feat, fix, add, docs):
  - feat: add mandatory Plan-Before-Code gate to skills framework (2026-07-22)
  - fix: scaffold robustness + skill loader/knowledge-identity fixes; add ire-scaffold.ps1 (2026-07-22)
  - add: last-mile-authorization skill + agent privilege-isolation patterns (2026-07-22)
  - ...and 3 more
- applications.services.resiliency.ire-python-template - 6 change(s) this week (feat, fix, add, docs):
  - feat: add mandatory Plan-Before-Code gate to skills framework (2026-07-22)
  - fix: scaffold robustness + skill loader/knowledge-identity fixes; add ire-scaffold.ps1 (2026-07-22)
  - add: last-mile-authorization skill + agent privilege-isolation patterns (2026-07-22)
  - ...and 3 more
- AI Adoption Exploration - 86 change(s) this week:
  - adoption_report.py (2026-07-21)
  - assess_skills.py (2026-07-20)
  - context_window.py (2026-07-20)
  - ...and 83 more
- Key meetings this week (16 total):
  - AI Modernization Journey for IAPM - IT Tech Talk - MeetUP @ https://teams.microsoft.com/meet/239132354815321?p=0JDrmVzDiwXHiOZnpS (2026-07-16)
  - Amy 1 day vacation - Webster, Amy C @ offline (2026-07-17)
  - Refresh ISMP/ServiceNow Preview, Test - McKain, Mark @ Save your work!!! (2026-07-18)
  - ...and 13 more
- Notable email activity this week (15 total):
  - [Sent Items] RE: Security for our data - john.monroe@intel.com (2026-07-22)
  - [Sent Items] RE: Agentic Diagramming - john.monroe@intel.com (2026-07-22)
  - [Sent Items] Can you remove me as a technical contact - john.monroe@intel.com (2026-07-22)
  - ...and 12 more

## Blockers / Risks

- OneNote automation blocked by admin-consent gap: posting to the IRE team OneNote notebook requires the Microsoft Graph Notes.ReadWrite.All application scope, which IT has not approved (confirmed via a Graph 403). Workaround in place: weeklies publish as Word docs to IRE > Shared Documents > weeklies. Ask: approve Notes.ReadWrite.All, or bless the OneNote desktop COM alternative (no admin scope).

## Next Week

- Extend app-to-host mapping coverage on the remaining unresolved Dynatrace nodes; curate approved mappings via the review UI.
- AI Adoption Exploration: initialize git, widen snapshot cadence to surface real week-over-week deltas.
- Publish the plan-before-code and last-mile-authorization skills to the team.
