"""LLC piercing: find the people behind an entity owner.

GovFiles (https://docs.govfiles.dev) - POST https://api.govfiles.dev/v2/companies/search,
header X-API-Key, $0.01 per returned result. Each company has `parties` with
roles (owner, manager, member, officer, registered_agent ...).
No key? We add a free state Secretary of State search link to the row so you can look it up by hand.
"""
import os, requests

GOVFILES = "https://api.govfiles.dev/v2/companies/search"
PEOPLE_ROLES = {"owner", "manager", "member", "governor", "officer"}

# Free fallback: official state business-search pages (verify yours; add more in your county YAML via sos_search_url).
SOS_SEARCH = {
    "WA": "https://ccfs.sos.wa.gov/#/BusinessSearch",
    "CA": "https://bizfileonline.sos.ca.gov/search/business",
    "TX": "https://comptroller.texas.gov/taxes/franchise/account-status/search",
    "FL": "https://search.sunbiz.org/Inquiry/CorporationSearch/ByName",
    "NY": "https://apps.dos.ny.gov/publicInquiry/",
}


def govfiles_lookup(name, state):
    body = {"q": f'"{name}"', "jurisdictions": f"us_{state.lower()}" if state else "all",
            "status": "any", "limit": 3, "page": 1}
    r = requests.post(GOVFILES, json=body, timeout=60,
                      headers={"X-API-Key": os.environ["GOVFILES_API_KEY"], "Content-Type": "application/json"})
    r.raise_for_status()
    people = []
    for hit in r.json().get("results", []):
        for p in (hit.get("company") or {}).get("parties") or []:
            kinds = {ro.get("kind") for ro in p.get("roles") or []}
            if p.get("type") == "person" and kinds & PEOPLE_ROLES:
                people.append(f"{p['name']} ({'/'.join(sorted(kinds & PEOPLE_ROLES))})")
            elif "registered_agent" in kinds and len(people) < 6:
                people.append(f"{p['name']} (registered agent)")
    return "; ".join(dict.fromkeys(people))


def pierce(rows, state, sos_url=None, max_lookups=200):
    use_api = bool(os.getenv("GOVFILES_API_KEY"))
    n = 0
    for r in rows:
        if r.get("owner_type") != "entity":
            continue
        if use_api and n < max_lookups:
            n += 1
            try:
                r["llc_principals"] = govfiles_lookup(r["owner_name"], state) or "no principals published"
            except requests.RequestException as e:
                r["llc_principals"] = f"GovFiles error: {e}"[:120]
        else:
            r["llc_principals"] = f"look up free: {sos_url or SOS_SEARCH.get(state, 'your state SOS business search')}"
    return rows
