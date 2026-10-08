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
from typing import Optional
from supabase import create_client, Client
from parse_formd import parse_xml_full

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


# ── Form D XML Parser (see parse_formd.py) ────────────────────────────────────

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


# ── Filtering ─────────────────────────────────────────────────────────────────

def passes_filters(f: dict, min_amt: float, max_amt: float, states: Optional[list]) -> bool:
    amt = f["amount_raised"] or f["amount_offered"]
    if amt is None or not (min_amt <= amt <= max_amt):
        return False
    if states and (f["state"] or "").upper() not in {s.upper() for s in states}:
        return False
    return True


def is_tech(f: dict) -> bool:
    ind = (f["industry"] or "").lower()
    return any(code in ind for code in TECH_INDUSTRY_CODES) or not ind


# ── Supabase Writer ───────────────────────────────────────────────────────────

def upsert_to_supabase(client: Client, filings: list[dict]):
    log.info(f"Upserting {len(filings)} filings to Supabase...")
    errors = 0

    for f in filings:
        try:
            lead_row = {k: v for k, v in f.items() if k != "_persons"}
            lead_row["round_name"] = infer_round_name(f["amount_raised"] or f["amount_offered"])
            persons = f["_persons"]

            # Upsert lead (accession_no is the conflict key)
            result = (
                client.table("leads")
                .upsert(lead_row, on_conflict="accession_no")
                .execute()
            )

            if not result.data:
                log.warning(f"No data returned for {f['company_name']}")
                errors += 1
                continue

            lead_id = result.data[0]["id"]

            # Insert persons (delete + re-insert to stay fresh)
            if persons:
                client.table("lead_persons").delete().eq("lead_id", lead_id).execute()
                person_rows = [
                    {
                        "lead_id": lead_id,
                        "name": p["name"],
                        "roles": p["roles"],
                        "is_executive": p["is_executive"],
                    }
                    for p in persons
                ]
                client.table("lead_persons").insert(person_rows).execute()

        except Exception as e:
            log.error(f"Supabase error for {f['company_name']}: {e}")
            errors += 1

    log.info(f"Upsert complete. {len(filings) - errors} succeeded, {errors} errors.")


# ── CSV Writer ────────────────────────────────────────────────────────────────

def write_csv(filings: list[dict], path: str):
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
                f"{p['name']} ({', '.join(p['roles'])})" for p in filing["_persons"]
            )
            writer.writerow({
                "company_name": filing["company_name"],
                "filing_date": filing["filing_date"],
                "state": filing["state"],
                "city": filing["city"],
                "amount_raised": filing["amount_raised"],
                "amount_offered": filing["amount_offered"],
                "round_name": infer_round_name(filing["amount_raised"] or filing["amount_offered"]),
                "industry": filing["industry"],
                "security_type": filing["security_type"],
                "date_first_sale": filing["date_first_sale"],
                "num_investors": filing["num_investors"],
                "executives": execs,
                "cik": filing["cik"],
                "accession_no": filing["accession_no"],
                "edgar_url": filing["edgar_url"],
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
    parsed: list[dict] = []
    for i, (acc_no, meta) in enumerate(all_hits.items(), 1):
        cik = str(meta.get("entity_id", "")).lstrip("0") or acc_no.split("-")[0].lstrip("0")
        if not cik:
            continue
        log.info(f"[{i}/{len(all_hits)}] {meta.get('entity_name', acc_no)}")
        root = fetch_form_d_xml(cik, acc_no)
        if root is None:
            continue
        filing = parse_xml_full(root, cik, acc_no, meta.get("file_date", ""))
        if filing:
            parsed.append(filing)

    # ── Filter ──
    filtered = [f for f in parsed if passes_filters(f, min_amount, max_amount, states) and is_tech(f)]
    log.info(f"After filters: {len(filtered)} filings")

    # ── Deduplicate by CIK ──
    seen: dict[str, dict] = {}
    for f in sorted(filtered, key=lambda x: x["filing_date"] or "", reverse=True):
        if f["cik"] not in seen:
            seen[f["cik"]] = f
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
