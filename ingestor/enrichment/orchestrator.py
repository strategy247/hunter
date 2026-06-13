"""
Enrichment orchestrator.

Runs each enricher in order, merges results, and writes the
merged profile + source attribution back to Supabase.

Fallback chain per field:
  1. TechCrunch  (best for investor names, round context, company description)
  2. VCBacked.co (confirms round stage, adds website/social links)
  3. X search    (early signal, VC account verification)
  4. LinkedIn    (URL generation only — no scraping)

Fields are populated from the first source that provides them,
but ALL sources that confirm a field are tracked for confidence display.
"""

import logging
import time
from dataclasses import asdict

from .base import EnrichmentResult, MergedProfile, Source
from .techcrunch import search_techcrunch
from .vcbacked import search_vcbacked
from .x_search import search_x_profile, generate_linkedin_search_url

log = logging.getLogger(__name__)


def enrich_company(
    company_name: str,
    state: str = "",
    filing_date: str = "",
    use_x: bool = False,   # Requires X_BEARER_TOKEN; set False if you don't have one
) -> MergedProfile:
    """
    Run all enrichers for a company and return a merged profile
    with source attribution on every field.
    """
    log.info(f"Enriching: {company_name} ({state})")
    results: list[EnrichmentResult] = []

    # ── Run enrichers ──
    tc = search_techcrunch(company_name, filing_date)
    results.append(tc)
    log.debug(f"  TC: confidence={tc.confidence:.2f}, round={tc.round_name}, investors={len(tc.investors)}")

    time.sleep(0.5)

    vcb = search_vcbacked(company_name)
    results.append(vcb)
    log.debug(f"  VCB: confidence={vcb.confidence:.2f}, round={vcb.round_name}, investors={len(vcb.investors)}")

    if use_x:
        time.sleep(0.5)
        x = search_x_profile(company_name)
        results.append(x)
        log.debug(f"  X: confidence={x.confidence:.2f}, round={x.round_name}")
    else:
        # Still generate X search URL (no API call needed)
        from .x_search import EnrichmentResult as ER
        x_url_only = EnrichmentResult(source=Source.X, confidence=0.05)
        from .x_search import quote
        x_url_only.x_url = f"https://x.com/search?q={quote(company_name + ' funding')}&f=live"
        results.append(x_url_only)

    # Always generate LinkedIn search URL
    li = EnrichmentResult(source=Source.LINKEDIN, confidence=0.05)
    li.linkedin_url = generate_linkedin_search_url(company_name, state)
    results.append(li)

    return _merge(results)


def _merge(results: list[EnrichmentResult]) -> MergedProfile:
    """
    Merge enrichment results into a single profile.
    First source with a value wins; all sources that confirm are tracked.
    """
    profile = MergedProfile()

    # ── Scalar fields: first-wins + track all confirmations ──
    scalar_fields = ("description", "website", "linkedin_url", "x_url", "round_name")

    for field in scalar_fields:
        sources_field = f"{field}_sources"
        for result in results:
            value = getattr(result, field, None)
            if value:
                current = getattr(profile, field)
                if current is None:
                    setattr(profile, field, value)
                # Track confirmation regardless
                current_sources: list = getattr(profile, sources_field)
                if result.source not in current_sources:
                    current_sources.append(result.source)

    # ── Investors: merge by name, track all confirming sources ──
    investor_map: dict[str, dict] = {}
    for result in results:
        for inv in result.investors:
            name = inv["name"].strip()
            if not name:
                continue
            if name not in investor_map:
                investor_map[name] = {
                    "name": name,
                    "is_lead": inv.get("is_lead", False),
                    "sources": [result.source],
                }
            else:
                # If any source says is_lead, mark as lead
                if inv.get("is_lead"):
                    investor_map[name]["is_lead"] = True
                if result.source not in investor_map[name]["sources"]:
                    investor_map[name]["sources"].append(result.source)

    # Sort: leads first, then by number of confirming sources (multi-source = more confident)
    profile.investors = sorted(
        investor_map.values(),
        key=lambda i: (not i["is_lead"], -len(i["sources"]))
    )

    # ── Article URLs ──
    profile.article_urls = [
        r.article_url for r in results if r.article_url
    ]

    score = profile.confidence_score()
    log.info(f"Enrichment complete. Confidence: {score}/100 | "
             f"Round: {profile.round_name} | Investors: {len(profile.investors)}")

    return profile


def write_enrichment_to_supabase(client, lead_id: str, profile: MergedProfile):
    """
    Write enrichment results back to Supabase.
    Updates the leads table and inserts/replaces investor records.
    """
    badges = profile.source_badges()

    # Build lead update
    lead_update = {}
    if profile.description:
        lead_update["description"] = profile.description
    if profile.website:
        lead_update["website"] = profile.website
    if profile.linkedin_url:
        lead_update["linkedin_url"] = profile.linkedin_url
    if profile.round_name:
        lead_update["round_name"] = profile.round_name

    # Store source badges as JSONB
    lead_update["enrichment_sources"] = {
        field: [s.value for s in sources]
        for field, sources in [
            ("description", profile.description_sources),
            ("website", profile.website_sources),
            ("linkedin_url", profile.linkedin_url_sources),
            ("x_url", profile.x_url_sources),
            ("round_name", profile.round_name_sources),
            ("investors", list({s for inv in profile.investors for s in inv.get("sources", [])})),
        ]
        if sources
    }
    lead_update["enrichment_sources"]["x_url"] = (
        profile.x_url_sources or []
    )
    if profile.x_url:
        lead_update["x_url"] = profile.x_url

    lead_update["enrichment_confidence"] = profile.confidence_score()
    lead_update["article_urls"] = profile.article_urls

    if lead_update:
        client.table("leads").update(lead_update).eq("id", lead_id).execute()
        log.debug(f"Updated lead {lead_id} with enrichment data")

    # Replace investor records from enrichment sources
    if profile.investors:
        # Remove previously enriched (non-manual) investor records
        client.table("lead_investors").delete().eq("lead_id", lead_id).neq("source", "manual").execute()

        investor_rows = []
        for inv in profile.investors:
            # Use the highest-confidence source as the stored source
            sources = inv.get("sources", [Source.TECHCRUNCH])
            primary_source = sources[0].value if sources else "techcrunch"
            investor_rows.append({
                "lead_id": lead_id,
                "investor_name": inv["name"],
                "is_lead": inv.get("is_lead", False),
                "source": primary_source,
                "confirmed_by": [s.value for s in sources],   # all confirming sources
            })

        if investor_rows:
            client.table("lead_investors").insert(investor_rows).execute()
            log.debug(f"Inserted {len(investor_rows)} investors for lead {lead_id}")
