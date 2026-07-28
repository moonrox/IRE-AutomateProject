"""weekly_auto - multi-source IRE weekly status report automation.

Collects changes from all registered sources (git repos, ADRs, file trees),
builds the weekly status report (Markdown + Word) in the standard
Progress / Blockers-Risks / Next-Week format, then publishes it to the IRE
SharePoint 'weeklies' document library and emails a copy to the author.

Source registry lives in weekly_sources.json so new data sources are declared
once and never forgotten. See run_weekly.py for the orchestrator entry point.
"""

__all__ = ["util", "collectors", "report_builder", "graph_client"]
