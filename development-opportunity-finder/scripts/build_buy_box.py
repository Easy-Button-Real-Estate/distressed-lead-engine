#!/usr/bin/env python3
"""Step 1: build a buy box from what developers and builders actually paid.

Input is a list of recent land / lot sales in your county. Any of these work:
  * a recorder / assessor SALES file with the recorded grantee (buyer). Best.
  * a county parcel layer or PropStream export with "last sale" columns. Here the
    buyer is the assessor's CURRENT owner, which is only the buyer if the parcel has
    not been resold since (see "survivorship gap" below).
  * NON-DISCLOSURE STATES (TX, NM, UT, ID, WY, MT, ND, KS, MS, LA, AK and others):
    sale prices are not public. Use --price-only with sold-land comps (MLS through
    an agent, Land Portal, Zillow / Redfin sold land) or your PropStream export.
    The buy box is then built from LAND PRICES IN GENERAL, not from developer buys,
    and every output says so.

What it does
  * keeps buyers that look like builders / developers (name patterns, your
    --known-developers list, or your Y/N choices in buyers_review.csv)
  * groups multi-parcel deeds, so one price is counted once (by deed / instrument
    number, or same buyer + date + price)
  * works out size band, $/acre, $/lot, zoning and location
  * flags deeds that "paid a premium (25%+ over the size-band median)"
  * says how much to trust it (confidence line)

Outputs (in --output-dir):
  buy_box.json          feeds score_parcels.py --buy-box
  buy_box_summary.md    plain-English read, with the confidence line
  developer_sales.csv   the deeds used, one row per deed
  buyers_review.csv     every buyer and the automatic call; put Y or N in "approve"
                        and re-run with --approved-buyers buyers_review.csv

Usage:
  python scripts/build_buy_box.py --sales sales.csv --market "Wake County, NC"
  python scripts/build_buy_box.py --sales tx_sold_land.csv --state TX --price-only

Survivorship gap: with current-owner data, a builder that bought 40 acres, platted
it and sold the homes no longer shows as the owner, so those buys disappear and
the sample leans toward land builders still hold. Recorder sales files do not have
this problem. The summary says which kind of data you used.
"""
import argparse, datetime as dt, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import norm, num, parse_date, pick, quantile, read_rows, write_rows  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS = os.path.join(HERE, "..", "references", "use-cases.json")
NON_DISCLOSURE = {"TX", "NM", "UT", "ID", "WY", "MT", "ND", "KS", "MS", "LA", "AK", "MO"}
PREMIUM_LABEL = "paid a premium (25%+ over the size-band median)"

COLS = {
    "grantee": ["grantee", "grantee_name", "grantee1", "buyer", "buyer_name", "buyer1", "purchaser"],
    "owner": ["owner1fullname", "ownerfullname", "owner1name", "owner", "ownername", "owner_name", "owner 1 full name", "deedholder"],
    "buyer_type": ["buyer_type", "buyertype", "ownertype", "owner_type"],
    "deed_id": ["instrument", "instrument_number", "instrumentno", "doc_number", "document_number", "docnum", "deed_id",
                "book_page", "bookpage", "deed_book_page", "recording_number", "reception_number"],
    "deed_book": ["deed_book", "deedbook", "book"],
    "owner_deed_date": ["deed_date", "deeddate", "owner_deed_date", "current_owner_deed_date", "date_acquired", "acquired_date"],
    "deed_page": ["deed_page", "deedpage", "page"],
    "sale_date": ["sale_date", "saledate", "recording_date", "recordingdate", "deed_date", "deeddate", "lastsalerecordingdate",
                  "last sale recording date", "lastsaledate", "last sale date", "transfer_date", "transferdate", "sold_date", "close_date",
                  "closedate", "list_date"],
    "sale_price": ["sale_price", "saleprice", "sale_amount", "saleamount", "consideration", "price", "lastsaleamount",
                   "last sale amount", "lastsaleprice", "last sale price", "sold_price", "soldprice", "totsalprice", "totalsaleprice",
                   "saleamt", "sale_amt", "close_price", "closeprice"],
    "list_price": ["list_price", "listprice", "asking_price", "askingprice"],
    "year_built": ["year_built", "yearbuilt", "yr_built", "yrbuilt", "effective_year_built"],
    "acres": ["acres", "acreage", "lot_acres", "lotacres", "lot size acres", "lotsizeacres", "lotacreage", "gis_acres", "gisacres",
              "calcacres", "deededacres", "deed_acres", "totalacres"],
    "lot_sqft": ["lot_sqft", "lot size sqft", "lotsizesqft", "lotsqft", "land_sqft", "landsqft"],
    "lots": ["lots", "lot_count", "num_lots", "number_of_lots", "units", "parcels_in_sale", "parcel_count"],
    "zoning": ["zoning", "zone", "zoning_code", "zoningcode", "zoning description"],
    "land_use": ["land_use", "landuse", "property type", "propertytype", "use_code", "usecode"],
    "city": ["city", "situs_city", "site city", "property city"],
    "zip": ["zip", "zipcode", "zip code", "situs_zip", "site zip", "property zip", "zipnum", "zip5"],
    "address": ["address", "situs_address", "site address", "property address", "site_address"],
    "apn": ["apn", "parcel_id", "parcelid", "pin", "pin_num", "parcel number"],
    "lat": ["lat", "latitude", "y"],
    "lon": ["lon", "lng", "long", "longitude", "x"],
}

# Builder / developer name patterns. Generic words first, then national and large regional builders.
BUILDER_WORDS = (r"homes?\b", r"home ?builders?", r"builders?\b", r"building\b", r"construction", r"constructors",
                 r"develop(ment|ments|ers?)\b", r"communities", r"community\b", r"residential\b", r"land (co|company|holdings|partners|ventures)",
                 r"subdivision", r"estates (llc|inc)", r"custom homes", r"housing\b")
BUILDER_NAMES = ("lennar", r"d\.? ?r\.? horton", "pulte", "centex", "del webb", r"\bnvr\b", "ryan homes", "toll brothers", r"kb home",
                 "meritage", "taylor morrison", "century communities", r"m/?i homes", "tri pointe", "ashton woods", "david weekley",
                 "beazer", "dream finders", "lgi homes", "smith douglas", "stanley martin", "shea homes", "richmond american",
                 "perry homes", "highland homes", "drees", "fischer homes", "forestar", "starlight homes", "brookfield residential",
                 "mungo", "great southern homes", "clayton properties", "eastwood homes", "true homes", "mattamy", "hovnanian",
                 "woodside homes", "landsea", "trumark", "william lyon", "holiday builders", "adams homes", "maronda", "lombardo")
NOT_DEVELOPER = re.compile(r"\b(bank|mortgage|credit union|church|school|county|city of|state of|united states|federal|"
                           r"hud|secretary of|fannie|freddie|habitat for humanity)\b", re.I)


def builder_regex(extra):
    pats = list(BUILDER_WORDS) + list(BUILDER_NAMES) + [re.escape(x.strip()) for x in (extra or []) if x.strip()]
    return re.compile(r"(" + "|".join(pats) + r")", re.I)


def load_names(path):
    """Known developers: a .txt (one name per line) or a CSV with a name / buyer / developer column."""
    if not path:
        return []
    if path.lower().endswith(".csv"):
        rows = read_rows(path)
        if not rows:
            return []
        c = pick(list(rows[0].keys()), ["name", "developer", "buyer", "company", "llc"]) or list(rows[0].keys())[0]
        return [r[c].strip() for r in rows if (r.get(c) or "").strip()]
    return [l.strip() for l in open(path) if l.strip() and not l.startswith("#")]


def size_band(acres):
    for lim, label in ((1, "under 1 ac"), (5, "1-5 ac"), (20, "5-20 ac"), (100, "20-100 ac")):
        if acres < lim:
            return label
    return "100+ ac"


def r2(v, nd=2):
    return None if v is None else round(v, nd)


def nice(v):
    if v is None:
        return None
    if v < 1:
        return round(v, 2)
    if v < 10:
        return round(v, 1)
    return float(round(v))


BEST_SOURCE = ("Best source: the county recorder's grantor-grantee index (deeds with the recorded buyer and price), "
               "or a sales report from a title company rep. Assessor 'current owner' data and name keywords are weaker.")
EVIDENCE = ("verified grantee purchase", "keyword-inferred buyer", "current-owner proxy", "price-only (no buyer)",
            "probable grantee (current owner; deed date = sale date)")
PREMIUM_MIN_DEEDS = 10  # below this, no "paid a premium" claims at all


def confidence(n, price_only, buyer_source, verified=0):
    if price_only:
        if n >= 25:
            return "medium", f"{n} sales, but prices are general land comps, not developer buys"
        return "low", f"only {n} sales, and they are general land comps, not developer buys"
    if buyer_source != "recorded grantee":
        if n >= 25:
            return "medium", f"{n} deeds, but buyers come from current-owner data (survivorship gap)"
        return "low", f"only {n} deeds, and buyers come from current-owner data (survivorship gap)"
    if n >= 25 and verified >= 10:
        return "high", f"{n} developer deeds from recorded sales, {verified} verified by you or your known-developers list"
    if n >= 10:
        return "medium", f"{n} deeds from recorded sales, but only {verified} verified; the rest are inferred from name keywords"
    return "low", f"only {n} deeds; the preset size and zoning were kept"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sales", required=True, help="recent land/lot sales, a parcel export with last-sale columns, or sold-land comps")
    ap.add_argument("--market", default="", help='e.g. "Wake County, NC"')
    ap.add_argument("--state", default="", help="two-letter state; warns and explains the fallback in non-disclosure states")
    ap.add_argument("--use-case", default="single_family", help="preset to start from (see references/use-cases.json)")
    ap.add_argument("--months", type=int, default=36, help="only sales in the last N months (default 36; 24-36 recommended)")
    ap.add_argument("--as-of", help="YYYY-MM-DD to measure --months from (default today)")
    ap.add_argument("--min-price", type=float, default=5000, help="ignore sales under this (gifts, quitclaims, $10 deeds)")
    ap.add_argument("--premium-pct", type=float, default=25, help="a deed 'paid a premium' when $/acre is this %% over its size-band median")
    ap.add_argument("--all-buyers", action="store_true", help="treat every buyer as a developer (your file is already filtered)")
    ap.add_argument("--price-only", action="store_true",
                    help="no buyer names (non-disclosure states, MLS / Land Portal / PropStream sold comps): build from land prices in general")
    ap.add_argument("--known-developers", help="txt or CSV of builder / developer names and their LLCs to always count")
    ap.add_argument("--approved-buyers", help="buyers_review.csv with Y / N in the approve column (your manual choices win)")
    ap.add_argument("--buyer-pattern", action="append", default=[], help="extra builder name to count as a developer (repeatable)")
    ap.add_argument("--min-sales", type=int, default=10, help="fewest deeds needed to set the buy box from data (default 10)")
    ap.add_argument("--band-min", type=int, default=5, help="fewest deeds in a size band before premiums are flagged (default 5)")
    ap.add_argument("--parcels", help="your parcel file: parcels owned by builders now are shown as extra evidence (current holdings)")
    ap.add_argument("--output-dir", default="out")
    a = ap.parse_args(argv)

    rows = read_rows(a.sales)
    if not rows:
        raise SystemExit("The sales file is empty.")
    H = list(rows[0].keys())
    C = {k: pick(H, v) for k, v in COLS.items()}
    if C["owner_deed_date"] == C["sale_date"]:
        C["owner_deed_date"] = None
    st = a.state.strip().upper()
    nd_state = st in NON_DISCLOSURE
    price_only = a.price_only
    if C["grantee"]:
        buyer_col, buyer_source = C["grantee"], "recorded grantee"
    elif C["owner"]:
        buyer_col, buyer_source = C["owner"], "assessor current owner (assumed to be the buyer)"
    else:
        buyer_col, buyer_source = None, "none"
    if not buyer_col and not price_only:
        raise SystemExit("No buyer / grantee / owner column." + (f" {st} is a non-disclosure state:" if nd_state else "") +
                         " If this is a sold-comps or listings file (MLS, Land Portal, PropStream), add --price-only. "
                         "The buy box will then come from land prices in general, not from developer buys.")
    price_col = C["sale_price"] or (C["list_price"] if price_only else None)
    price_kind = "sold price" if C["sale_price"] else "LIST price (asking, not sold)"
    if not price_col:
        msg = "No sale price column."
        if nd_state:
            msg += (f" {st} is a non-disclosure state, so recorded prices are not public. Use sold-land comps (MLS via an agent, "
                    "Land Portal, Zillow / Redfin sold land) or your PropStream export, and add --price-only.")
        raise SystemExit(msg)
    if not (C["acres"] or C["lot_sqft"]) or not C["sale_date"]:
        raise SystemExit("The sales file needs a sale date and acres (or lot sqft).")
    priced = sum(1 for r in rows if num(r.get(price_col)))
    if nd_state and not price_only and priced < 0.5 * len(rows):
        raise SystemExit(f"{st} is a non-disclosure state and most rows have no price. Re-run with sold-land comps and --price-only.")

    as_of = parse_date(a.as_of) if a.as_of else dt.date.today()
    cutoff = as_of - dt.timedelta(days=int(a.months * 30.44))
    known = load_names(a.known_developers)
    known_n = [norm(k) for k in known if norm(k)]
    rx = builder_regex(a.buyer_pattern)
    approved = {}
    if a.approved_buyers and os.path.exists(a.approved_buyers):
        for r in read_rows(a.approved_buyers):
            v = str(r.get("approve") or "").strip().upper()[:1]
            if v in ("Y", "N"):
                approved[norm(r.get("buyer"))] = v == "Y"

    g = lambda r, k: (r.get(C[k]) if C[k] else None)
    skipped = {"older than window": 0, "price missing or under min": 0, "no acreage": 0, "buyer not a builder/developer": 0, "no sale date": 0, "price included an existing building": 0}
    review, deeds = {}, {}
    for r in rows:
        buyer = str(r.get(buyer_col) or "").strip() if buyer_col else ""
        d = parse_date(g(r, "sale_date"))
        price = num(r.get(price_col))
        acres = num(g(r, "acres"))
        if acres is None and num(g(r, "lot_sqft")):
            acres = num(g(r, "lot_sqft")) / 43560.0
        if d is None:
            skipped["no sale date"] += 1; continue
        if d < cutoff or d > as_of:
            skipped["older than window"] += 1; continue
        if not price or price < a.min_price:
            skipped["price missing or under min"] += 1; continue
        if not acres or acres <= 0:
            skipped["no acreage"] += 1; continue
        yb = num(g(r, "year_built"))
        if yb and 1700 < yb < d.year:
            # a building already stood when it sold, so the price is not a land price
            skipped["price included an existing building"] += 1; continue
        if price_only:
            is_dev, why, evid = True, "price-only mode (not developer-specific)", EVIDENCE[3]
        else:
            bn = norm(buyer)
            btype = str(g(r, "buyer_type") or "")
            if bn in approved:
                is_dev, why = approved[bn], "your choice in buyers_review.csv"
            elif any(k and (k in bn) for k in known_n):
                is_dev, why = True, "on your known-developers list"
            elif a.all_buyers:
                is_dev, why = True, "--all-buyers"
            elif NOT_DEVELOPER.search(buyer):
                is_dev, why = False, "bank / government / institution"
            elif re.search(r"builder|developer", btype, re.I) or rx.search(buyer):
                is_dev, why = True, "name looks like a builder / developer"
            else:
                is_dev, why = False, "name does not look like a builder"
            rv = review.setdefault(bn, {"buyer": buyer, "deeds": 0, "auto_decision": "developer" if is_dev else "not developer",
                                        "reason": why, "approve": ""})
            rv["deeds"] += 1
            if buyer_source != "recorded grantee":
                odd = parse_date(g(r, "owner_deed_date")) if C["owner_deed_date"] else None
                # the current owner's deed was recorded at this sale: the owner very probably is the buyer of this sale
                evid = EVIDENCE[4] if (odd and abs((odd - d).days) <= 31) else EVIDENCE[2]
            elif why in ("your choice in buyers_review.csv", "on your known-developers list"):
                evid = EVIDENCE[0]
            else:
                evid = EVIDENCE[1]
            if not is_dev:
                skipped["buyer not a builder/developer"] += 1
                continue
        # one deed = one price: group parcels that share a deed / instrument, or buyer + date + price
        did = str(g(r, "deed_id") or "").strip()
        if not did and C["deed_book"] and C["deed_page"] and str(g(r, "deed_book") or "").strip():
            did = f"{g(r, 'deed_book')}-{g(r, 'deed_page')}"
        key = ("deed:" + did) if did else f"{norm(buyer)}|{d.isoformat()}|{round(price)}"
        dd = deeds.get(key)
        if dd is None:
            lots = num(g(r, "lots"))
            dd = deeds[key] = {"buyer": buyer or "(not recorded - price-only)", "buyer_source": buyer_source if not price_only else "none (price-only)",
                               "sale_date": d.isoformat(), "sale_price": round(price), "acres": 0.0, "parcels": 0, "lots": int(lots) if lots else 0,
                               "zoning": str(g(r, "zoning") or "").strip(), "land_use": str(g(r, "land_use") or "").strip(),
                               "city": str(g(r, "city") or "").strip(), "zip": str(g(r, "zip") or "").strip()[:5],
                               "address": str(g(r, "address") or "").strip(), "apns": [], "lat": num(g(r, "lat")), "lon": num(g(r, "lon")),
                               "deed_id": did, "price_kind": price_kind, "evidence": evid, "counted_because": why}
        else:
            lots = num(g(r, "lots"))
            if lots:
                dd["lots"] += int(lots)
        dd["acres"] += acres
        dd["parcels"] += 1
        if g(r, "apn"):
            dd["apns"].append(str(g(r, "apn")))
    used = list(deeds.values())
    funnel, left = [], len(rows)
    funnel.append((f"{left:,} sales in the file", left))
    unchanged = []
    for label, keys in (("in the date window", ("no sale date", "older than window")), ("with a usable price", ("price missing or under min",)),
                        ("with acreage", ("no acreage",)), ("land only (no existing building)", ("price included an existing building",)),
                        ("bought by a builder / developer" if not price_only else "kept (price-only: all buyers)", ("buyer not a builder/developer",))):
        cut = sum(skipped[k] for k in keys)
        left -= cut
        if not cut:
            unchanged.append(label)
        funnel.append((f"{left:,} {label}" + (" (none removed)" if not cut else ""), left))
    funnel.append((f"{len(used):,} deeds after grouping multi-parcel deeds", len(used)))
    for s in used:
        if not s["lots"] and s["acres"] < 1:
            s["lots"] = s["parcels"]
        s["acres"] = round(s["acres"], 3)
        s["price_per_acre"] = round(s["sale_price"] / s["acres"])
        s["price_per_lot"] = round(s["sale_price"] / s["lots"]) if s["lots"] else ""
        s["size_band"] = size_band(s["acres"])
        s["apns"] = "; ".join(s["apns"])
        s["lots"] = s["lots"] or ""

    bands = {}
    for s in used:
        bands.setdefault(s["size_band"], []).append(s["price_per_acre"])
    band_med = {b: quantile(v, 0.5) for b, v in bands.items()}
    for s in used:
        med = band_med[s["size_band"]]
        s["band_median_per_acre"] = round(med)
        s["vs_band_median_pct"] = round(100.0 * (s["price_per_acre"] / med - 1)) if med else ""
        # price-only files have no buyer names, so a high price says nothing about developers: never flag a premium
        s["paid_premium"] = "Y" if (not price_only and len(used) >= PREMIUM_MIN_DEEDS and len(bands[s["size_band"]]) >= a.band_min and med and
                                    s["price_per_acre"] >= med * (1 + a.premium_pct / 100.0)) else ""

    presets = json.load(open(PRESETS))
    if a.use_case not in presets:
        raise SystemExit("Unknown use case " + a.use_case)
    preset = presets[a.use_case]
    os.makedirs(a.output_dir, exist_ok=True)
    write_rows(os.path.join(a.output_dir, "developer_sales.csv"), used,
               ["sale_date", "buyer", "buyer_source", "evidence", "counted_because", "sale_price", "price_kind", "acres", "parcels", "apns", "deed_id", "lots",
                "price_per_acre", "price_per_lot", "size_band", "band_median_per_acre", "vs_band_median_pct", "paid_premium",
                "zoning", "land_use", "city", "zip", "address", "lat", "lon"])
    if review:
        write_rows(os.path.join(a.output_dir, "buyers_review.csv"),
                   sorted(review.values(), key=lambda v: (v["auto_decision"] != "developer", -v["deeds"], v["buyer"])),
                   ["buyer", "deeds", "auto_decision", "reason", "approve"])

    n = len(used)
    enough = n >= a.min_sales
    builder_owned = None
    if a.parcels and os.path.exists(a.parcels):
        prow = read_rows(a.parcels)
        if prow:
            PH = list(prow[0].keys())
            PC = {k: pick(PH, COLS[k]) for k in ("owner", "acres", "zip", "zoning", "land_use", "apn")}
            held = []
            for r in prow:
                ow = str(r.get(PC["owner"]) or "").strip() if PC["owner"] else ""
                if not ow or NOT_DEVELOPER.search(ow):
                    continue
                on = norm(ow)
                if approved.get(on) is False:
                    continue
                if approved.get(on) or any(k and k in on for k in known_n) or rx.search(ow):
                    held.append({"owner": ow, "apn": str(r.get(PC["apn"]) or "") if PC["apn"] else "",
                                 "acres": num(r.get(PC["acres"])) if PC["acres"] else None,
                                 "zip": str(r.get(PC["zip"]) or "")[:5] if PC["zip"] else "",
                                 "zoning": str(r.get(PC["zoning"]) or r.get(PC["land_use"]) or "") if (PC["zoning"] or PC["land_use"]) else ""})
            if held:
                write_rows(os.path.join(a.output_dir, "builder_owned_parcels.csv"), held, ["owner", "apn", "acres", "zip", "zoning"])
            hac = [h["acres"] for h in held if h["acres"]]
            cnt = lambda k: sorted({v: sum(1 for h in held if h[k] == v) for v in {h[k] for h in held if h[k]}}.items(), key=lambda kv: -kv[1])[:5]
            builder_owned = {"parcels": len(held), "owners": len({norm(h["owner"]) for h in held}), "acres_total": round(sum(hac), 1),
                             "acres_median": r2(quantile(hac, .5)) if hac else None, "top_zips": cnt("zip"), "top_zoning": cnt("zoning")}
    ev_counts = {e: sum(1 for s_ in used if s_["evidence"] == e) for e in EVIDENCE}
    conf, conf_why = confidence(n, price_only, buyer_source, ev_counts[EVIDENCE[0]])
    ac = [s["acres"] for s in used]
    ppa = [s["price_per_acre"] for s in used]
    ppl = [s["price_per_lot"] for s in used if s["price_per_lot"] != ""]

    def counts(key, only_premium=False):
        c = {}
        for s in used:
            if only_premium and not s["paid_premium"]:
                continue
            v = s[key]
            if v:
                c[v] = c.get(v, 0) + 1
        return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))

    zoning_counts = counts("zoning")
    prem = [s for s in used if s["paid_premium"]]
    multi = sum(1 for s in used if s["parcels"] > 1)
    activity = {
        "deeds_used": n, "multi_parcel_deeds_grouped": multi, "window": f"{cutoff.isoformat()} to {as_of.isoformat()}",
        "buyer_source": buyer_source if not price_only else "none (price-only)", "price_only": price_only, "price_kind": price_kind,
        "confidence": conf, "confidence_reason": conf_why, "skipped": skipped, "evidence_counts": ev_counts,
        "acres": {"p10": r2(quantile(ac, .1)), "p25": r2(quantile(ac, .25)), "median": r2(quantile(ac, .5)),
                  "p75": r2(quantile(ac, .75)), "p90": r2(quantile(ac, .9))} if n else None,
        "price_per_acre": {"p25": r2(quantile(ppa, .25), 0), "median": r2(quantile(ppa, .5), 0), "p75": r2(quantile(ppa, .75), 0)} if n else None,
        "price_per_lot_median": r2(quantile(ppl, .5), 0) if ppl else None,
        "size_band_median_per_acre": {b: round(m) for b, m in band_med.items()},
        "top_zoning": zoning_counts[:8], "top_cities": counts("city")[:8], "top_zips": counts("zip")[:8],
        "top_buyers": [] if price_only else counts("buyer")[:10],
        "premium_deeds": len(prem), "premium_label": PREMIUM_LABEL.replace("25%", f"{a.premium_pct:.0f}%"),
        "funnel": [f for f, _ in funnel], "builder_owned": builder_owned, "premium_min_deeds": PREMIUM_MIN_DEEDS,
        "premium_zips": counts("zip", True)[:5], "premium_zoning": counts("zoning", True)[:5], "premium_cities": counts("city", True)[:5],
    }
    what = "developer purchases" if not price_only else "land sales (all buyers - not developer-specific)"
    box = {"_how": "Made by build_buy_box.py. score_parcels.py reads it with --buy-box. Edit any number; weights are relative points.",
           "label": (preset["label"] + (" - developer buy box" if not price_only else " - land-price buy box") + (f", {a.market}" if a.market else "")),
           "use_case_hint": a.use_case, "built_from_data": enough, "developer_activity": activity,
           "known_developers": known}
    rural_buys = 0
    if enough:
        p10, p25, p75, p90 = quantile(ac, .1), quantile(ac, .25), quantile(ac, .75), quantile(ac, .9)
        box["acres"] = {"min": nice(p10 * 0.75), "max": nice(p90 * 1.25), "ideal_min": nice(p25), "ideal_max": nice(p75)}
        if box["acres"]["ideal_min"] >= box["acres"]["ideal_max"]:
            box["acres"]["ideal_max"] = nice(box["acres"]["ideal_min"] * 1.5)
        RURAL = re.compile(r"agri|\bag\b|a-1|rural|farm|vacant|timber|pasture", re.I)
        dev_zones = [z.lower() for z, c in zoning_counts if c >= 2 and not RURAL.search(z)]
        rural_buys = sum(c for z, c in zoning_counts if RURAL.search(z))
        if dev_zones:
            box["zoning_keywords"] = list(dict.fromkeys(list(preset.get("zoning_keywords", [])) + dev_zones))
        box["developer_anchor"] = {"per_acre": round(quantile(ppa, .5)), "n": n, "low": round(quantile(ppa, .25)),
                                   "high": round(quantile(ppa, .75)),
                                   "source": (f"median $/acre developers paid ({n} deeds)" if not price_only else
                                              f"median $/acre of land {'sales' if C['sale_price'] else 'LISTINGS'} ({n}, all buyers - not developer-specific)")}
        if not price_only:
            pts = [[s["lat"], s["lon"]] for s in used if s["lat"] is not None and s["lon"] is not None]
            if pts:
                box["developer_points"] = pts
                box["distances"] = {"developer_buy": {"ideal": 1, "limit": 10}}
            box["developer_zips"] = [z for z, _ in counts("zip")]
            if pts or box["developer_zips"]:
                box["weights"] = {"activity": 15}
    from_data = (["acres (size range)", "valuation anchor ($/acre)"] + (["zoning keywords (added to the preset's)"] if box.get("zoning_keywords") else [])
                 + (["near-developer-buys factor"] if box.get("weights") else [])) if enough else []
    from_preset = ["factor weights", "distances (highway, power, rail)", "max flood / slope limits", "required access"] + \
        ([] if enough else ["acres (size range)", "zoning keywords"]) + (["preset zoning keywords"] if enough and box.get("zoning_keywords") else [])
    box["_from_data"], box["_from_preset"] = from_data, from_preset
    PRESET = "EBRE default, not derived from your county"
    dist_p = preset.get("distances", {})

    def dtxt(k):
        d = dist_p.get(k)
        return f"best within {d['ideal']} mi, no credit past {d['limit']} mi" if d else "default distance curve"
    w_p = preset.get("weights", {})
    zone_support = sum(c for z, c in zoning_counts if z.lower() in (box.get("zoning_keywords") or [])) if enough else 0
    criteria = [
        {"criterion": "Size (acres)",
         # the range actually used for scoring (box["acres"]), and where it came from
         "value": (f"{box['acres']['min']}-{box['acres']['max']} ac from your sales (sweet spot {box['acres']['ideal_min']}-{box['acres']['ideal_max']} ac; "
                   f"{n} county purchases)" if enough else
                   f"EBRE default {preset['acres']['min']}-{preset['acres']['max']} ac ({n} county purchases seen; {a.min_sales} needed to set from data; "
                   f"sweet spot {preset['acres']['ideal_min']}-{preset['acres']['ideal_max']} ac)"),
         "source": (f"your sales data ({conf.upper()} confidence)" if enough else PRESET),
         "supporting_purchases": (f"{n} of {n}" if enough else f"0 used ({n} seen; {a.min_sales} needed to set it from data)")},
        {"criterion": "Zoning", "value": ", ".join((box.get("zoning_keywords") or preset.get("zoning_keywords", []))[:8]) or "any",
         "source": ("preset keywords plus zones seen in your sales" if (enough and box.get("zoning_keywords")) else PRESET),
         "supporting_purchases": (f"{zone_support} of {n}" if enough else "0 (preset)")},
        {"criterion": "Price anchor ($/acre)", "value": (f"${box['developer_anchor']['per_acre']:,}" if box.get("developer_anchor") else "none: county values in the file are used"),
         "source": (f"median of your sales ({conf.upper()} confidence)" if box.get("developer_anchor") else "not set"),
         "supporting_purchases": (f"{n} of {n}" if box.get("developer_anchor") else "0")},
        {"criterion": "Near recent developer buys", "value": ("within 1 mi best, none past 10 mi" if box.get("developer_points") else
                                                               ("same ZIP as buys" if box.get("developer_zips") else "not used")),
         "source": ("locations of your sales" if box.get("weights") else "not used"),
         "supporting_purchases": (f"{len(box.get('developer_points') or [])} of {n}" if box.get("weights") else "0")},
        {"criterion": "Access (road frontage)", "value": f"{preset.get('min_frontage_ft', 100)} ft frontage for full credit; land-locked fails",
         "source": PRESET, "supporting_purchases": "0 (sales data has no access facts)"},
        {"criterion": "Highway access", "value": dtxt("highway") if ("highway" in w_p or "highway" in dist_p) else "not scored for this use",
         "source": PRESET, "supporting_purchases": "0 (sales data has no infrastructure facts)"},
        {"criterion": "Power (substation / transmission line)", "value": (dtxt("substation") + "; line: " + dtxt("transmission_line")) if ("power" in w_p) else "not scored for this use",
         "source": PRESET, "supporting_purchases": "0 (sales data has no infrastructure facts)"},
        {"criterion": "Rail", "value": dtxt("rail") if "rail" in w_p else "not scored for this use",
         "source": PRESET, "supporting_purchases": "0 (sales data has no infrastructure facts)"},
        {"criterion": "Flood", "value": (f"fails over {preset['max_flood_pct']}% of parcel in the 100-year zone" if preset.get("max_flood_pct") is not None
                                         else "less credit as more of the parcel is in the 100-year zone"),
         "source": PRESET, "supporting_purchases": "0 (sales data has no flood facts)"},
        {"criterion": "Wetlands", "value": "less credit as more of the parcel is mapped NWI wetland", "source": PRESET,
         "supporting_purchases": "0 (sales data has no wetland facts)"},
        {"criterion": "Slope / buildable", "value": f"max {preset.get('max_slope_pct', 10)}% slope counted as buildable", "source": PRESET,
         "supporting_purchases": "0 (sales data has no slope facts)"},
    ]
    box["criteria"] = criteria
    box["criteria_note"] = f"Rows marked '{PRESET}' are presets. Supporting purchases = deeds in your sales file behind each value."
    with open(os.path.join(a.output_dir, "buy_box.json"), "w") as f:
        json.dump(box, f, indent=2)

    L = [f"# Buy box{(' - ' + a.market) if a.market else ''}", "",
         f"**Confidence: {conf.upper()}** - {conf_why}.", ""]
    if conf == "low":
        L += ["**LOW confidence: do not treat this as a real buy box.** There is too little solid evidence. Use it as a rough hint, "
              "and confirm sizes, zoning and prices with local builders or their land brokers before you rely on it.", ""]
    L += ["## Evidence", "",
          f"- Verified grantee purchases (recorded buyer, confirmed by you or your known-developers list): {ev_counts[EVIDENCE[0]]}",
          f"- Keyword-inferred buyers (recorded buyer whose name looks like a builder, not confirmed): {ev_counts[EVIDENCE[1]]}",
          f"- Probable grantees (assessor's current owner whose deed was recorded at this sale): {ev_counts[EVIDENCE[4]]}",
          f"- Current-owner proxies (assessor's current owner assumed to be the buyer, no matching deed date): {ev_counts[EVIDENCE[2]]}"]
    if price_only:
        L.append(f"- Price-only sales (no buyer at all): {ev_counts[EVIDENCE[3]]}")
    if builder_owned is not None:
        bo = builder_owned
        L.append(f"- Builder-owned land now (from your parcel file, current holdings, not purchases with a price): {bo['parcels']} parcels, "
                 f"{bo['owners']} owners, {bo['acres_total']} acres" + (f", median {bo['acres_median']} ac" if bo["acres_median"] else "") +
                 ((". ZIPs: " + ", ".join(f"{z} ({c})" for z, c in bo["top_zips"])) if bo["top_zips"] else "") +
                 ". Shows where builders hold land; it does not set prices. See builder_owned_parcels.csv.")
    L += ["- Left out: " + (", ".join(f"{k} {v}" for k, v in skipped.items() if v) or "none") + ".",
          "- Limits: keyword matching misses builders that buy through plain LLC names and can count non-builders with builder-like "
          "names (check buyers_review.csv); a recorded price can include more than land; current-owner data misses builders who "
          "already sold the lots.", "- " + BEST_SOURCE, "",
          "## How the sales were narrowed down", "", " -> ".join(f for f, _ in funnel), ""] + (
          [f"Steps that removed nothing: {', '.join(unchanged)}. When the first steps keep every sale, the file was already filtered "
           "before it reached the kit (for example the county query asked only for recent sales with a price and acreage), so the "
           "count stays the same. That is expected, not an error. The cut happens at 'land only' and 'bought by a builder / developer'.", ""]
          if unchanged else []) + [
          "## Buy box criteria and how much supports each one", "",
          f"Confidence for the whole buy box: **{conf.upper()}**" + (" (LOW: a rough hint, not a real buy box)" if conf == "low" else "") + ".", "",
          "| Criterion | Value used | Where it came from | Supporting purchases |", "|---|---|---|---|"] + [
          f"| {c['criterion']} | {c['value']} | {c['source']} | {c['supporting_purchases']} |" for c in criteria] + ["",
          "## Where each part of the buy box came from", "",
          "- From your sales data: " + (", ".join(from_data) or "nothing (too few deeds)") + ".",
          f"- From the {a.use_case} preset: " + ", ".join(from_preset) + ".", "",
         f"Built from {n} {what} between {cutoff.isoformat()} and {as_of.isoformat()} "
         f"({multi} multi-parcel deeds counted once). Buyer names came from: {activity['buyer_source']}.", ""]
    if price_only:
        L += ["**Price-only mode.** " + (f"{st} does not make sale prices public, so " if nd_state else "") +
              "this buy box comes from land prices in general (sold comps or listings), not from what developers paid. "
              "It cannot tell you where developers paid a premium. Ask local builders or their land brokers what they pay, "
              "and add a --known-developers list if you get recorded buyer names.", ""]
        if not C["sale_price"]:
            L += ["These are LIST prices (asking), which usually run above what land sells for.", ""]
    elif buyer_source.startswith("assessor"):
        L += ["Buyers here are the assessor's current owners. A builder that bought, platted and sold homes no longer shows as the "
              "owner, so those buys are missing (survivorship gap). A recorder sales file with the grantee fixes this.", ""]
    if not enough:
        L += [f"**Not enough deeds to set a buy box from data** (found {n}, need {a.min_sales}). The preset size and zoning were kept. "
              "Try 36 months, a wider area, --known-developers, or approve buyers in buyers_review.csv.", ""]
    if n:
        A_, P_ = activity["acres"], activity["price_per_acre"]
        L += ["## " + ("What land is selling for" if price_only else
                       "What these few deeds show (LOW confidence: not a reliable pattern)" if conf == "low" else
                       "Recent developer purchase patterns"),
              f"- Size: most deeds are {A_['p25']}-{A_['p75']} acres (median {A_['median']}).",
              f"- Price: median ${P_['median']:,.0f}/acre (middle half ${P_['p25']:,.0f}-${P_['p75']:,.0f})."]
        if activity["price_per_lot_median"]:
            L.append(f"- Per lot: median ${activity['price_per_lot_median']:,.0f} per lot (deeds with a lot count, or lots under 1 acre).")
        if zoning_counts:
            L.append("- Zoning: " + ", ".join(f"{z} ({c})" for z, c in zoning_counts[:5]) + ".")
        if activity["top_zips"]:
            L.append("- Where: " + ", ".join(f"{z} ({c})" for z, c in activity["top_zips"][:5]) + ".")
        if activity["top_buyers"]:
            L.append("- Most active buyers: " + ", ".join(f"{b} ({c})" for b, c in activity["top_buyers"][:5]) + ".")
        if price_only:
            L += ["", "## Premiums", "- Not shown in price-only mode: without buyer names a high price says nothing about what developers pay."]
        else:
            if n < PREMIUM_MIN_DEEDS:
                L += ["", "## Premiums", f"- Not shown: {n} deeds is too few to say where buyers paid a premium (needs {PREMIUM_MIN_DEEDS}+)."]
        if not price_only and n >= PREMIUM_MIN_DEEDS:
            L += ["", "## Deeds that " + activity["premium_label"],
                  f"Compared with the median $/acre of deeds the same size (only size bands with {a.band_min}+ deeds). "
                  "A premium can mean a hot area, a better site, or a price that included more than land."]
            if prem:
                L.append(f"- {len(prem)} of {n} deeds paid a premium.")
                if activity["premium_zips"]:
                    L.append("- ZIPs: " + ", ".join(f"{z} ({c})" for z, c in activity["premium_zips"]) + ".")
                if activity["premium_zoning"]:
                    L.append("- Zoning: " + ", ".join(f"{z} ({c})" for z, c in activity["premium_zoning"]) + ".")
                for s in sorted(prem, key=lambda s: -(s["vs_band_median_pct"] or 0))[:5]:
                    L.append(f"  - {s['sale_date']} {s['buyer']}: {s['acres']} ac at ${s['price_per_acre']:,}/ac "
                             f"(+{s['vs_band_median_pct']}% vs {s['size_band']} median) {s['zip']} {s['zoning']}")
            else:
                L.append("- None in this window (or too few deeds per size band to say).")
    if enough:
        b = box["acres"]
        L += ["", "## The buy box this sets" + (" (rough hint only: LOW confidence)" if conf == "low" else
                                                " (parcels that match recent developer purchase patterns)"),
              f"- Acres: {b['min']}-{b['max']} (sweet spot {b['ideal_min']}-{b['ideal_max']}).",
              f"- Valuation anchor: ${box['developer_anchor']['per_acre']:,}/acre ({box['developer_anchor']['source']})."]
        if box.get("weights"):
            L.append("- New factor: 'Near developer buys' (15 pts) rewards parcels close to recent developer deeds.")
        if box.get("zoning_keywords"):
            L.append("- Zoning that counts as a match: " + ", ".join(box["zoning_keywords"]) + ".")
        if rural_buys:
            L.append(f"- {rural_buys} deeds were agricultural / rural land (rezoning plays). Those zones are not counted as a match.")
    if review:
        L += ["", f"Check buyers_review.csv: {sum(1 for v in review.values() if v['auto_decision'] == 'developer')} buyers counted as developers, "
              f"{sum(1 for v in review.values() if v['auto_decision'] != 'developer')} not. Put Y or N in 'approve' and re-run with "
              "--approved-buyers to fix any wrong calls."]
    L += ["", "Market evidence, not an appraisal. Recorded prices can include buildings or several parcels; check outliers in "
          "developer_sales.csv. Zoning on a sale record is what the parcel had then. Verify current zoning with the city."]
    if price_only:
        L = [l.replace("deeds", "sales").replace("Deeds", "Sales") for l in L]
    with open(os.path.join(a.output_dir, "buy_box_summary.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print(json.dumps({"deeds_used": n, "confidence": conf, "built_from_data": enough, "price_only": price_only,
                      "premium_deeds": len(prem), "median_price_per_acre": activity["price_per_acre"]["median"] if n else None,
                      "buy_box": os.path.join(a.output_dir, "buy_box.json")}, indent=2))
    return box


if __name__ == "__main__":
    main()
