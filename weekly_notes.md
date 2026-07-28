# Weekly Status Notes

Edit this file any time. The automated weekly report reads the two tagged
sections below and drops their bullet lines straight into the Word/Markdown
report. Everything under [Blockers] becomes the "Blockers/Risks:" section;
everything under [Next Week] becomes the "Next Week:" section. The "Progress:"
section is generated automatically from git/ADR/file activity, so you don't
need to maintain it by hand.

Leave a section empty to get a sensible default ("None." / "TBD.").

[Blockers]
- OneNote automation blocked by admin-consent gap: posting to the IRE team OneNote notebook requires the Microsoft Graph Notes.ReadWrite.All application scope, which IT has not approved (confirmed via a Graph 403). Workaround in place: weeklies publish as Word docs to IRE > Shared Documents > weeklies. Ask: approve Notes.ReadWrite.All, or bless the OneNote desktop COM alternative (no admin scope).

[Next Week]
- Extend app-to-host mapping coverage on the remaining unresolved Dynatrace nodes; curate approved mappings via the review UI.
- AI Adoption Exploration: initialize git, widen snapshot cadence to surface real week-over-week deltas.
- Publish the plan-before-code and last-mile-authorization skills to the team.
