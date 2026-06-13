"""
VCBacked.co enricher.

Searches VCBacked.co for company data including funding stage, investors,
and basic company info. VCBacked aggregates Form D data with VC context.
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from .base import EnrichmentResult, Source

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
DELAY = 1.0
BASE_URL = "https://vcbacked.co"


def search_vcbacked(company_name: str) -> EnrichmentResult:
    """Search VCBacked.co for a company and return enrichment data."""
    result = EnrichmentResult(source=Source.VCBACKED, confidence=0.0)

    search_url = f"{BASE_URL}/search?q={requests.utils.quote(company_name)}"
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        time.sleep(DELAY)
    except Exception as e:
        log.debug(f"VCBacked search failed for '{company_name}': {e}")
        return result

    soup = BeautifulSoup(resp.text, "html.parser")
    company_url = _find_company_link(soup, company_name)

    if not company_url:
        log.debug(f"VCBacked: no result for '{company_name}'")
        return result

    if not company_url.startswith("http"):
        company_url = BASE_URL + company_url

    result.article_url = company_url
    log.info(f"VCBacked found: {company_url}")

    try:
        detail_resp = requests.get(company_url, headers=HEADERS, timeout=10)
        detail_resp.raise_for_status()
        time.sleep(DELAY)
        _parse_company_page(detail_resp.text, result)
    except Exception as e:
        log.debug(f"VCBacked detail parse failed: {e}")

    return result


def _find_company_link(soup: BeautifulSoup, company_name: str) -> str | None:
    """Find the best matching company link in search results."""
    name_lower = company_name.lower()
    # Look for result cards or list items with company names
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True).lower()
        href = link["href"]
        if name_lower in text and ("/company/" in href or "/startup/" in href or "/c/" in href):
            return href
    # Looser match — any link with the company name
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True).lower()
        if name_lower in text and link["href"] not in ("/", "#", ""):
            return link["href"]
    return None


def _parse_company_page(html: str, result: EnrichmentResult):
    """Extract company data from a VCBacked detail page."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Round stage
    stage_patterns = [
        (r"\bSeries\s+[A-E]\b", lambda m: f"Series {m.group(0).split()[-1]}"),
        (r"\bSeed\b",            lambda m: "Seed"),
        (r"\bPre-Seed\b",        lambda m: "Pre-Seed"),
    ]
    for pattern, extractor in stage_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result.round_name = extractor(match)
            result.confidence = max(result.confidence, 0.75)
            break

    # Website
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("http") and not any(
            skip in href for skip in ["vcbacked", "twitter", "x.com", "linkedin", "sec.gov"]
        ):
            result.website = href
            break

    # LinkedIn
    for link in soup.find_all("a", href=True):
        if "linkedin.com/company" in link["href"]:
            result.linkedin_url = link["href"]
            break

    # X / Twitter
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if ("twitter.com/" in href or "x.com/" in href) and "/status/" not in href:
            result.x_url = href
            break

    # Investors — look for labeled sections
    investor_section = soup.find(
        lambda tag: tag.name in ("div", "section", "ul") and
        any(kw in (tag.get_text() or "").lower() for kw in ["investor", "backed by", "funded by"])
    )
    if investor_section:
        for item in investor_section.find_all(["li", "span", "p"]):
            name = item.get_text(strip=True)
            if 2 < len(name) < 60 and name not in [i["name"] for i in result.investors]:
                result.investors.append({"name": name, "is_lead": False})

    # Description
    desc_tag = (
        soup.find("meta", attrs={"name": "description"}) or
        soup.find("meta", attrs={"property": "og:description"})
    )
    if desc_tag and desc_tag.get("content"):
        result.description = desc_tag["content"][:500]
        result.confidence = max(result.confidence, 0.6)
