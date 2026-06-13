"""
TechCrunch enricher — uses WordPress REST API (no scraping, no HTML parsing).
Free, structured JSON, no key required.
"""
import time, logging, requests
from .base import EnrichmentResult, Source

log = logging.getLogger(__name__)
BASE = "https://techcrunch.com/wp-json/wp/v2"
HEADERS = {"User-Agent": "FormD-Tracker/1.0 brandon@livingoak.org"}
DELAY = 1.0

ROUND_KEYWORDS = {"series a":"Series A","series b":"Series B","series c":"Series C+","seed round":"Seed","pre-seed":"Pre-Seed","seed funding":"Seed"}
LEAD_PATTERNS = [
    r"led by ([A-Z][A-Za-z\s&]+?)(?:,|\sand\s|\.|$)",
    r"([A-Z][A-Za-z\s&]+?) led the round",
]
import re
VC_NAMES = re.compile(r"((?:[A-Z][A-Za-z]+\s?){1,3}(?:Capital|Ventures|VC|Partners|Investments|Fund|Catalyst|Sequoia|Bessemer|Kleiner|Lightspeed|Tiger|a16z|GV|NEA|Index|Insight|Battery|IVP|Andreessen Horowitz|Founders Fund|Coatue|General Catalyst|Y Combinator))")

def search_techcrunch(company_name: str, filing_date: str = "") -> EnrichmentResult:
    result = EnrichmentResult(source=Source.TECHCRUNCH, confidence=0.0)
    try:
        resp = requests.get(f"{BASE}/posts", params={"search": f"{company_name} funding", "per_page": 5}, headers=HEADERS, timeout=10)
        resp.raise_for_status(); time.sleep(DELAY)
        posts = resp.json()
    except Exception as e:
        log.debug(f"TC WP API failed for '{company_name}': {e}"); return result

    name_lower = company_name.lower()
    best = next((p for p in posts if name_lower in p.get("title",{}).get("rendered","").lower()
                 and any(kw in p.get("title",{}).get("rendered","").lower() for kw in ["funding","raises","million","series"])), None)
    if not best:
        best = next((p for p in posts), None)
    if not best:
        return result

    result.article_url = best.get("link")
    excerpt = best.get("excerpt", {}).get("rendered", "")
    content = re.sub(r"<[^>]+>", " ", best.get("content", {}).get("rendered", "") or excerpt)

    # Round name
    for kw, rn in ROUND_KEYWORDS.items():
        if kw in content.lower():
            result.round_name = rn; result.confidence = 0.8; break

    # Lead investor
    for pat in LEAD_PATTERNS:
        m = re.search(pat, content, re.IGNORECASE)
        if m:
            name = m.group(1).strip().rstrip(",")
            if 3 < len(name) < 60:
                result.investors.append({"name": name, "is_lead": True})
                result.confidence = max(result.confidence, 0.9); break

    # All VC names
    for m in VC_NAMES.finditer(content):
        name = m.group(1).strip()
        if name not in [i["name"] for i in result.investors]:
            result.investors.append({"name": name, "is_lead": False})

    # Description from excerpt
    clean_excerpt = re.sub(r"<[^>]+>", "", excerpt).strip()
    if clean_excerpt and company_name.lower() in clean_excerpt.lower():
        result.description = clean_excerpt[:400]
        result.confidence = max(result.confidence, 0.7)

    log.info(f"TC: found article for '{company_name}' | round={result.round_name} | investors={len(result.investors)}")
    return result
