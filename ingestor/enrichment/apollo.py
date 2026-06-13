"""
Apollo.io enricher — finds verified executive contact info.

Free tier: 50 email lookups/month (no card required).
Paid:      $49/month for 10k credits.

Setup:
  1. Sign up at apollo.io (free)
  2. Settings → Integrations → API → copy key
  3. export APOLLO_API_KEY=your_key

What it adds:
  - Verified email for named executives from Form D
  - LinkedIn URL for the contact
  - Job title confirmation
"""

import os
import time
import logging
import requests
from .base import EnrichmentResult, Source

log = logging.getLogger(__name__)

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
BASE_URL = "https://api.apollo.io/v1"
DELAY = 0.5


def enrich_contacts(
    company_name: str,
    domain: str = "",
    executives: list[dict] = None,  # [{"name": str, "roles": [str]}]
) -> EnrichmentResult:
    """
    Look up verified contact info for a company's executives on Apollo.
    Returns enriched executive data with emails and LinkedIn URLs.
    """
    result = EnrichmentResult(source=Source.MANUAL, confidence=0.0)
    result.investors = []  # We'll reuse investors list for contacts here

    if not APOLLO_API_KEY:
        log.debug("Apollo: no API key — skipping contact enrichment")
        log.info(
            "To enable contact enrichment:\n"
            "  1. Sign up free at https://apollo.io\n"
            "  2. export APOLLO_API_KEY=your_key\n"
            "  Free tier: 50 lookups/month"
        )
        return result

    # Step 1: Find the company in Apollo's database
    company_id = _find_company(company_name, domain)
    if not company_id:
        log.debug(f"Apollo: company not found for '{company_name}'")
        return result

    # Step 2: Get people at the company (filter to relevant titles)
    contacts = _get_people(company_id, executives)
    if not contacts:
        return result

    # Step 3: Enrich — request verified emails for each contact
    enriched = []
    for contact in contacts[:5]:  # Cap at 5 to preserve free tier credits
        email_data = _get_email(contact.get("id", ""))
        enriched.append({
            "name": f"{contact.get('first_name','')} {contact.get('last_name','')}".strip(),
            "title": contact.get("title", ""),
            "email": email_data.get("email"),
            "email_status": email_data.get("email_status"),  # "verified", "likely", etc.
            "linkedin_url": contact.get("linkedin_url"),
            "is_decision_maker": _is_decision_maker(contact.get("title", "")),
        })
        time.sleep(DELAY)

    result.confidence = 0.9 if any(c["email"] for c in enriched) else 0.3

    # Store enriched contacts in a custom attribute
    result._contacts = enriched
    log.info(f"Apollo: {len(enriched)} contacts found for '{company_name}', "
             f"{sum(1 for c in enriched if c['email'])} with verified emails")

    return result, enriched


def _find_company(name: str, domain: str = "") -> str | None:
    """Find Apollo company ID by name or domain."""
    payload = {"q_organization_name": name, "page": 1, "per_page": 5}
    if domain:
        payload["q_organization_domains[]"] = domain

    try:
        resp = requests.post(
            f"{BASE_URL}/mixed_companies/search",
            json=payload,
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": APOLLO_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        time.sleep(DELAY)
        orgs = resp.json().get("organizations", [])
        name_lower = name.lower()
        # Exact match first, then first result
        match = next((o for o in orgs if name_lower in (o.get("name") or "").lower()), orgs[0] if orgs else None)
        return match["id"] if match else None
    except Exception as e:
        log.debug(f"Apollo company search failed: {e}")
        return None


def _get_people(company_id: str, executives: list[dict] = None) -> list[dict]:
    """Get people at a company, prioritizing C-suite and product roles."""
    TARGET_TITLES = [
        "Chief Product Officer", "CPO", "VP of Product", "VP Product",
        "Head of Product", "Director of Product", "Chief Executive Officer",
        "CEO", "Co-Founder", "Founder", "Chief Technology Officer", "CTO",
        "Chief Operating Officer", "COO",
    ]

    payload = {
        "q_organization_ids[]": company_id,
        "person_titles[]": TARGET_TITLES[:8],  # API limit
        "page": 1,
        "per_page": 10,
    }

    # If we have executive names from Form D, add them to improve matching
    if executives:
        first_names = [e["name"].split()[0] for e in executives if e.get("name")]
        if first_names:
            payload["q_keywords"] = " OR ".join(first_names[:3])

    try:
        resp = requests.post(
            f"{BASE_URL}/mixed_people/search",
            json=payload,
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": APOLLO_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        time.sleep(DELAY)
        return resp.json().get("people", [])
    except Exception as e:
        log.debug(f"Apollo people search failed: {e}")
        return []


def _get_email(person_id: str) -> dict:
    """Request a verified email for a person (uses 1 credit)."""
    if not person_id:
        return {}
    try:
        resp = requests.post(
            f"{BASE_URL}/people/match",
            json={"id": person_id, "reveal_personal_emails": False},
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": APOLLO_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        person = resp.json().get("person", {})
        return {
            "email": person.get("email"),
            "email_status": person.get("email_status"),
        }
    except Exception as e:
        log.debug(f"Apollo email lookup failed for {person_id}: {e}")
        return {}


def _is_decision_maker(title: str) -> bool:
    """Return True if the title suggests a hiring/consulting decision maker."""
    title_lower = title.lower()
    keywords = ["cpo", "ceo", "cto", "coo", "vp", "chief", "head of product",
                "director of product", "founder", "president"]
    return any(kw in title_lower for kw in keywords)


def write_contacts_to_supabase(client, lead_id: str, contacts: list[dict]):
    """
    Write Apollo-enriched contacts to Supabase.
    These go into lead_persons with email/linkedin enrichment.
    """
    if not contacts:
        return

    # Add email/linkedin columns if enriching existing persons
    for contact in contacts:
        if not contact.get("name"):
            continue
        # Try to match to existing person record by name
        existing = (
            client.table("lead_persons")
            .select("id, name")
            .eq("lead_id", lead_id)
            .ilike("name", f"%{contact['name'].split()[0]}%")
            .execute()
        )
        if existing.data:
            updates = {}
            if contact.get("email"):
                updates["email"] = contact["email"]
                updates["email_status"] = contact.get("email_status")
            if contact.get("linkedin_url"):
                updates["linkedin_url"] = contact["linkedin_url"]
            if updates:
                client.table("lead_persons").update(updates).eq("id", existing.data[0]["id"]).execute()
        else:
            # Insert new person record with full data
            client.table("lead_persons").insert({
                "lead_id": lead_id,
                "name": contact["name"],
                "roles": [contact.get("title", "")],
                "is_executive": contact.get("is_decision_maker", False),
                "email": contact.get("email"),
                "email_status": contact.get("email_status"),
                "linkedin_url": contact.get("linkedin_url"),
            }).execute()

    log.info(f"Wrote {len(contacts)} Apollo contacts for lead {lead_id}")
