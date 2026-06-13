"""
X (Twitter) enricher — two modes:

1. PROFILE SEARCH (enrichment)
   Given a company name, finds their X profile and checks for funding
   announcements in recent tweets. Uses the free-tier X API v2.
   Rate limit: 500k tweets/month read on Basic ($100/mo) — skip if no key.

2. VC MONITOR (real-time discovery — separate use case)
   Monitors a curated list of VC accounts for new funding announcements
   BEFORE they hit TechCrunch or EDGAR. This is your early outreach edge.
   Run separately: python -m enrichment.x_search --monitor

X API tiers (as of 2026):
  Free: read own tweets only (useless for this)
  Basic: $100/mo — 10k tweets/month read (works for light enrichment)
  Pro:   $5000/mo — full search (overkill)

Fallback when no API key: generates a direct X search URL for manual review.
"""

import os
import re
import time
import logging
import requests
from urllib.parse import quote
from .base import EnrichmentResult, Source

log = logging.getLogger(__name__)

X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "")

# Top VC accounts to monitor for early-signal round announcements
# Following these on X is also the manual version of this strategy
VC_MONITOR_ACCOUNTS = [
    "a16z", "sequoia", "ycombinator", "Kleiner_Perkins",
    "BessemerVP", "AccelPartners", "LightspeedVP", "gcvp",
    "firstround", "FoundersFund", "IndexVentures", "InsightPartners",
    "GVteam", "GeneralCatalyst", "NFX", "TigerGlobal",
    "coatue", "dragoneer", "USVentures", "BattteryVentures",
    "GreylockVC", "SoftBank_Group", "CRVvc", "TrueVentures",
]

FUNDING_KEYWORDS = [
    "raises", "raised", "funding", "series a", "series b",
    "seed round", "led by", "announces", "backed by", "new funding",
    "million", "investment", "closes",
]


# ── Enrichment mode ───────────────────────────────────────────────────────────

def search_x_profile(company_name: str) -> EnrichmentResult:
    """
    Find a company's X profile and check for funding tweet signals.
    Returns enrichment data if API key is available, otherwise returns
    a search URL for manual review.
    """
    result = EnrichmentResult(source=Source.X, confidence=0.0)

    # Always generate a search URL — useful even without API key
    search_query = f"{company_name} funding"
    result.x_url = f"https://x.com/search?q={quote(search_query)}&f=live"

    if not X_BEARER_TOKEN:
        log.debug(f"X: No API key — generated search URL for '{company_name}'")
        result.confidence = 0.1   # Low confidence — URL only, not verified
        return result

    # API-based search
    try:
        return _api_search(company_name, result)
    except Exception as e:
        log.warning(f"X API search failed for '{company_name}': {e}")
        return result


def _api_search(company_name: str, result: EnrichmentResult) -> EnrichmentResult:
    """Use X API v2 to search for company funding tweets."""
    query = f'"{company_name}" ({" OR ".join(FUNDING_KEYWORDS[:5])}) -is:retweet lang:en'
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
    params = {
        "query": query,
        "max_results": 10,
        "tweet.fields": "created_at,author_id,entities",
        "expansions": "author_id",
        "user.fields": "name,username,verified",
    }

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    time.sleep(0.5)

    data = resp.json()
    tweets = data.get("data", [])
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

    if not tweets:
        return result

    for tweet in tweets:
        text = tweet.get("text", "")
        text_lower = text.lower()
        author = users.get(tweet.get("author_id", ""), {})
        author_name = author.get("name", "")

        # Check if tweet is from a VC account (high confidence signal)
        is_vc_tweet = author.get("username", "").lower() in {a.lower() for a in VC_MONITOR_ACCOUNTS}

        # Extract round name
        if not result.round_name:
            for kw, round_name in [("series a", "Series A"), ("series b", "Series B"),
                                    ("seed", "Seed"), ("pre-seed", "Pre-Seed")]:
                if kw in text_lower:
                    result.round_name = round_name
                    result.confidence = max(result.confidence, 0.85 if is_vc_tweet else 0.6)
                    break

        # Extract lead investor from VC tweet
        if is_vc_tweet and author_name not in [i["name"] for i in result.investors]:
            result.investors.append({"name": author_name, "is_lead": True})
            result.confidence = max(result.confidence, 0.9)

        # Profile URL
        if not result.x_url or "search" in result.x_url:
            username = author.get("username")
            if username:
                result.x_url = f"https://x.com/{username}"

    return result


# ── VC Monitor mode (real-time discovery) ─────────────────────────────────────

def monitor_vc_announcements(max_results: int = 100) -> list[dict]:
    """
    Poll VC accounts for recent funding announcement tweets.
    Returns a list of potential companies to add to the pipeline.

    This is your early-signal advantage — catches rounds before Form D or TechCrunch.
    Run on a schedule (daily) alongside the EDGAR ingestor.

    Requires X_BEARER_TOKEN env var.
    """
    if not X_BEARER_TOKEN:
        log.warning(
            "X_BEARER_TOKEN not set. To use VC monitoring:\n"
            "  1. Sign up for X Basic API ($100/mo) at developer.twitter.com\n"
            "  2. export X_BEARER_TOKEN=your_token\n\n"
            "Manual alternative: Follow these accounts on X and check daily:\n" +
            "\n".join(f"  https://x.com/{account}" for account in VC_MONITOR_ACCOUNTS[:10])
        )
        return []

    announcements = []
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

    # Build a query that searches across all VC accounts
    accounts_query = " OR ".join(f"from:{a}" for a in VC_MONITOR_ACCOUNTS[:20])
    funding_query = " OR ".join(FUNDING_KEYWORDS[:6])
    query = f"({accounts_query}) ({funding_query}) -is:retweet lang:en"

    url = "https://api.twitter.com/2/tweets/search/recent"
    params = {
        "query": query,
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,author_id,text",
        "expansions": "author_id",
        "user.fields": "name,username",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

        for tweet in data.get("data", []):
            text = tweet["text"]
            author = users.get(tweet.get("author_id", ""), {})
            companies = _extract_company_names(text)
            for company in companies:
                announcements.append({
                    "company_name": company,
                    "tweet_text": text,
                    "tweet_url": f"https://x.com/i/web/status/{tweet['id']}",
                    "vc_account": author.get("username", ""),
                    "vc_name": author.get("name", ""),
                    "created_at": tweet.get("created_at", ""),
                    "source": "x_monitor",
                })
    except Exception as e:
        log.error(f"VC monitor failed: {e}")

    log.info(f"X monitor found {len(announcements)} potential announcements")
    return announcements


def _extract_company_names(tweet_text: str) -> list[str]:
    """
    Heuristic company name extraction from tweet text.
    Looks for capitalized phrases near funding keywords.
    """
    companies = []
    # Pattern: capitalized word(s) before "raises", "closes", "announces" etc.
    for pattern in [
        r"([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)?)\s+(?:raises|raised|closes|announced|secures)",
        r"(?:invested in|backed)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)?)",
        r"portfolio company\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)?)",
    ]:
        for match in re.finditer(pattern, tweet_text):
            name = match.group(1).strip()
            if len(name) > 2 and name not in companies:
                companies.append(name)
    return companies


# ── LinkedIn URL generator (no scraping — just search link) ───────────────────

def generate_linkedin_search_url(company_name: str, state: str = "") -> str:
    """
    Generate a LinkedIn search URL for manual review.
    LinkedIn scraping is not practical; this opens the right search in browser.
    """
    query = f"{company_name} {state}".strip()
    return f"https://www.linkedin.com/search/results/companies/?keywords={quote(query)}"
