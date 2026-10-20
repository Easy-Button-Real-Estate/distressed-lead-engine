"""Skip tracing behind one interface. Set SKIPTRACE_PROVIDER=dealmachine|batchdata and that provider's key.

DealMachine: POST https://api.v2.dealmachine.com/v1/enrichment/address  (Bearer DEALMACHINE_API_KEY,
  up to 250 addresses per call, contact_audience=owners returns contacts with phones/emails + do_not_call flags).
  Docs: https://api.docs.dealmachine.com
BatchData:  POST https://api.batchdata.com/api/v3/property/skip-trace  (Bearer BATCHDATA_API_KEY).
  Docs: https://developer.batchdata.com  - response parsing is defensive; confirm on your first test call.
Anything else: rows without phones are exported to output/skiptrace_upload.csv for manual upload.
"""
import os, requests


def _dealmachine(rows, state):
    key = os.environ["DEALMACHINE_API_KEY"]
    for i in range(0, len(rows), 250):
        chunk = rows[i:i + 250]
        body = {"data": [{"street": r["property_address"], "city": r["city"], "state": state, "zip": r["zip"]} for r in chunk],
                "contact_audience": "owners", "fields": ["full_name", "phones", "emails"]}
        res = requests.post("https://api.v2.dealmachine.com/v1/enrichment/address", json=body, timeout=120,
                            headers={"Authorization": f"Bearer {key}"})
        res.raise_for_status()
        for r, item in zip(chunk, res.json().get("data", [])):
            if not item.get("matched"):
                continue
            cs = item.get("contacts") or []
            r["phones"] = "; ".join(f"{p['number']}{' (DNC)' if p.get('do_not_call') else ''}"
                                    for c in cs for p in c.get("phones") or [])[:300]
            r["emails"] = "; ".join(e["address"] for c in cs for e in c.get("emails") or [])[:300]
            if not r["owner_name"]:
                owners = [c["full_name"] for c in cs if c.get("is_likely_owner")]
                r["owner_name"] = " & ".join(owners[:2])


def _batchdata(rows, state):
    key = os.environ["BATCHDATA_API_KEY"]
    for i in range(0, len(rows), 100):
        chunk = rows[i:i + 100]
        body = [{"address": r["property_address"], "city": r["city"], "state": state, "zip_code": r["zip"]} for r in chunk]
        res = requests.post("https://api.batchdata.com/api/v3/property/skip-trace", json=body, timeout=120,
                            headers={"Authorization": f"Bearer {key}"})
        res.raise_for_status()
        data = res.json()
        persons = (data.get("results") or {}).get("persons") or data.get("results") or data.get("data") or []
        for r, p in zip(chunk, persons if isinstance(persons, list) else []):
            ph = p.get("phoneNumbers") or p.get("phones") or []
            em = p.get("emails") or []
            r["phones"] = "; ".join(str(x.get("number", x)) if isinstance(x, dict) else str(x) for x in ph)[:300]
            r["emails"] = "; ".join(str(x.get("email", x)) if isinstance(x, dict) else str(x) for x in em)[:300]


PROVIDERS = {"dealmachine": _dealmachine, "batchdata": _batchdata}


def skiptrace(rows, state, min_score=0, max_records=100):
    prov = os.getenv("SKIPTRACE_PROVIDER", "").lower()
    keyname = {"dealmachine": "DEALMACHINE_API_KEY", "batchdata": "BATCHDATA_API_KEY"}.get(prov)
    if not prov or not keyname or not os.getenv(keyname):
        return rows, "skipped (no provider key)"
    todo = sorted([r for r in rows if r["score"] >= min_score and r["property_address"] and not r["phones"]],
                  key=lambda r: -r["score"])[:max_records]
    try:
        PROVIDERS[prov](todo, state)
    except requests.RequestException as e:
        return rows, f"{prov} error: {e}"[:200]
    return rows, f"{prov}: traced {len(todo)} (cap {max_records})"
