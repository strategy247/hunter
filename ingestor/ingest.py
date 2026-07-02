"""
SEC EDGAR Form D → Supabase Ingestor
--------------------------------------
Fetches Form D filings from EDGAR and upserts them into Supabase.
Run manually or on a schedule (e.g. cron, GitHub Actions).

Usage:
    python ingest.py                              # last 90 days
    python ingest.py --days 270                   # last 9 months
    python ingest.py --states CA NY TX            # filter by state
    python ingest.py --min 2000000 --max 30000000
    python ingest.py --csv-only                   # skip Supabase, output CSV
"""

import os
from dotenv import load_dotenv
load_dotenv()
import csv
import time
import logging
import argparse
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from supabase import create_client, Client

# ── Config ────────────────────────────────────────────────────────────────────

# Copy these from your Supabase project → Settings → API


DEFAULT_MIN_AMOUNT = 500_000
DEFAULT_MAX_AMOUNT = 500_000_000

TECH_KEYWORDS = [
    "software", "technology", "artificial intelligence",
    "machine learning", "fintech", "cybersecurity", "marketplace",
    "startup", "venture", "equity",
]

TECH_INDUSTRY_CODES = {
    "technology", "computers", "electronic technology",
    "health technology",
}

EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

HEADERS = {
    "User-Agent": "FormD-Tracker/1.0 brandon@livingoak.org",
    "Accept-Encoding": "gzip, deflate",
}
REQUEST_DELAY = 0.15

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class ParsedFiling:
    # leads table
    cik: str
    accession_no: str
    company_name: str
    filing_date: str
    state: str
    city: str
    amount_raised: Optional[float]
    amount_offered: Optional[float]
    industry: str
    security_type: str
    date_first_sale: str
    num_investors: Optional[int]
    edgar_url: str
    # related persons — stored separately in lead_persons
    persons: list[dict]   # [{"name": str, "roles": [str], "is_executive": bool}]


# ── EDGAR Fetchers ────────────────────────────────────────────────────────────

def search_filings(start_date: str, end_date: str, keyword: str, page: int = 0) -> dict:
    params = {
        "q": f'"{keyword}"',
        "forms": "D",
        "dateRange": "custom",
        "startdt": start_date,
        "enddt": end_date,
        "from": page * 40,
    }
    r = requests.get(EFTS_SEARCH_URL, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return r.json()


def get_all_hits(start_date: str, end_date: str, keyword: str) -> list[dict]:
    hits, page = [], 0
    while True:
        try:
            data = search_filings(start_date, end_date, keyword, page)
        except Exception as e:
            log.warning(f"Search failed for '{keyword}': {e}")
            break
        batch = data.get("hits", {}).get("hits", [])
        if not batch:
            break
        hits.extend(batch)
        total = data.get("hits", {}).get("total", {}).get("value", 0)
        if len(hits) >= total:
            break
        page += 1
    return hits


def fetch_form_d_xml(cik: str, accession_no: str) -> Optional[ET.Element]:
    acc_clean = accession_no.replace("-", "")
    url = f"{EDGAR_ARCHIVES_URL}/{cik}/{acc_clean}/primary_doc.xml"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return ET.fromstring(r.content)
    except Exception as e:
        log.warning(f"XML fetch failed {cik}/{accession_no}: {e}")
        return None


# ── Form D XML Parser ─────────────────────────────────────────────────────────

def _t(root: ET.Element, path: str, ns: str = "") -> str:
    tag = f"{{{ns}}}{path}" if ns else path
    node = root.find(f".//{tag}")
    return (node.text or "").strip() if node is not None else ""


def infer_round_name(amount: Optional[float]) -> str:
    if amount is None:
        return ""
    if amount < 500_000:
        return "Pre-Seed"
    if amount < 3_000_000:
        return "Seed"
    if amount < 15_000_000:
        return "Series A"
    if amount < 40_000_000:
        return "Series B"
    if amount < 75_000_000:
        return "Series C"
    if amount < 150_000_000:
        return "Series D"
    if amount < 300_000_000:
        return "Series E"
    return "Series F"


def parse_xml(root: ET.Element, cik: str, accession_no: str, filing_date: str) -> Optional[ParsedFiling]:
    ns = "http://www.sec.gov/edgar/document/formd"

    def t(path):
        return _t(root, path, ns) or _t(root, path)

    company_name = t("entityName") or t("issuerName")
    if not company_name:
        return None

    amount_raised = _to_float(t("totalAmountSold"))
    amount_offered = _to_float(t("totalOfferingAmount"))

    # Parse related persons
    persons = []
    for node in root.iter():
        if "relatedPersonInfo" not in node.tag:
            continue
        fn_node = node.find(f".//{{{ns}}}firstName") or node.find(".//firstName")
        ln_node = node.find(f".//{{{ns}}}lastName") or node.find(".//lastName")
        rel_node = node.find(f".//{{{ns}}}relationships") or node.find(".//relationships")
        first = (fn_node.text or "").strip() if fn_node is not None else ""
        last = (ln_node.text or "").strip() if ln_node is not None else ""
        name = f"{first} {last}".strip()
        if not name:
            continue
        roles = []
        if rel_node is not None:
            for rel in rel_node:
                tag = rel.tag.split("}")[-1] if "}" in rel.tag else rel.tag
                if (rel.text or "").strip().lower() in ("true", "1"):
                    roles.append(tag)
        is_exec = any(r in ("executiveOfficer", "officer", "director") for r in roles)
        persons.append({"name": name, "roles": roles, "is_executive": is_exec})

    edgar_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=D&dateb=&owner=include&count=10"

    return ParsedFiling(
        cik=cik,
        accession_no=accession_no,
        company_name=company_name,
        filing_date=filing_date,
        state=t("issuerAddress/stateOrCountry") or t("stateOrCountry"),
        city=t("issuerAddress/city") or t("city"),
        amount_raised=amount_raised,
        amount_offered=amount_offered,
        industry=t("industryGroupType") or t("industryGroup"),
        security_type=t("typesOfSecuritiesOffered") or t("typeOfSecurities"),
        date_first_sale=t("dateOfFirstSale"),
        num_investors=int(n) if (n := t("totalNumberAlreadyInvested")).isdigit() else None,
        edgar_url=edgar_url,
        persons=persons,
    )


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "")) if s else None
    except ValueError:
        return None


# ── Filtering ─────────────────────────────────────────────────────────────────

def passes_filters(f: ParsedFiling, min_amt: float, max_amt: float, states: Optional[list]) -> bool:
    amt = f.amount_raised or f.amount_offered
    if amt is None or not (min_amt <= amt <= max_amt):
        return False
    if states and f.state.upper() not in {s.upper() for s in states}:
        return False
    return True


def is_tech(f: ParsedFiling) -> bool:
    ind = f.industry.lower()
    return any(code in ind for code in TECH_INDUSTRY_CODES) or not ind


# ── Supabase Writer ───────────────────────────────────────────────────────────

def upsert_to_supabase(client: Client, filings: list[ParsedFiling]):
    log.info(f"Upserting {len(filings)} filings to Supabase...")
    errors = 0

    for f in filings:
        try:
            lead_row = {
                "cik": f.cik,
                "accession_no": f.accession_no,
                "company_name": f.company_name,
                "filing_date": f.filing_date or None,
                "state": f.state or None,
                "city": f.city or None,
                "amount_raised": f.amount_raised,
                "amount_offered": f.amount_offered,
                "industry": f.industry or None,
                "security_type": f.security_type or None,
                "date_first_sale": f.date_first_sale or None,
                "num_investors": f.num_investors,
                "edgar_url": f.edgar_url,
                "round_name": infer_round_name(f.amount_raised or f.amount_offered),
            }

            # Upsert lead (accession_no is the conflict key)
            result = (
                client.table("leads")
                .upsert(lead_row, on_conflict="accession_no")
                .execute()
            )

            if not result.data:
                log.warning(f"No data returned for {f.company_name}")
                errors += 1
                continue

            lead_id = result.data[0]["id"]

            # Insert persons (delete + re-insert to stay fresh)
            if f.persons:
                client.table("lead_persons").delete().eq("lead_id", lead_id).execute()
                person_rows = [
                    {
                        "lead_id": lead_id,
                        "name": p["name"],
                        "roles": p["roles"],
                        "is_executive": p["is_executive"],
                    }
                    for p in f.persons
                ]
                client.table("lead_persons").insert(person_rows).execute()

        except Exception as e:
            log.error(f"Supabase error for {f.company_name}: {e}")
            errors += 1

    log.info(f"Upsert complete. {len(filings) - errors} succeeded, {errors} errors.")


# ── CSV Writer ────────────────────────────────────────────────────────────────

def write_csv(filings: list[ParsedFiling], path: str):
    fieldnames = [
        "company_name", "filing_date", "state", "city",
        "amount_raised", "amount_offered", "round_name",
        "industry", "security_type", "date_first_sale",
        "num_investors", "executives", "cik", "accession_no", "edgar_url",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for filing in filings:
            execs = "; ".join(
                f"{p['name']} ({', '.join(p['roles'])})" for p in filing.persons
            )
            writer.writerow({
                "company_name": filing.company_name,
                "filing_date": filing.filing_date,
                "state": filing.state,
                "city": filing.city,
                "amount_raised": filing.amount_raised,
                "amount_offered": filing.amount_offered,
                "round_name": infer_round_name(filing.amount_raised or filing.amount_offered),
                "industry": filing.industry,
                "security_type": filing.security_type,
                "date_first_sale": filing.date_first_sale,
                "num_investors": filing.num_investors,
                "executives": execs,
                "cik": filing.cik,
                "accession_no": filing.accession_no,
                "edgar_url": filing.edgar_url,
            })
    log.info(f"CSV written to {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run(days=90, min_amount=DEFAULT_MIN_AMOUNT, max_amount=DEFAULT_MAX_AMOUNT,
        states=None, csv_only=False, csv_path="formd_leads.csv"):

    # use service key for ingestor — never expose in frontend
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not csv_only and (not SUPABASE_URL or not SUPABASE_SERVICE_KEY):
        raise SystemExit(
            "❌ Set SUPABASE_URL and SUPABASE_SERVICE_KEY env vars, or use --csv-only"
        )

    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=days)
    start_str, end_str = start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")

    log.info(f"Date range: {start_str} → {end_str}")
    log.info(f"Amount: ${min_amount:,.0f} – ${max_amount:,.0f}")

    # ── Collect unique filing hits ──
    all_hits: dict[str, dict] = {}
    for kw in TECH_KEYWORDS:
        log.info(f"Keyword: '{kw}'")
        for hit in get_all_hits(start_str, end_str, kw):
            src = hit.get("_source", {})
            acc = src.get("accession_no") or hit.get("_id", "").split(":")[0]
            if acc:
                all_hits[acc] = src
    log.info(f"Unique Form D filings found: {len(all_hits)}")

    # ── Fetch + parse XML ──
    parsed: list[ParsedFiling] = []
    for i, (acc_no, meta) in enumerate(all_hits.items(), 1):
        cik = str(meta.get("entity_id", "")).lstrip("0") or acc_no.split("-")[0].lstrip("0")
        if not cik:
            continue
        log.info(f"[{i}/{len(all_hits)}] {meta.get('entity_name', acc_no)}")
        root = fetch_form_d_xml(cik, acc_no)
        if root is None:
            continue
        filing = parse_xml(root, cik, acc_no, meta.get("file_date", ""))
        if filing:
            parsed.append(filing)

    # ── Filter ──
    filtered = [f for f in parsed if passes_filters(f, min_amount, max_amount, states) and is_tech(f)]
    log.info(f"After filters: {len(filtered)} filings")

    # ── Deduplicate by CIK ──
    seen: dict[str, ParsedFiling] = {}
    for f in sorted(filtered, key=lambda x: x.filing_date, reverse=True):
        if f.cik not in seen:
            seen[f.cik] = f
    final = list(seen.values())
    log.info(f"After dedup: {len(final)} unique companies")

    if csv_only:
        write_csv(final, csv_path)
    else:
        sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        upsert_to_supabase(sb, final)
        write_csv(final, csv_path)   # always write CSV as backup
    log.info("✅ Done.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--min", type=float, default=DEFAULT_MIN_AMOUNT)
    p.add_argument("--max", type=float, default=DEFAULT_MAX_AMOUNT)
    p.add_argument("--states", nargs="+")
    p.add_argument("--csv-only", action="store_true")
    p.add_argument("--csv-path", default="formd_leads.csv")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run(
        days=args.days,
        min_amount=args.min,
        max_amount=args.max,
        states=args.states,
        csv_only=args.csv_only,
        csv_path=args.csv_path,
    )


if __name__ == "__main__":
    main()
