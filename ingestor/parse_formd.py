"""
Updated Form D XML parser — pulls all available fields from the spec.
Drop-in replacement for parse_xml in ingest.py.
"""

from typing import Optional
import xml.etree.ElementTree as ET


def _t(root: ET.Element, path: str, ns: str = "") -> str:
    tag = f"{{{ns}}}{path}" if ns else path
    node = root.find(f".//{tag}")
    return (node.text or "").strip() if node is not None else ""


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "").replace("$", "")) if s else None
    except ValueError:
        return None


def _to_bool(s: str) -> bool:
    return s.strip().lower() in ("true", "1", "yes")


def parse_xml_full(root: ET.Element, cik: str, accession_no: str, filing_date: str) -> Optional[dict]:
    ns = "http://www.sec.gov/edgar/document/formd"

    def t(path):
        return _t(root, path, ns) or _t(root, path)

    company_name = t("entityName") or t("issuerName")
    if not company_name:
        return None

    amount_raised  = _to_float(t("totalAmountSold"))
    amount_offered = _to_float(t("totalOfferingAmount"))

    # Federal exemptions
    exemptions = []
    for node in root.iter():
        tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag
        if "exemption" in tag.lower() or "rule506" in tag.lower() or "rule504" in tag.lower():
            val = (node.text or "").strip()
            if val and val not in exemptions:
                exemptions.append(val)

    # Related persons
    persons = []
    for node in root.iter():
        if "relatedPersonInfo" not in node.tag:
            continue
        fn = node.find(f".//{{{ns}}}firstName") or node.find(".//firstName")
        ln = node.find(f".//{{{ns}}}lastName") or node.find(".//lastName")
        mn = node.find(f".//{{{ns}}}middleName") or node.find(".//middleName")
        rel = node.find(f".//{{{ns}}}relationships") or node.find(".//relationships")

        first  = (fn.text or "").strip() if fn is not None else ""
        middle = (mn.text or "").strip() if mn is not None else ""
        last   = (ln.text or "").strip() if ln is not None else ""
        name   = " ".join(filter(None, [first, middle, last]))

        p_state = _t(node, "stateOrCountry", ns) or _t(node, "stateOrCountry")
        clarification = _t(node, "relationshipClarification", ns) or _t(node, "relationshipClarification")

        roles = []
        if rel is not None:
            for r in rel:
                tag = r.tag.split("}")[-1] if "}" in r.tag else r.tag
                if (r.text or "").strip().lower() in ("true", "1"):
                    roles.append(tag)

        is_exec = any(r in ("executiveOfficer", "officer", "director") for r in roles)

        if name:
            persons.append({
                "name": name,
                "roles": roles,
                "is_executive": is_exec,
                "state": p_state,
                "clarification": clarification,
            })

    edgar_url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={cik}&type=D&dateb=&owner=include&count=10"
    )

    return {
        "cik":               cik,
        "accession_no":      accession_no,
        "company_name":      company_name,
        "filing_date":       filing_date or None,
        "street1":           t("street1") or None,
        "street2":           t("street2") or None,
        "city":              t("issuerAddress/city") or t("city") or None,
        "state":             t("issuerAddress/stateOrCountry") or t("stateOrCountry") or None,
        "zip_code":          t("issuerAddress/zipCode") or t("zipCode") or None,
        "phone":             t("issuerPhoneNumber") or t("phoneNumber") or None,
        "entity_type":       t("entityType") or None,
        "jurisdiction_inc":  t("jurisdictionOfInc") or None,
        "year_inc":          t("yearOfIncorporation") or t("yearOfInc") or None,
        "amount_raised":     amount_raised,
        "amount_offered":    amount_offered,
        "industry":          t("industryGroupType") or t("industryGroup") or None,
        "sic_code":          t("sicCode") or None,
        "security_type":     t("typesOfSecuritiesOffered") or t("typeOfSecurities") or None,
        "date_first_sale":   t("dateOfFirstSale") or None,
        "revenue_range":     t("revenueRange") or None,
        "federal_exemptions": ", ".join(exemptions) if exemptions else None,
        "is_amendment":      _to_bool(t("isAmendment")) if t("isAmendment") else False,
        "min_investment":    _to_float(t("minimumInvestmentAccepted")),
        "has_non_accredited": _to_bool(t("hasNonAccreditedInvestors")),
        "num_non_accredited": int(n) if (n := t("numberOfNonAccreditedInvestors")).isdigit() else None,
        "num_investors":     int(n) if (n := t("totalNumberAlreadyInvested")).isdigit() else None,
        "sales_commissions": _to_float(t("salesCommissionsDollarAmount")),
        "finders_fee":       _to_float(t("findersFeesDollarAmount")),
        "edgar_url":         edgar_url,
        "_persons":          persons,
    }
