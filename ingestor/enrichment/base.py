"""
Enrichment base types.

Each enricher returns an EnrichmentResult — a partial company profile
plus the source name. The orchestrator merges results across sources,
tracking which source(s) provided each field.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Source(str, Enum):
    TECHCRUNCH = "techcrunch"
    VCBACKED   = "vcbacked"
    X          = "x"
    LINKEDIN   = "linkedin"   # URL generation only — no scraping
    MANUAL     = "manual"


SOURCE_LABELS = {
    Source.TECHCRUNCH: "TC",
    Source.VCBACKED:   "VCB",
    Source.X:          "X",
    Source.LINKEDIN:   "LI",
    Source.MANUAL:     "M",
}


@dataclass
class EnrichmentResult:
    """Partial company profile returned by one enricher."""
    source: Source

    # Company profile
    description: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None   # URL to LinkedIn company page
    x_url: Optional[str] = None          # URL to X/Twitter profile
    article_url: Optional[str] = None    # source article, if applicable

    # Round data
    round_name: Optional[str] = None     # "Series A", "Series B", etc.
    round_date: Optional[str] = None

    # Investors — list of {name, is_lead}
    investors: list[dict] = field(default_factory=list)

    # Confidence 0.0–1.0 (used for merge priority)
    confidence: float = 1.0


@dataclass
class MergedProfile:
    """
    Final enriched profile after merging all source results.
    Each populated field carries a list of sources that confirmed it.
    """
    description: Optional[str] = None
    description_sources: list[Source] = field(default_factory=list)

    website: Optional[str] = None
    website_sources: list[Source] = field(default_factory=list)

    linkedin_url: Optional[str] = None
    linkedin_url_sources: list[Source] = field(default_factory=list)

    x_url: Optional[str] = None
    x_url_sources: list[Source] = field(default_factory=list)

    round_name: Optional[str] = None
    round_name_sources: list[Source] = field(default_factory=list)

    investors: list[dict] = field(default_factory=list)   # [{name, is_lead, sources:[Source]}]

    article_urls: list[str] = field(default_factory=list)

    def source_badges(self) -> dict[str, list[str]]:
        """
        Returns a dict of field → [short source label] for UI display.
        e.g. {"round_name": ["TC", "VCB"], "investors": ["TC"]}
        """
        badges = {}
        for attr in ("description", "website", "linkedin_url", "x_url", "round_name"):
            sources = getattr(self, f"{attr}_sources", [])
            if sources:
                badges[attr] = [SOURCE_LABELS[s] for s in sources]
        if self.investors:
            inv_sources = {s for inv in self.investors for s in inv.get("sources", [])}
            if inv_sources:
                badges["investors"] = [SOURCE_LABELS[s] for s in sorted(inv_sources)]
        return badges

    def confidence_score(self) -> int:
        """0–100 confidence based on how many fields are multi-source confirmed."""
        confirmed = sum(
            1 for attr in ("round_name", "description", "investors")
            if len(getattr(self, f"{attr}_sources", [])) >= 2
        )
        filled = sum(
            1 for attr in ("description", "website", "linkedin_url", "round_name")
            if getattr(self, attr) is not None
        )
        investors_found = min(len(self.investors), 3)
        return min(100, (confirmed * 20) + (filled * 10) + (investors_found * 10))
