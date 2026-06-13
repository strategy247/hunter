"""
CRM Integration — Salesforce and HubSpot.

Both Salesforce and HubSpot are available as MCP connectors in the frontend.
This module handles the backend API routes that the frontend calls when
the user clicks "Push to Salesforce" or "Push to HubSpot".

Setup:
  Salesforce: Settings → Integrations → Connected Apps → get client_id/secret
  HubSpot:    Settings → Integrations → API Key (or OAuth)

Environment variables:
  SALESFORCE_CLIENT_ID
  SALESFORCE_CLIENT_SECRET
  SALESFORCE_USERNAME
  SALESFORCE_PASSWORD
  SALESFORCE_SECURITY_TOKEN
  HUBSPOT_ACCESS_TOKEN

Usage (from Next.js API route):
  POST /api/crm/push
  Body: { leadId, platform: "salesforce" | "hubspot" }
"""

import os
import logging
import requests

log = logging.getLogger(__name__)

# ── Salesforce ────────────────────────────────────────────────────────────────

SF_CLIENT_ID     = os.environ.get("SALESFORCE_CLIENT_ID", "")
SF_CLIENT_SECRET = os.environ.get("SALESFORCE_CLIENT_SECRET", "")
SF_USERNAME      = os.environ.get("SALESFORCE_USERNAME", "")
SF_PASSWORD      = os.environ.get("SALESFORCE_PASSWORD", "")
SF_TOKEN         = os.environ.get("SALESFORCE_SECURITY_TOKEN", "")


def push_to_salesforce(lead: dict, contacts: list[dict] = None) -> dict:
    """
    Push a Form D lead to Salesforce as an Account + Opportunity + Contacts.
    Returns {"success": bool, "account_id": str, "opportunity_id": str}
    """
    access_token, instance_url = _sf_authenticate()
    if not access_token:
        return {"success": False, "error": "Salesforce auth failed — check env vars"}

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    base = f"{instance_url}/services/data/v58.0"

    # Create or update Account
    account = {
        "Name": lead["company_name"],
        "BillingState": lead.get("state", ""),
        "BillingCity": lead.get("city", ""),
        "Website": lead.get("website", ""),
        "Description": lead.get("description", ""),
        "NumberOfEmployees": None,
        "Industry": lead.get("industry", "Technology"),
        "Type": "Prospect",
    }
    acct_resp = requests.post(f"{base}/sobjects/Account/", json=account, headers=headers)
    acct_resp.raise_for_status()
    account_id = acct_resp.json()["id"]

    # Create Opportunity
    opportunity = {
        "Name": f"{lead['company_name']} — {lead.get('outreach_type', 'Job/Consulting')}",
        "AccountId": account_id,
        "StageName": _map_status_to_sf_stage(lead.get("outreach_status", "new")),
        "CloseDate": _close_date_estimate(),
        "Amount": lead.get("amount_raised") or lead.get("amount_offered"),
        "Description": f"Source: SEC Form D · Filed: {lead.get('filing_date','')} · Round: {lead.get('round_name','')}",
        "LeadSource": "SEC EDGAR Form D",
        "Type": lead.get("outreach_type", "New Business").replace("_", " ").title(),
    }
    opp_resp = requests.post(f"{base}/sobjects/Opportunity/", json=opportunity, headers=headers)
    opp_resp.raise_for_status()
    opportunity_id = opp_resp.json()["id"]

    # Create Contacts
    contact_ids = []
    for c in (contacts or []):
        if not c.get("name"):
            continue
        parts = c["name"].rsplit(" ", 1)
        contact = {
            "AccountId": account_id,
            "FirstName": parts[0] if len(parts) > 1 else "",
            "LastName": parts[-1],
            "Title": c.get("title", ""),
            "Email": c.get("email", ""),
        }
        c_resp = requests.post(f"{base}/sobjects/Contact/", json=contact, headers=headers)
        if c_resp.ok:
            contact_ids.append(c_resp.json()["id"])

    log.info(f"Salesforce: pushed {lead['company_name']} — account={account_id} opp={opportunity_id}")
    return {
        "success": True,
        "platform": "salesforce",
        "account_id": account_id,
        "opportunity_id": opportunity_id,
        "contact_ids": contact_ids,
        "url": f"{instance_url}/{opportunity_id}",
    }


def _sf_authenticate() -> tuple[str, str]:
    """Get Salesforce access token via username-password flow."""
    if not all([SF_CLIENT_ID, SF_CLIENT_SECRET, SF_USERNAME, SF_PASSWORD]):
        log.warning("Salesforce env vars not set")
        return "", ""
    try:
        resp = requests.post("https://login.salesforce.com/services/oauth2/token", data={
            "grant_type": "password",
            "client_id": SF_CLIENT_ID,
            "client_secret": SF_CLIENT_SECRET,
            "username": SF_USERNAME,
            "password": SF_PASSWORD + SF_TOKEN,
        })
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], data["instance_url"]
    except Exception as e:
        log.error(f"Salesforce auth failed: {e}")
        return "", ""


def _map_status_to_sf_stage(status: str) -> str:
    return {
        "new": "Prospecting",
        "reviewing": "Qualification",
        "contacted": "Needs Analysis",
        "responded": "Value Proposition",
        "interviewing": "Perception Analysis",
        "offer": "Proposal/Price Quote",
        "closed_won": "Closed Won",
        "not_interested": "Closed Lost",
    }.get(status, "Prospecting")


def _close_date_estimate() -> str:
    from datetime import datetime, timedelta
    return (datetime.today() + timedelta(days=90)).strftime("%Y-%m-%d")


# ── HubSpot ───────────────────────────────────────────────────────────────────

HS_ACCESS_TOKEN = os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
HS_BASE = "https://api.hubapi.com"


def push_to_hubspot(lead: dict, contacts: list[dict] = None) -> dict:
    """
    Push a Form D lead to HubSpot as a Company + Deal + Contacts.
    Returns {"success": bool, "company_id": str, "deal_id": str}
    """
    if not HS_ACCESS_TOKEN:
        return {"success": False, "error": "HUBSPOT_ACCESS_TOKEN not set"}

    headers = {"Authorization": f"Bearer {HS_ACCESS_TOKEN}", "Content-Type": "application/json"}

    # Create Company
    company_payload = {
        "properties": {
            "name": lead["company_name"],
            "city": lead.get("city", ""),
            "state": lead.get("state", ""),
            "website": lead.get("website", ""),
            "description": lead.get("description", ""),
            "industry": lead.get("industry", "TECHNOLOGY"),
            "numberofemployees": "",
            "hs_lead_status": "NEW",
        }
    }
    co_resp = requests.post(f"{HS_BASE}/crm/v3/objects/companies", json=company_payload, headers=headers)
    co_resp.raise_for_status()
    company_id = co_resp.json()["id"]

    # Create Deal
    deal_payload = {
        "properties": {
            "dealname": f"{lead['company_name']} — {lead.get('outreach_type','Job/Consulting').replace('_',' ').title()}",
            "dealstage": _map_status_to_hs_stage(lead.get("outreach_status", "new")),
            "amount": str(lead.get("amount_raised") or lead.get("amount_offered") or 0),
            "closedate": _close_date_estimate(),
            "pipeline": "default",
            "description": f"Source: SEC Form D | Filed: {lead.get('filing_date','')} | Round: {lead.get('round_name','')}",
            "hs_deal_stage_probability": _stage_probability(lead.get("outreach_status","new")),
        }
    }
    deal_resp = requests.post(f"{HS_BASE}/crm/v3/objects/deals", json=deal_payload, headers=headers)
    deal_resp.raise_for_status()
    deal_id = deal_resp.json()["id"]

    # Associate deal with company
    requests.put(
        f"{HS_BASE}/crm/v3/objects/deals/{deal_id}/associations/companies/{company_id}/deal_to_company",
        headers=headers,
    )

    # Create Contacts and associate
    contact_ids = []
    for c in (contacts or []):
        if not c.get("name"):
            continue
        parts = c["name"].rsplit(" ", 1)
        contact_payload = {
            "properties": {
                "firstname": parts[0] if len(parts) > 1 else "",
                "lastname": parts[-1],
                "jobtitle": c.get("title", ""),
                "email": c.get("email", ""),
                "hs_linkedin_url": c.get("linkedin_url", ""),
            }
        }
        c_resp = requests.post(f"{HS_BASE}/crm/v3/objects/contacts", json=contact_payload, headers=headers)
        if c_resp.ok:
            cid = c_resp.json()["id"]
            contact_ids.append(cid)
            requests.put(
                f"{HS_BASE}/crm/v3/objects/deals/{deal_id}/associations/contacts/{cid}/deal_to_contact",
                headers=headers,
            )

    log.info(f"HubSpot: pushed {lead['company_name']} — company={company_id} deal={deal_id}")
    return {
        "success": True,
        "platform": "hubspot",
        "company_id": company_id,
        "deal_id": deal_id,
        "contact_ids": contact_ids,
        "url": f"https://app.hubspot.com/contacts/deals/{deal_id}",
    }


def _map_status_to_hs_stage(status: str) -> str:
    return {
        "new": "appointmentscheduled",
        "reviewing": "appointmentscheduled",
        "contacted": "qualifiedtobuy",
        "responded": "presentationscheduled",
        "interviewing": "decisionmakerboughtin",
        "offer": "contractsent",
        "closed_won": "closedwon",
        "not_interested": "closedlost",
    }.get(status, "appointmentscheduled")


def _stage_probability(status: str) -> str:
    return {
        "new": "0.1", "reviewing": "0.2", "contacted": "0.3",
        "responded": "0.5", "interviewing": "0.7", "offer": "0.9",
        "closed_won": "1.0", "not_interested": "0.0",
    }.get(status, "0.1")
