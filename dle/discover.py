"""Find candidate open-data sources for ANY US county (free, plain fetch, no keys).

  python -m dle.discover --county Maricopa --state AZ [--city Phoenix --city Mesa] [--json out.json]

Searches the Socrata open-data catalog and ArcGIS Hub for each list type and prints datasets whose
name/owner mentions the county, state or cities. These are CANDIDATES: open each one, check it has
addresses or parcels and recent dates, then add it to counties/<st>_<county>.yaml and run --check.
Court/recorder lists (probate, eviction, lien, pre-foreclosure) are rarely open data; this tool also
prints the search phrases to find that county's court and recorder portals (search_page or manual_csv).
"""
import argparse, json, requests

LISTS = {
    "code_violation": ["code violation", "code enforcement", "property maintenance", "blight"],
    "vacant_building": ["vacant building", "vacant property"],
    "tax_delinquent": ["delinquent tax", "tax delinquent", "tax lien", "tax sale"],
    "tax_foreclosure": ["tax foreclosure", "treasurer deed"],
    "pre_foreclosure": ["foreclosure", "notice of default", "lis pendens", "trustee sale"],
    "probate": ["probate"],
    "eviction": ["eviction", "unlawful detainer", "forcible detainer"],
    "lien": ["lien"],
    "fire": ["fire incidents", "fire calls"],
}
UA = {"User-Agent": "distressed-lead-engine/0.3 (public records research)"}


def _hits_ok(text, terms):
    t = text.lower()
    return any(x.lower() in t for x in terms if x)


def socrata(q, terms):
    r = requests.get("https://api.us.socrata.com/api/catalog/v1", headers=UA, timeout=30,
                     params={"q": q, "only": "dataset", "limit": 20})
    r.raise_for_status()
    out = []
    for x in r.json().get("results", []):
        res, md = x["resource"], x.get("metadata", {})
        blob = " ".join([res.get("name", ""), res.get("description", "")[:300], md.get("domain", ""),
                         res.get("attribution") or ""])
        if _hits_ok(blob, terms):
            out.append({"platform": "socrata", "name": res["name"], "domain": md.get("domain"),
                        "updated": res.get("data_updated_at", "")[:10],
                        "api": f"https://{md.get('domain')}/resource/{res['id']}.json",
                        "page": x.get("permalink")})
    return out


def arcgis_hub(q, terms):
    r = requests.get("https://hub.arcgis.com/api/v3/search", headers=UA, timeout=30,
                     params={"q": q, "filter[type]": "Feature Service,Feature Layer,Table", "page[size]": 20})
    if r.status_code != 200:
        r = requests.get("https://www.arcgis.com/sharing/rest/search", headers=UA, timeout=30,
                         params={"q": f'{q} type:"Feature Service"', "num": 20, "f": "json"})
        r.raise_for_status()
        items = [{"name": i.get("title"), "owner": i.get("owner"), "url": i.get("url"),
                  "desc": (i.get("snippet") or "")} for i in r.json().get("results", [])]
    else:
        items = [{"name": d["attributes"].get("name"), "owner": d["attributes"].get("source") or d["attributes"].get("owner"),
                  "url": d["attributes"].get("url"), "desc": (d["attributes"].get("searchDescription") or "")[:300]}
                 for d in r.json().get("data", [])]
    return [{"platform": "arcgis", "name": i["name"], "owner": i["owner"], "api": i["url"]}
            for i in items if i.get("url") and _hits_ok(f"{i['name']} {i['owner']} {i['desc']}", terms)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--city", action="append", default=[])
    ap.add_argument("--json")
    a = ap.parse_args()
    terms = [a.county, f"{a.county} County"] + a.city
    report = {}
    for lt, phrases in LISTS.items():
        found, seen = [], set()
        for ph in phrases:
            for place in [a.county] + a.city:
                for fn in (socrata, arcgis_hub):
                    try:
                        for h in fn(f"{place} {ph}", terms):
                            if h["api"] not in seen:
                                seen.add(h["api"]); found.append(h)
                    except Exception as e:  # noqa: BLE001
                        found.append({"platform": fn.__name__, "error": str(e)[:120]})
        kws = [w for ph in phrases for w in ph.split() if len(w) > 3]
        found = [h for h in found if "error" in h or any(k.lower()[:6] in (h.get("name") or "").lower() for k in kws)]
        report[lt] = found
    print(f"\n=== Open-data candidates for {a.county} County, {a.state} ===")
    for lt, hits in report.items():
        good = [h for h in hits if "error" not in h]
        print(f"\n{lt}: {len(good)} candidate(s)")
        for h in good[:8]:
            print(f"  [{h['platform']}] {h['name']}  ->  {h['api']}")
    print("\nCourt / recorder portals to look up (usually search_page or manual_csv):")
    for q in [f"{a.county} County {a.state} probate case search", f"{a.county} County {a.state} eviction case search justice court",
              f"{a.county} County {a.state} recorder document search notice of trustee sale",
              f"{a.county} County {a.state} treasurer delinquent tax list", f"{a.state} secretary of state business search"]:
        print("  search:", q)
    if a.json:
        json.dump(report, open(a.json, "w"), indent=2)


if __name__ == "__main__":
    main()
