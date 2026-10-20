"""Shared lead schema, normalization, dedupe, scoring and storage."""
import csv, hashlib, json, os, re, sqlite3
from datetime import date, datetime

FIELDS = ["lead_id", "county", "state", "list_types", "list_count", "score",
          "property_address", "city", "zip", "parcel_id", "owner_name", "owner_type",
          "event_date", "amount", "details", "source_urls", "first_seen", "is_new",
          "llc_principals", "phones", "emails", "mailing_address",
          "marketing_sms", "marketing_email_subject", "marketing_email_body", "marketing_letter"]

# Base weight per list type. Stacked lists add up (see score()).
WEIGHTS = {"probate": 30, "pre_probate": 25, "pre_foreclosure": 30, "tax_foreclosure": 30,
           "tax_delinquent": 25, "code_violation": 15, "vacant_building": 20, "eviction": 15,
           "water_shutoff": 15, "lien": 15, "fire": 20}

SUFFIX = {"street": "st", "avenue": "ave", "av": "ave", "road": "rd", "drive": "dr", "place": "pl",
          "court": "ct", "lane": "ln", "boulevard": "blvd", "terrace": "ter", "north": "n",
          "south": "s", "east": "e", "west": "w", "northeast": "ne", "northwest": "nw",
          "southeast": "se", "southwest": "sw", "way": "way", "highway": "hwy", "parkway": "pkwy"}


def norm_address(a):
    a = re.sub(r"[^a-z0-9 ]", " ", (a or "").lower())
    a = re.sub(r"\b(apt|unit|ste|suite)\b.*$", "", a)
    return " ".join(SUFFIX.get(w, w) for w in a.split())


def lead(county, state, list_type, address, city="", zip_="", parcel_id="", owner_name="",
         event_date="", amount="", details="", source_url=""):
    return {"county": county, "state": state, "list_type": list_type,
            "property_address": (address or "").strip().upper(), "city": (city or "").upper(),
            "zip": (zip_ or "")[:5], "parcel_id": parcel_id or "", "owner_name": owner_name or "",
            "event_date": (event_date or "")[:10], "amount": amount or "", "details": details or "",
            "source_url": source_url or ""}


def key(l):
    # Address first (so a parcel on the tax list stacks with a code case at the same address),
    # parcel number when there is no street address (vacant land).
    if norm_address(l["property_address"]):
        return "addr:" + l["county"].lower() + "|" + norm_address(l["property_address"])
    return "pin:" + re.sub(r"\D", "", l["parcel_id"])


def owner_type(name):
    n = (name or "").upper()
    if re.search(r"\b(LLC|L L C|INC|CORP|CORPORATION|LP|LLP|LTD|COMPANY|CO|HOLDINGS|PROPERTIES|INVESTMENTS)\b", n):
        return "entity"
    if re.search(r"\b(TRUST|TRUSTEE|TR|TTEE)\b", n):
        return "trust"
    if re.search(r"\b(ESTATE|EST OF|HEIRS|DECEASED)\b", n):
        return "estate"
    return "individual" if n else ""


def merge(raw_leads):
    """Merge raw single-list rows into one row per property (stacked lists)."""
    out = {}
    for l in raw_leads:
        if not l["property_address"] and not l["parcel_id"]:
            continue
        k = key(l)
        m = out.setdefault(k, {"lead_id": hashlib.sha1(k.encode()).hexdigest()[:12], "county": l["county"],
                               "state": l["state"], "types": set(), "urls": set(), "details": [],
                               **{f: "" for f in ["property_address", "city", "zip", "parcel_id",
                                                  "owner_name", "event_date", "amount"]}})
        m["types"].add(l["list_type"])
        if l["source_url"]:
            m["urls"].add(l["source_url"])
        if l["details"] and len(m["details"]) < 4:
            m["details"].append(f"[{l['list_type']}] {l['details'][:160]}")
        for f in ["property_address", "city", "zip", "parcel_id", "owner_name", "amount"]:
            m[f] = m[f] or l.get(f, "")
        if l["event_date"] > m["event_date"]:
            m["event_date"] = l["event_date"]
    rows = []
    for m in out.values():
        r = {f: "" for f in FIELDS}
        r.update({k: v for k, v in m.items() if k in FIELDS})
        r["list_types"] = ";".join(sorted(m["types"]))
        r["list_count"] = len(m["types"])
        r["source_urls"] = " ".join(sorted(m["urls"]))
        r["details"] = " | ".join(m["details"])
        r["owner_type"] = owner_type(r["owner_name"])
        r["score"] = score(r)
        rows.append(r)
    return rows


def score(r):
    types = r["list_types"].split(";") if r["list_types"] else []
    s = sum(WEIGHTS.get(t, 10) for t in types)
    if len(types) > 1:
        s += 15 * (len(types) - 1)          # stacked-list bonus
    if r.get("event_date"):
        try:
            age = (date.today() - date.fromisoformat(r["event_date"])).days
            s += 15 if age <= 7 else 8 if age <= 30 else 0   # freshness
        except ValueError:
            pass
    if r.get("owner_type") in ("estate", "trust"):
        s += 10
    return min(s, 100)


class Store:
    """SQLite history so a property is only flagged NEW the first time it shows up."""
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("create table if not exists seen (lead_id text primary key, first_seen text, list_types text)")

    def mark(self, rows, dry_run=False):
        today = date.today().isoformat()
        for r in rows:
            cur = self.db.execute("select first_seen, list_types from seen where lead_id=?", (r["lead_id"],)).fetchone()
            if cur is None:
                r["first_seen"], r["is_new"] = today, "NEW"
                if not dry_run:
                    self.db.execute("insert into seen values (?,?,?)", (r["lead_id"], today, r["list_types"]))
            else:
                r["first_seen"] = cur[0]
                r["is_new"] = "NEW LIST" if r["list_types"] != cur[1] else ""
                if r["is_new"] and not dry_run:
                    self.db.execute("update seen set list_types=? where lead_id=?", (r["list_types"], r["lead_id"]))
        if not dry_run:
            self.db.commit()
        return rows


def write_csv(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path
