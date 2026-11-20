#!/usr/bin/env python3
"""Score and rank land parcels against a development buy box.

Inputs
  --input      parcel export (CSV/XLSX): county GIS, PropStream, Regrid, Land Portal,
               DataTree, LandGlide, fetch_arcgis_parcels.py output, etc.
  --use-case   general_land | single_family | industrial | warehouse | data_center | solar
  --buy-box    optional JSON that overrides the preset (weights, acres, distances, zoning...)
  --infra      optional infrastructure CSV from fetch_infrastructure.py (or your own:
               layer,lat,lon rows with layer in substation / transmission_line /
               highway_interchange / major_highway / rail / water_plant / industrial_area)
  --comps      optional sold-land comps CSV (acres + sale_price, optional sale_date/lat/lon)

Outputs (in --output-dir)
  parcels_ranked.csv, development_sites.xlsx, summary.json,
  index.html and reports/NN_<apn>.html due-diligence pages for the top parcels.

Rules baked in: unknown data stays unknown (its weight is removed and the
confidence drops); nothing is invented; owner contact columns are copied only
from the input file.
"""
import argparse, datetime as dt, html, json, math, os, re, sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS = os.path.join(HERE, "..", "references", "use-cases.json")

ALIASES = {
    "apn": ["apn", "parcelid", "parcel_id", "parcelnumber", "parcelno", "pin", "pinnum", "pinnumber", "parcelpin", "parcel", "accountnum", "taxid", "folio", "reid"],
    "address": ["address", "siteaddress", "situsaddress", "propertyaddress", "parceladd", "situs", "location"],
    "city": ["city", "sitecity", "situscity", "parcelcity", "propertycity"],
    "county": ["county", "countyname"],
    "state": ["state", "sitestate", "situsstate", "propertystate"],
    "zip": ["zip", "zipcode", "sitezip", "situszip", "parcelzip", "propertyzip", "zipnum"],
    "lat": ["lat", "latitude", "centroidlat", "y"],
    "lon": ["lon", "lng", "long", "longitude", "centroidlon", "x"],
    "acres": ["lotacreage", "lotsizeacre", "lotsizeac", "acreage1", "acres", "acreage", "lotacres", "lotsizeacres", "calcacres", "gisacres", "deededacres", "totalacres"],
    "zoning": ["zoning", "zone", "zoningcode", "zoningdesc", "zoningdescription"],
    "land_use": ["landusestandardized", "landusegeneral", "landuse", "usecode", "landusecode", "propertyuse", "landusedesc", "usedescription", "propertytype", "classdesc", "typeusedecode", "landclassdecode"],
    "owner": ["owner1fullname", "ownerfullname", "owner1name", "owner", "ownername", "owner1", "ownername1", "owners", "deedholder"],
    "owner_type": ["ownertype", "owntype"],
    "mail_address": ["mailingaddress1", "mailingaddress", "mailaddress", "owneraddress", "mailingstreet", "mailstreet", "mailaddr", "mailaddr1", "mailingaddr1", "addr1"],
    "mail_csz": ["mailcitystatezip", "mailingcitystatezip", "citystatezip", "mailaddr2", "mailingaddr2", "addr2"],
    "mail_city": ["mailingcity", "mailcity", "ownercity"],
    "mail_state": ["mailingstate", "mailstate", "ownerstate"],
    "mail_zip": ["mailingzip", "mailzip", "ownerzip"],
    "owner_phone": ["phone", "ownerphone", "phone1", "mobile", "cellphone"],
    "owner_email": ["email", "owneremail", "email1"],
    "last_sale_date": ["lastsalerecordingdate", "lastsalerecdate", "lastsaledate", "saledate", "recordingdate", "deeddate", "lastsale"],
    "last_sale_price": ["lastsaleprice", "saleprice", "lastsaleamount"],
    "assessed_value": ["assessedvalue", "totalvalueassd", "totalassessedvalue", "assessedtotal", "taxablevalue"],
    "land_value": ["landvalue", "landval", "assessedlandvalue", "marketlandvalue", "appraisedlandvalue"],
    "market_value": ["estvalue", "estimatedmarketvalue", "marketvalue", "totalmarketvalue", "estimatedvalue", "estvalue", "avm", "justvalue"],
    "asking_price": ["askingprice", "listprice", "price", "offerprice"],
    "frontage_ft": ["roadfrontageft", "roadfrontage", "frontage", "frontageft"],
    "landlocked": ["landlocked", "islandlocked"],
    "flood_pct": ["floodpct", "femafloodpct", "floodzonepct", "pctflood", "femaflood"],
    "fema_zone": ["femazone", "femazones", "floodzone", "fldzone"],
    "wetlands_pct": ["wetlandspct", "wetlandpct", "pctwetlands", "wetlandspctest", "wetlands"],
    "buildable_pct": ["buildablepct", "buildablepctest", "pctbuildable", "buildable"],
    "slope_pct": ["slopepct", "avgslope", "slopepctest", "slope"],
    "mortgage": ["totalopenloans", "estremainingbalanceofopenloans", "openloanbalance", "mortgage", "mortgagebalance", "openmortgage", "loanbalance", "mortgageamount"],
    "tax_delinquent": ["taxdelinquentyear", "taxdelinquent", "delinquent", "taxdefault", "taxdelinquentyear"],
    "public_water": ["publicwater", "water", "waterservice", "municipalwater"],
    "public_sewer": ["publicsewer", "sewer", "sewerservice"],
    "jurisdiction": ["planningjurisdiction", "jurisdiction", "municipality", "zoningjurisdiction", "citylimits", "incorporated", "etj", "inetj", "cityjurisdiction"],
    "use_value": ["cauv", "cauvvalue", "cauvflag", "currentuse", "currentusevalue", "usevalue", "agusevalue", "farmuse", "presentusevalue", "greenbelt", "agvalue", "uservalue", "deferral", "farmassessed"],
    "mail_county": ["mailingcounty", "mailcounty", "ownercounty"],
    "record_url": ["recordurl", "countyurl", "coparcelurl", "assessorurl", "url"],
}
PRECOMPUTED = {
    "highway": ["disthighwaymi", "highwaymi", "milestohighway", "distinterstatemi", "disttointerstatemi"],
    "substation": ["distsubstationmi", "substationmi", "milestosubstation"],
    "transmission_line": ["disttransmissionmi", "transmissionmi", "milestotransmission"],
    "rail": ["distrailmi", "railmi", "milestorail"],
}
FACTOR_LABEL = {"access": "Access", "highway": "Highway access", "power": "Power", "rail": "Rail", "utilities": "Water / sewer",
                "size": "Size", "zoning": "Zoning / use", "flood": "FEMA flood", "wetlands": "Wetlands", "slope": "Slope / buildable",
                "valuation": "Valuation", "activity": "Near developer buys"}
SOURCE_HINT = {"access": "your file", "size": "your file", "zoning": "your file (verify with the city)",
               "flood": "FEMA NFHL via your file / enrich_constraints.py", "wetlands": "USFWS NWI via your file / enrich_constraints.py (screen only)",
               "slope": "USGS 3DEP estimate via your file / enrich_constraints.py", "utilities": "your file",
               "valuation": "price vs anchor", "activity": "developer sales (buy_box.json)",
               "highway": "OpenStreetMap", "power": "OpenStreetMap", "rail": "OpenStreetMap"}
DISCLAIMER = ("SCREENING TOOL ONLY. Public data has gaps. This does not predict profit or what a developer will pay, and it does not "
              "replace a survey, title search, appraisal, wetlands delineation, flood determination or a zoning letter. "
              "Verify zoning with the city or county.")
PUBLIC_OWNER = re.compile(r"\b(united states|usa|u s a|federal|bureau of land|blm|forest service|state of|county of|city of|town of|"
                          r"village of|township|school district|department of|dept of|municipal|government|public works|"
                          r"housing authority|water district|irrigation district|state)\b", re.I)


EXCLUDED_OWNER = [
    ("builder / developer", r"\b(homes|home builders?|builders?|construction|development|developers?|communities|lennar|d ?r horton|pulte|nvr|ryan homes|toll brothers|kb home|meritage|taylor morrison|century communities)\b"),
    ("HOA / owners association", r"\b(hoa|homeowners?'? ?assn|homeowners?'? ?association|owners'? ?association|property owners|community association|poa)\b"),
    ("utility", r"\b(electric|power company|power co|energy|gas company|gas co|water company|water co|utility|utilities|telephone|telecom|cooperative|co-op|pipeline|water district|sanitary district|sewer district)\b"),
    ("railroad", r"\b(railroad|railway|rail road|r r co|csx|norfolk southern|union pacific|bnsf|amtrak)\b"),
    ("cemetery", r"\b(cemetery|cemetary|memorial gardens|memorial park|memorial$|burial|funeral|mausoleum)"),
    ("church / religious", r"\b(church|ministries|ministry|diocese|parish|congregation|temple|mosque|synagogue|baptist|methodist|presbyterian|lutheran|catholic)\b"),
    ("conservation / easement", r"\b(conservancy|conservation|nature preserve|preserve|easement|open space|audubon)\b"),
]


# A name is "entity-shaped" when it carries a legal-entity or organisation word, or is a known
# national builder / railroad. Exclusion keywords are only matched on entity-shaped names, so a
# person named TEMPLE, BAPTIST, POWER or BUILDER is never excluded.
ENTITY_SHAPE = re.compile(
    r"\b(llc|l l c|inc|incorporated|corp|corporation|co|company|ltd|lp|llp|lllp|pllc|plc|partners|partnership|holdings|group|"
    r"association|assn|assoc|hoa|poa|church|ministries|ministry|diocese|parish|congregation|mosque|synagogue|cemetery|cemetary|"
    r"railroad|railway|r r co|conservancy|district|authority|cooperative|co-op|coop|foundation|society|utilities|bank|memorial gardens|memorial park|memorial$|funeral|mausoleum|"
    r"lennar|pulte|nvr|toll brothers|kb home|meritage|taylor morrison|ryan homes|d ?r horton|csx|norfolk southern|union pacific|bnsf|amtrak)\b", re.I)


def entity_shaped(name):
    return bool(ENTITY_SHAPE.search(str(name or "")))


def owner_exclusion(owner, land_use, extra_builders=None, detail=False):
    """Owner-type exclusion label (or None). detail=True returns (label, matched word)."""
    text = str(owner or "").strip()
    hit = None
    if entity_shaped(text):
        for label, rx in EXCLUDED_OWNER:
            m = re.search(rx, text, re.I)
            if m:
                hit = (label, m.group(0))
                break
    if not hit:
        for name in extra_builders or []:
            if name and norm(name) and norm(name) in norm(text):
                hit = ("builder / developer (known_developers)", name)
                break
    if not hit:
        m = re.search(r"conservation easement|cemetery|right of way|\brow\b|railroad|utility", str(land_use or ""), re.I)
        if m:
            hit = ("use: " + m.group(0).lower(), m.group(0))
    if detail:
        return hit
    return hit[0] if hit else None


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def load_table(path):
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path, dtype=str)
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, keep_default_na=False)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"Could not read {path}")


def pick(df, canon, extra=None):
    """First alias column that has data; an all-blank column only if nothing better exists
    (Wake's TYPE_USE_DECODE is empty on vacant land while LAND_CLASS_DECODE says Cemetery)."""
    cols = {norm(c): c for c in df.columns}
    first = None
    for a in (extra or ALIASES.get(canon, [canon])):
        if a in cols:
            col = cols[a]
            first = first or col
            try:
                vals = df[col].astype(str).str.strip().str.lower()
                if (~vals.isin(["", "nan", "none", "null"])).any():
                    return col
            except Exception:
                return col
    return first


def num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("$", "").replace("%", "")
    if s == "" or s.lower() in ("nan", "none", "null", "n/a", "na", "-", "unknown"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def yes(v):
    s = str(v or "").strip().lower()
    if s in ("y", "yes", "true", "t", "1", "x"):
        return True
    if s in ("n", "no", "false", "f", "0"):
        return False
    return None


def date(v):
    s = str(v or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{12,13}", s):  # epoch ms (ArcGIS)
        return dt.datetime.fromtimestamp(int(s) / 1000, dt.timezone.utc).date()
    try:
        return pd.to_datetime(s, errors="raise").date()
    except Exception:
        return None


def lin(d, ideal, limit):
    if d is None:
        return None
    if d <= ideal:
        return 1.0
    if d >= limit:
        return 0.0
    return 1.0 - (d - ideal) / (limit - ideal)


def nearest_miles(lat, lon, pts):
    """lat/lon arrays (n) vs pts (m,2) -> distance in miles to nearest point, chunked."""
    if pts is None or len(pts) == 0:
        return np.full(len(lat), np.nan)
    out = np.empty(len(lat))
    plat, plon = np.radians(pts[:, 0]), np.radians(pts[:, 1])
    for i in range(0, len(lat), 500):
        la = np.radians(lat[i:i + 500])[:, None]; lo = np.radians(lon[i:i + 500])[:, None]
        a = np.sin((plat - la) / 2) ** 2 + np.cos(la) * np.cos(plat) * np.sin((plon - lo) / 2) ** 2
        out[i:i + 500] = (2 * 3958.8 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))).min(axis=1)
    return out


def load_box(use_case, box_path, args):
    presets = json.load(open(PRESETS))
    if use_case not in presets:
        raise SystemExit(f"Unknown use case {use_case}. Pick one of: {', '.join(k for k in presets if not k.startswith('_'))}")
    box = json.loads(json.dumps(presets[use_case]))
    box["use_case"] = use_case
    if box_path:
        user = json.load(open(box_path))
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(box.get(k), dict):
                box[k].update(v)
            else:
                box[k] = v
    if args.min_acres is not None: box["acres"]["min"] = args.min_acres
    if args.max_acres is not None: box["acres"]["max"] = args.max_acres
    if args.max_price is not None: box["max_price"] = args.max_price
    if args.zoning: box["zoning_keywords"] = [z.strip().lower() for z in args.zoning.split(",") if z.strip()]
    if args.max_flood_pct is not None: box["max_flood_pct"] = args.max_flood_pct
    tot = sum(box["weights"].values())
    box["weights"] = {k: v * 100.0 / tot for k, v in box["weights"].items() if v}
    box.setdefault("distances", {})
    return box


def comp_anchor(comps_path, args):
    if args.comp_anchor_per_acre:
        return {"per_acre": args.comp_anchor_per_acre, "n": None, "source": "user-supplied $/acre", "low": None, "high": None}
    if not comps_path:
        return None
    c = load_table(comps_path)
    ac, pr = pick(c, "acres"), pick(c, "last_sale_price", ALIASES["last_sale_price"] + ["price", "soldprice", "saleamount"])
    if not (ac and pr):
        raise SystemExit("Comps file needs acres and sale price columns.")
    ppa = []
    for _, r in c.iterrows():
        a, p = num(r[ac]), num(r[pr])
        if a and p and a > 0 and p > 1000:
            ppa.append(p / a)
    if len(ppa) < 2:
        return None
    s = pd.Series(ppa)
    q1, q3 = s.quantile(.25), s.quantile(.75); iqr = q3 - q1
    clean = s[(s >= q1 - 1.5 * iqr) & (s <= q3 + 1.5 * iqr)] if len(s) >= 4 else s
    return {"per_acre": float(clean.median()), "n": int(len(clean)), "dropped_outliers": int(len(s) - len(clean)),
            "low": float(clean.quantile(.25)), "high": float(clean.quantile(.75)), "source": f"comp median ({len(clean)} clean sales)"}


def score(df, box, infra, anchor, args):
    C = {k: pick(df, k) for k in ALIASES}
    county_codes = {c.strip().upper() for c in (getattr(args, "county_code", None) or []) if c.strip()}
    if C["mail_csz"] and not (C["mail_city"] or C["mail_state"] or C["mail_zip"]):
        # one "CITY ST 12345-6789" mailing line (common on county layers): split it
        parts = df[C["mail_csz"]].astype(str).str.extract(r"^\s*(.*?)[\s,]+([A-Za-z]{2})[\s,]+(\d{5})")
        df["_mail_city"], df["_mail_state"], df["_mail_zip"] = parts[0], parts[1].str.upper(), parts[2]
        C["mail_city"], C["mail_state"], C["mail_zip"] = "_mail_city", "_mail_state", "_mail_zip"
    if not C["acres"]:
        raise SystemExit("No acreage column found. Add one named 'acres'.")
    n = len(df)
    lat = np.array([num(v) if C["lat"] else None for v in (df[C["lat"]] if C["lat"] else [None] * n)], dtype=float)
    lon = np.array([num(v) if C["lon"] else None for v in (df[C["lon"]] if C["lon"] else [None] * n)], dtype=float)
    has_xy = ~(np.isnan(lat) | np.isnan(lon))
    dist = {}
    for layer in ("highway", "substation", "transmission_line", "rail", "water_plant", "industrial_area"):
        pre = pick(df, layer, PRECOMPUTED.get(layer, []))
        if pre:
            dist[layer] = np.array([num(v) if num(v) is not None else np.nan for v in df[pre]], dtype=float)
            continue
        if infra is None:
            continue
        layers = ["highway_interchange", "major_highway"] if layer == "highway" else [layer]
        if layer == "highway":
            # prefer interchanges (on-ramps); a parcel next to a limited-access highway w/o ramp is not "access"
            ij = infra[infra.layer == "highway_interchange"][["lat", "lon"]].to_numpy(float)
            mh = infra[infra.layer == "major_highway"][["lat", "lon"]].to_numpy(float)
            d1 = nearest_miles(np.nan_to_num(lat), np.nan_to_num(lon), ij) if len(ij) else np.full(n, np.nan)
            d2 = nearest_miles(np.nan_to_num(lat), np.nan_to_num(lon), mh) if len(mh) else np.full(n, np.nan)
            d = np.where(np.isnan(d1), d2 * 1.5, np.fmin(d1, d2 * 1.5))
            if len(ij) or len(mh):
                dist[layer] = np.where(has_xy, d, np.nan)
            continue
        pts = infra[infra.layer.isin(layers)][["lat", "lon"]].to_numpy(float)
        if len(pts):
            dist[layer] = np.where(has_xy, nearest_miles(np.nan_to_num(lat), np.nan_to_num(lon), pts), np.nan)
    # ---- developer activity (from buy_box.json made by build_buy_box.py)
    dev_pts = np.array([p for p in (box.get("developer_points") or []) if p and len(p) == 2], dtype=float).reshape(-1, 2)
    if len(dev_pts):
        dist["developer_buy"] = np.where(has_xy, nearest_miles(np.nan_to_num(lat), np.nan_to_num(lon), dev_pts), np.nan)
    dev_zips = {str(z)[:5] for z in (box.get("developer_zips") or [])}
    D = box.get("distances", {})
    W = box["weights"]
    today = dt.date.today()
    file_ppa = []
    if C["land_value"] or C["market_value"]:
        for _, r in df.iterrows():
            a = num(r[C["acres"]]); v = num(r[C["land_value"]]) if C["land_value"] else None
            v = v if v else (num(r[C["market_value"]]) if C["market_value"] else None)
            if a and v and a > 0:
                file_ppa.append(v / a)
    file_anchor = float(np.median(file_ppa)) if len(file_ppa) >= 5 else None

    county_zips = {str(v).strip()[:5] for v in (df[C["zip"]] if C["zip"] else []) if str(v).strip()}
    recs = []
    for i, (_, r) in enumerate(df.iterrows()):
        g = lambda k: r[C[k]] if C[k] else None
        acres = num(g("acres"))
        f, note, gates, flags = {}, {}, [], []
        fsrc = {}
        # ---- access
        ll = yes(g("landlocked")); fr = num(g("frontage_ft"))
        if ll is True:
            f["access"], note["access"] = 0.0, "land-locked"
            if box.get("require_access", True): gates.append("land-locked")
        elif fr is not None:
            need = box.get("min_frontage_ft", 100)
            f["access"], note["access"] = min(1.0, fr / need), f"{fr:,.0f} ft frontage"
        elif ll is False:
            f["access"], note["access"] = 0.8, "not land-locked (frontage unknown)"
        # ---- distances
        def dval(layer):
            return None if layer not in dist or np.isnan(dist[layer][i]) else float(dist[layer][i])
        hw = dval("highway")
        if hw is not None:
            d = D.get("highway", {"ideal": 2, "limit": 15})
            f["highway"], note["highway"] = lin(hw, d["ideal"], d["limit"]), f"{hw:.1f} mi to highway access"
        sub, tl = dval("substation"), dval("transmission_line")
        if sub is not None or tl is not None:
            mix = box.get("power_mix", {"substation": 0.7, "transmission_line": 0.3})
            parts, wsum, txt = 0.0, 0.0, []
            if sub is not None:
                d = D.get("substation", {"ideal": 2, "limit": 10}); parts += mix["substation"] * lin(sub, d["ideal"], d["limit"]); wsum += mix["substation"]; txt.append(f"{sub:.1f} mi substation")
            if tl is not None:
                d = D.get("transmission_line", {"ideal": 1, "limit": 6}); parts += mix["transmission_line"] * lin(tl, d["ideal"], d["limit"]); wsum += mix["transmission_line"]; txt.append(f"{tl:.1f} mi transmission line")
            f["power"], note["power"] = parts / wsum, ", ".join(txt) + " (distance to mapped lines, not capacity)"
            if box.get("max_substation_mi") and sub is not None and sub > box["max_substation_mi"]:
                gates.append(f"substation > {box['max_substation_mi']} mi")
        rl = dval("rail")
        if rl is not None:
            d = D.get("rail", {"ideal": 1, "limit": 8})
            f["rail"], note["rail"] = lin(rl, d["ideal"], d["limit"]), f"{rl:.1f} mi to rail"
        # ---- near developer buys
        if "activity" in W:
            db = dval("developer_buy")
            if db is not None:
                d = D.get("developer_buy", {"ideal": 1, "limit": 10})
                f["activity"], note["activity"] = lin(db, d["ideal"], d["limit"]), f"{db:.1f} mi to a recent developer purchase"
            elif dev_zips and str(g("zip") or "").strip()[:5]:
                hit = str(g("zip")).strip()[:5] in dev_zips
                f["activity"], note["activity"] = (0.8 if hit else 0.2), ("same ZIP as recent developer purchases" if hit else "no recent developer purchases in this ZIP")
        # ---- utilities
        pw, ps = yes(g("public_water")), yes(g("public_sewer"))
        if pw is not None or ps is not None:
            vals = [v for v in (pw, ps) if v is not None]
            f["utilities"] = sum(vals) / len(vals)
            note["utilities"] = ", ".join(x for x in ((f"water {'yes' if pw else 'no'}" if pw is not None else ""), (f"sewer {'yes' if ps else 'no'}" if ps is not None else "")) if x) + " (from your file)"
            fsrc["utilities"] = "your file: " + ", ".join(c for c in (C["public_water"], C["public_sewer"]) if c)
        else:
            flags.append("water / sewer unknown (no utility layer or column)")
        # ---- size
        A = box["acres"]
        if acres is not None:
            if acres < A["min"] or acres > A["max"]:
                gates.append(f"size {acres:,.1f} ac outside {A['min']}-{A['max']} ac")
                f["size"] = 0.0
            elif A["ideal_min"] <= acres <= A["ideal_max"]:
                f["size"] = 1.0
            elif acres < A["ideal_min"]:
                f["size"] = 0.5 + 0.5 * (acres - A["min"]) / max(A["ideal_min"] - A["min"], 1e-9)
            else:
                f["size"] = 0.5 + 0.5 * (A["max"] - acres) / max(A["max"] - A["ideal_max"], 1e-9)
            note["size"] = f"{acres:,.2f} ac"
        else:
            gates.append("no acreage")
        # ---- zoning / use
        z = " ".join(str(x) for x in (g("zoning"), g("land_use")) if x and str(x).strip()).lower()
        if z:
            kws = box.get("zoning_keywords", [])
            excl = [k.lower() for k in box.get("zoning_exclude", [])]
            if excl and any(k in z for k in excl):
                f["zoning"] = 0.0; gates.append("excluded zoning/use")
            elif any(k in z for k in kws):
                f["zoning"] = 1.0
            elif re.search(r"vacant|agri|rural|farm|undeveloped|ag\b|timber|pasture", z):
                f["zoning"] = 0.55; flags.append("may need rezoning")
            elif re.search(r"improved|residential|commercial|office|retail", z):
                f["zoning"] = 0.3
            else:
                f["zoning"] = 0.4
            note["zoning"] = z[:60]
        # ---- flood
        fp = num(g("flood_pct")); fz = str(g("fema_zone") or "").upper()
        if "UNMAPPED" in fz or "NOT MAPPED" in fz or "NO DATA" in fz:
            fp = None
            flags.append("flood: not mapped by FEMA here - unknown, not safe")
        elif fp is not None:
            f["flood"], note["flood"] = max(0.0, 1 - fp / 50.0), f"{fp:.0f}% of parcel in the FEMA 100-year flood zone" + (f" ({fz})" if fz else "") + " (FEMA NFHL screen)"
        elif fz:
            sfha = bool(re.search(r"\b(A|AE|AH|AO|AR|A99|V|VE)\b", fz.replace("|", " ")))
            f["flood"] = 0.3 if sfha else 1.0
            note["flood"] = (f"FEMA zone {fz} touches the parcel; % of parcel unknown" if sfha else f"0% of parcel in the FEMA 100-year flood zone (zone {fz})")
            fp = None if sfha else 0.0
        if box.get("max_flood_pct") is not None and fp is not None and fp > box["max_flood_pct"]:
            gates.append(f"flood {fp:.0f}% > {box['max_flood_pct']}%")
        # ---- wetlands
        wp_ = num(g("wetlands_pct"))
        if wp_ is not None:
            f["wetlands"], note["wetlands"] = max(0.0, 1 - wp_ / 40.0), f"{wp_:.0f}% of parcel mapped as NWI wetlands (screen only, not a delineation)"
        # ---- slope
        bp, sp = num(g("buildable_pct")), num(g("slope_pct"))
        ms = box.get("max_slope_pct", 10)
        if bp is not None:
            f["slope"], note["slope"] = min(1.0, bp / 90.0), f"{bp:.0f}% buildable"
        elif sp is not None:
            f["slope"], note["slope"] = lin(sp, ms * 0.4, ms * 2), f"~{sp:.1f}% avg slope"
        # ---- valuation
        uv = g("use_value")
        farm = (yes(uv) is True) or (num(uv) is not None and num(uv) > 0) or bool(re.search(r"\b(cauv|current use|use value|farm use|greenbelt|agricultural use)\b", z))
        ask = num(g("asking_price"))
        basis, basis_src = None, None
        if ask:
            basis, basis_src = ask, "asking price"
        else:
            lv = num(g("land_value")) or num(g("market_value"))
            if lv and farm:
                flags.append("farm / use-value assessment: county value is not market value (not scored as a bargain)")
            elif lv:
                basis, basis_src = lv, "county land/market value"
        anc = anchor["per_acre"] if anchor else file_anchor
        if basis and acres and anc:
            ratio = (basis / acres) / anc
            f["valuation"] = lin(ratio, 0.6, 1.4)
            note["valuation"] = f"${basis / acres:,.0f}/ac ({basis_src}) vs ${anc:,.0f}/ac anchor"
            fsrc["valuation"] = basis_src + " vs " + ((anchor or {}).get("source") or "median county value in file")
        if box.get("max_price") and ask and ask > box["max_price"]:
            gates.append(f"asking ${ask:,.0f} > max ${box['max_price']:,.0f}")
        # ---- owner / motivation
        owner = str(g("owner") or "").strip(); otype = str(g("owner_type") or "").strip()
        public = bool(PUBLIC_OWNER.search(otype)) or bool(re.search(r"\b(united states|state of|county of|city of|town of|school district|bureau of land)\b", owner, re.I))
        if public and not args.include_public:
            gates.append("public / government owner")
        exo = None if args.keep_all_owners else owner_exclusion(owner, g("land_use"), box.get("known_developers"), detail=True)
        if exo:
            gates.append("owner type: " + exo[0])
        elif public and not args.include_public:
            pm = PUBLIC_OWNER.search(otype) or re.search(r"\b(united states|state of|county of|city of|town of|school district|bureau of land)\b", owner, re.I)
            exo = ("public / government owner", pm.group(0) if pm else "owner type")
        mot, mot_notes = 0.0, []
        sd = date(g("last_sale_date"))
        yrs = (today - sd).days / 365.25 if sd else None
        if yrs is not None:
            mot += min(30, yrs * 2); mot_notes.append(f"held {yrs:.0f} yrs")
        ms_, mz = str(g("mail_state") or "").strip().upper(), str(g("mail_zip") or "").strip()[:5]
        ps_, pz = str(g("state") or "").strip().upper(), str(g("zip") or "").strip()[:5]
        mc_, pc_ = norm(g("mail_county") or ""), norm(g("county") or "")
        if ms_ and ps_ and ms_ != ps_:
            mot += 25; mot_notes.append("out-of-state owner")
        elif mc_ and pc_ and mc_ != pc_:
            mot += 15; mot_notes.append("out-of-county owner")
        elif mz and county_zips and ms_ == ps_ and mz not in county_zips:
            mot += 12; mot_notes.append("likely out-of-county owner (mailing ZIP not in this county's parcel ZIPs)")
        mg = g("mortgage"); mgv = num(mg)
        if (mgv is not None and mgv == 0) or str(mg or "").strip().lower() in ("none", "no", "none on record", "free and clear"):
            mot += 15; mot_notes.append("no mortgage on record")
        td = yes(g("tax_delinquent")) if num(g("tax_delinquent")) is None or num(g("tax_delinquent")) in (0, 1) else True
        if td:
            mot += 20; mot_notes.append("tax delinquent")
        if re.search(r"\b(estate of|est of|heirs?|deceased|decd|dec'd)\b", owner, re.I) or (
                re.search(r"\bestate\b", owner, re.I) and not re.search(r"\b(real estate|estates? (llc|inc|co|corp|lp)|trust)\b", owner, re.I)):
            mot += 10; mot_notes.append("estate / heirs")
        elif re.search(r"\b(etal|et al|et ux)\b", owner, re.I):
            mot += 5; mot_notes.append("multiple owners")
        elif re.search(r"\btrust(ee)?s?\b", owner, re.I):
            mot += 5; mot_notes.append("trust owner (a living trust is not an estate)")
        mot = min(100.0, mot)
        known = {k: v for k, v in f.items() if k in W and v is not None}
        kw = sum(W[k] for k in known)
        conf = kw / 100.0
        land = 100.0 * sum(W[k] * v for k, v in known.items()) / kw if kw else 0.0
        rank_score = land * (0.6 + 0.4 * conf)
        mw = args.motivation_weight
        priority = (1 - mw) * rank_score + mw * mot if mot_notes else rank_score * (1 - mw / 2)
        ev = None
        if acres and (anchor or file_anchor):
            src = []
            if anchor:
                src.append((anchor["per_acre"], 0.6, anchor["source"]))
            lvv = None if farm else (num(g("land_value")) or num(g("market_value")))
            if lvv:
                src.append((lvv / acres, 0.4, "county land/market value"))
            elif not anchor and file_anchor:
                src.append((file_anchor, 1.0, "file median county value"))
            tw = sum(s[1] for s in src)
            ppa = sum(s[0] * s[1] for s in src) / tw
            spread = 0.05 if anchor and anchor.get("n", 0) and anchor["n"] >= 3 else 0.10
            ev = {"per_acre": ppa, "low": ppa * (1 - spread) * acres, "high": ppa * (1 + spread) * acres,
                  "ppa_low": ppa * (1 - spread), "ppa_high": ppa * (1 + spread), "mid": ppa * acres,
                  "sources": [{"source": s[2], "per_acre": s[0], "total": s[0] * acres, "weight": s[1] / tw} for s in src]}
        missing = [FACTOR_LABEL[k] for k in W if k not in known]
        jv = str(g("jurisdiction") or "").strip()
        if jv:
            juris = jv
            if jv.upper() in county_codes:
                juris = jv + " (county)"
            elif not re.search(r"^(county|unincorporated|none|no|n|0|false)$|unincorporated|county", jv, re.I):
                flags.append(f"inside a city or its ETJ ({jv}): city zoning and subdivision rules apply")
        else:
            juris = "unknown - check the city limits / ETJ map"
        for k in f:
            if k not in fsrc:
                fsrc[k] = SOURCE_HINT.get(k, "your file")
        for k, col in (("access", C["frontage_ft"] or C["landlocked"]), ("size", C["acres"]), ("zoning", C["zoning"] or C["land_use"]),
                       ("flood", C["flood_pct"] or C["fema_zone"]), ("wetlands", C["wetlands_pct"]), ("slope", C["buildable_pct"] or C["slope_pct"])):
            if k in f and col:
                fsrc[k] = fsrc[k] + f" (column {col})"
        for k in ("highway", "power", "rail"):
            if k in f:
                pre = [c for c in df.columns if norm(c) in sum((PRECOMPUTED.get(x, []) for x in (["highway"] if k == "highway" else ["substation", "transmission_line"] if k == "power" else ["rail"])), [])]
                fsrc[k] = ("your file: " + ", ".join(pre)) if pre else "OpenStreetMap infrastructure file (distance to mapped features)"
        recs.append({
            "row": i, "apn": str(g("apn") or ""), "address": str(g("address") or ""), "city": str(g("city") or ""),
            "county": str(g("county") or ""), "state": str(g("state") or ""), "zip": str(g("zip") or ""),
            "lat": None if np.isnan(lat[i]) else float(lat[i]), "lon": None if np.isnan(lon[i]) else float(lon[i]),
            "acres": acres, "zoning_use": z, "owner": owner, "owner_type": otype,
            "mail_address": " ".join(str(x) for x in (g("mail_address"), g("mail_city"), g("mail_state"), g("mail_zip")) if x and str(x).strip()),
            "mail_street": str(g("mail_address") or "").strip(), "mail_city": str(g("mail_city") or "").strip(),
            "mail_state": str(g("mail_state") or "").strip(), "mail_zip": str(g("mail_zip") or "").strip()[:5],
            "owner_phone": str(g("owner_phone") or ""), "owner_email": str(g("owner_email") or ""),
            "last_sale": sd.isoformat() if sd else "", "years_held": None if yrs is None else round(yrs, 1),
            "asking_price": ask, "record_url": str(g("record_url") or ""),
            "factors": f, "notes": note, "gates": gates, "flags": flags, "sources": fsrc, "jurisdiction": juris,
            "land_score": round(land, 1), "confidence": round(conf, 2), "motivation": round(mot), "motivation_notes": mot_notes,
            "priority": round(priority, 1), "expected_value": ev, "missing": missing,
            "excluded_owner": exo, "research_next": research_next(missing, flags, juris, owner, f, note),
            "raw": {k: r[C[k]] for k in C if C[k]},
        })
    elig = [x for x in recs if not x["gates"]]
    # Deterministic order. Equal priority is broken by: more factors with data (confidence), then land score,
    # then owner signals, then acreage closest to the buy box's ideal range, then APN (so ties never depend on file order).
    A_ = box["acres"]
    mid = (A_["ideal_min"] + A_["ideal_max"]) / 2.0

    def tiekey(x):
        ac = x["acres"] or 0
        dist = 0.0 if A_["ideal_min"] <= ac <= A_["ideal_max"] else min(abs(ac - A_["ideal_min"]), abs(ac - A_["ideal_max"]))
        return (-x["priority"], -x["confidence"], -x["land_score"], -x["motivation"], dist, abs(ac - mid), str(x["apn"]), x["row"])
    elig.sort(key=tiekey)
    for k, x in enumerate(elig, 1):
        x["rank"] = k
        same = [y for y in elig if y["priority"] == x["priority"]]
        x["tiebreak"] = ("" if len(same) == 1 else
                         f"tied at priority {x['priority']} with {len(same) - 1} other(s); order: data coverage, land score, "
                         "owner signals, acreage fit, then APN")
        x["tier"] = "A - call first" if x["priority"] >= 72 else ("B - work next" if x["priority"] >= 58 else "C - park")
        if x["confidence"] < 0.6:
            x["flags"].append("thin data - verify before ranking high")
    for x in recs:
        if x["gates"]:
            x["rank"], x["tier"] = None, "Excluded"
    return recs, C, dist, file_anchor


def research_next(missing, flags, juris, owner, f, note):
    """One line: the next things to check on this parcel, most important first."""
    todo = []
    j = juris if not juris.startswith("unknown") else ""
    todo.append("confirm zoning and what can be built with " + (j + " planning" if j else "the city / county planning office"))
    if "Access" in missing or (f.get("access") is not None and f["access"] < 0.6):
        todo.append("confirm legal road access and frontage on the county map / a title search")
    if any("water / sewer unknown" in x for x in flags) or "Water / sewer" in missing:
        todo.append("ask the water and sewer utility if service reaches the parcel")
    if "FEMA flood" in missing:
        todo.append("check the FEMA flood map (msc.fema.gov)")
    elif "% of parcel unknown" in str(note.get("flood", "")) or (f.get("flood") is not None and f["flood"] < 0.8):
        todo.append("measure the flood area on the FEMA map")
    if "Wetlands" in missing or (f.get("wetlands") is not None and f["wetlands"] < 0.9):
        todo.append("screen wetlands (NWI) and plan a delineation if a buyer is interested")
    if "Slope / buildable" in missing:
        todo.append("check slope / topography")
    if "Power" in missing:
        todo.append("ask the electric utility about service and capacity")
    if any("inside a city or its ETJ" in x for x in flags):
        todo.append("read the city's subdivision rules")
    if entity_shaped(owner) or re.search(r"\b(estate|heirs|trust)\b", owner, re.I):
        todo.append("find who can sign for the owner (officer, trustee or personal representative)")
    todo.append("title search before any contract")
    return "; ".join(dict.fromkeys(todo))


def explain(x, box):
    """One readable line per factor: points, why, source; unknown factors say so."""
    parts = []
    for k, w in box["weights"].items():
        s = x["factors"].get(k)
        if s is None:
            parts.append(f"{FACTOR_LABEL[k]}: unknown (no data, {w:.0f} pts left out)")
        else:
            parts.append(f"{FACTOR_LABEL[k]}: {s * w:.1f}/{w:.0f} - {x['notes'].get(k, '')} [{x['sources'].get(k, '')}]")
    head = f"Land score {x['land_score']}/100 on known factors, confidence {x['confidence']:.0%}"
    if x["gates"]:
        head += "; EXCLUDED: " + "; ".join(x["gates"])
    return head + " | " + " | ".join(parts)


def maps_links(lat, lon, acres):
    if lat is None:
        return {}
    half = max(0.002, math.sqrt((acres or 5) * 43560) / 364000.0 * 0.9)
    hl = half / math.cos(math.radians(lat))
    return {"google_satellite": f"https://www.google.com/maps/@?api=1&map_action=map&center={lat:.6f},{lon:.6f}&zoom=17&basemap=satellite",
            "google_pin": f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}",
            "imagery": f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox={lon - hl:.6f},{lat - half:.6f},{lon + hl:.6f},{lat + half:.6f}&bboxSR=4326&imageSR=3857&size=640,420&format=jpg&f=image",
            "fema": f"https://msc.fema.gov/portal/search?AddressQuery={lat:.6f}%2C{lon:.6f}"}


CSS = """body{font-family:Arial,Helvetica,sans-serif;color:#222;max-width:860px;margin:24px auto;padding:0 16px}
h1{text-align:center;margin-bottom:4px}h2{color:#2f5d34;border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:28px}
.cards{display:flex;gap:16px;margin:18px 0}.card{flex:1;background:#f5edda;border:1px solid #8a9a7b;text-align:center;padding:14px}
.card .k{font-size:12px;letter-spacing:1px;color:#555}.big{font-size:54px;font-weight:bold;color:#2f5d34}.big small{font-size:22px;color:#777}
.ev{font-size:28px;font-weight:bold;color:#2f5d34;margin-top:12px}.meta{display:flex;justify-content:space-around;text-align:center;font-size:13px;margin:10px 0}
.meta b{display:block;font-size:11px;letter-spacing:1px;color:#555}table{border-collapse:collapse;width:100%;font-size:14px}
th{background:#2f5d34;color:#fff;text-align:left;padding:7px}td{border-bottom:1px solid #e6e6e6;padding:7px}tr.tot td{background:#f5edda;font-weight:bold}
.btn{display:block;background:#2f5d34;color:#fff;text-align:center;padding:12px;text-decoration:none;font-weight:bold;margin:12px 0}
.flag{display:inline-block;background:#fbe3c8;border-radius:10px;padding:2px 9px;margin:2px;font-size:12px}.gray{color:#777;font-size:12px}
img.sat{width:100%;border:1px solid #ccc}"""


def money(v):
    return " - " if v is None else f"${v:,.0f}"


def esc(v):
    return html.escape("" if v is None else str(v))


def report_html(x, box, anchor):
    L = maps_links(x["lat"], x["lon"], x["acres"])
    ev = x["expected_value"]
    W = box["weights"]
    rows = []
    for k, w in W.items():
        s = x["factors"].get(k)
        pts = "n/a" if s is None else f"{s * w:.0f} / {w:.0f}"
        rows.append(f"<tr><td>{FACTOR_LABEL[k]}</td><td>{pts}</td><td>{esc(x['notes'].get(k, 'no data in file - verify'))}</td></tr>")
    known_w = sum(w for k, w in W.items() if x["factors"].get(k) is not None)
    raw_pts = sum(x["factors"][k] * w for k, w in W.items() if x["factors"].get(k) is not None)
    rows.append(f"<tr class='tot'><td>TOTAL</td><td>{raw_pts:.0f} / {known_w:.0f}</td><td>Land Score {x['land_score']:.0f}/100 on known factors - data confidence {x['confidence']:.0%}</td></tr>")
    raw = x["raw"]
    ov = [("APN", x["apn"]), ("County", f"{x['county']} {x['state']}".strip()), ("Size", f"{x['acres']:,.2f} acres" if x["acres"] else " - "),
          ("Road frontage", (f"{num(raw.get('frontage_ft')):,.0f} ft" if num(raw.get("frontage_ft")) is not None else " - ")), ("Land-locked", raw.get("landlocked") or " - "),
          ("Wetlands", x["notes"].get("wetlands", " - ")), ("FEMA flood", x["notes"].get("flood", " - ")),
          ("Buildable / slope", x["notes"].get("slope", " - ")), ("Zoning / use", x["zoning_use"] or " - "),
          ("Last sale", (x["last_sale"] + (f" ({x['years_held']:.0f} yrs)" if x["years_held"] is not None else "")) if x["last_sale"] else " - "),
          ("Mortgage", raw.get("mortgage") or " - "), ("Highway", x["notes"].get("highway", " - ")), ("Power", x["notes"].get("power", " - ")),
          ("Rail", x["notes"].get("rail", " - ")), ("Water / sewer", x["notes"].get("utilities", " - "))]
    ov_html = "".join(f"<tr><td><b>{esc(a)}</b></td><td>{esc(b)}</td><td><b>{esc(c)}</b></td><td>{esc(d)}</td></tr>"
                      for (a, b), (c, d) in zip(ov[0::2], ov[1::2] + [("", "")]))
    val_html = ""
    if ev:
        vr = "".join(f"<tr><td>{esc(s['source'])}</td><td>{money(s['per_acre'])}</td><td>{money(s['total'])}</td><td>{s['weight']:.0%}</td></tr>" for s in ev["sources"])
        vr += f"<tr class='tot'><td>Blended</td><td>{money(ev['per_acre'])}</td><td>{money(ev['mid'])}</td><td>100%</td></tr>"
        val_html = f"<h2>Valuation Sources</h2><table><tr><th>Source</th><th>$ / acre</th><th>Total</th><th>Weight</th></tr>{vr}</table>"
    flags = "".join(f"<span class='flag'>{esc(f)}</span>" for f in x["flags"] + x["motivation_notes"])
    contact = ""
    if x["owner_phone"] or x["owner_email"]:
        contact = f"<br>Phone: {esc(x['owner_phone'] or ' - ')} - Email: {esc(x['owner_email'] or ' - ')} (from your file)"
    sat = f"<h2>Satellite</h2><img class='sat' src='{L['imagery']}' alt='satellite view'><div class='gray'>Imagery: Esri World Imagery. Square approximates parcel size around the centroid, not the legal boundary.</div>" if L else ""
    links = " - ".join(f"<a href='{u}'>{n}</a>" for n, u in (("Google satellite", L.get("google_satellite")), ("Map pin", L.get("google_pin")), ("FEMA map", L.get("fema")), ("County record", x["record_url"] or None)) if u)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Due Diligence Report - {esc(x['apn'] or x['address'])}</title><style>{CSS}</style></head><body>
<h1>Due Diligence Report</h1><div class='gray' style='text-align:center'>{esc(box['label'])} buy box - rank #{x['rank']} - {esc(x['tier'])}</div>
<div class='cards'><div class='card'><div class='k'>LAND SCORE</div><div class='big'>{x['land_score']:.0f}<small>/100</small></div><div class='gray'>confidence {x['confidence']:.0%} - priority {x['priority']:.0f}</div></div>
<div class='card'><div class='k'>EXPECTED VALUE</div><div class='ev'>{(money(ev['low']) + ' - ' + money(ev['high'])) if ev else 'Add comps to estimate'}</div><div class='gray'>{(money(ev['ppa_low']) + ' - ' + money(ev['ppa_high']) + ' / acre') if ev else ''}</div></div></div>
<div class='meta'><div><b>SIZE</b>{x['acres']:,.2f} ac</div><div><b>OWNER</b>{esc(x['owner'] or ' - ')}</div><div><b>LAND USE</b>{esc(x['zoning_use'][:40] or ' - ')}</div></div>
{f"<a class='btn' href='{L['google_satellite']}'>View this parcel on the map -></a>" if L else ''}
<div>{flags}</div>
<h2>Parcel Overview</h2><table>{ov_html}</table>
<h2>Land Score Breakdown</h2><table><tr><th>Factor</th><th>Score</th><th>Notes</th></tr>{''.join(rows)}</table>
{val_html}{sat}
<h2>Owner</h2><p>{esc(x['owner'] or 'Not in file')}<br>Mailing: {esc(x['mail_address'] or 'not in file')}{contact}<br>Motivation signals: {esc(', '.join(x['motivation_notes']) or 'none found in file')}</p>
<h2>Verify before you offer</h2><ul><li>Zoning and permitted use with the county planning office</li><li>Legal access / easements and title</li>
<li>Utility capacity letters (power, water, sewer){'  -  ask the utility about substation capacity' if box['use_case'] == 'data_center' else ''}</li>
<li>Wetlands delineation and FEMA flood determination on the actual boundary</li><li>Recent sold comps from a local land broker</li></ul>
<p class='gray'>{links}<br>Screening estimate from public data and your file, not an appraisal, survey or title opinion. Infrastructure: (c) OpenStreetMap contributors.</p>
</body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--use-case", default="general_land")
    ap.add_argument("--buy-box")
    ap.add_argument("--infra")
    ap.add_argument("--comps")
    ap.add_argument("--comp-anchor-per-acre", type=float)
    ap.add_argument("--min-acres", type=float); ap.add_argument("--max-acres", type=float)
    ap.add_argument("--max-price", type=float); ap.add_argument("--max-flood-pct", type=float)
    ap.add_argument("--zoning", help="comma list of zoning/use keywords that count as a match")
    ap.add_argument("--include-public", action="store_true", help="keep government-owned parcels")
    ap.add_argument("--county-code", action="append", default=[],
                    help="jurisdiction value that means unincorporated county (e.g. WC on Wake County's layer); repeatable")
    ap.add_argument("--keep-all-owners", action="store_true", help="do not exclude builder / HOA / utility / railroad / cemetery / church / conservation owners")
    ap.add_argument("--motivation-weight", type=float, default=0.2, help="0-1 share of priority from owner motivation (0 = pure site fit)")
    ap.add_argument("--top", type=int, default=10, help="due-diligence reports to write")
    ap.add_argument("--market", default="")
    ap.add_argument("--output-dir", default="out")
    a = ap.parse_args(argv)
    box = load_box(a.use_case, a.buy_box, a)
    df = load_table(a.input)
    infra = None
    if a.infra:
        infra = pd.read_csv(a.infra)
        infra = infra.dropna(subset=["lat", "lon"])
    anchor = comp_anchor(a.comps, a)
    if anchor is None and isinstance(box.get("developer_anchor"), dict) and box["developer_anchor"].get("per_acre"):
        # buy_box.json from build_buy_box.py carries the median $/acre developers actually paid
        anchor = dict(box["developer_anchor"])
        anchor.setdefault("source", "median $/acre paid by developers (buy_box.json)")
    recs, C, dist, file_anchor = score(df, box, infra, anchor, a)
    os.makedirs(os.path.join(a.output_dir, "reports"), exist_ok=True)
    ranked = sorted(recs, key=lambda x: (x["rank"] is None, x["rank"] or 0))
    flat = []
    for x in ranked:
        L = maps_links(x["lat"], x["lon"], x["acres"])
        ev = x["expected_value"]
        row = {"rank": x["rank"], "tier": x["tier"], "priority": x["priority"], "land_score": x["land_score"], "confidence": x["confidence"],
               "motivation": x["motivation"], "apn": x["apn"], "address": x["address"], "city": x["city"], "county": x["county"], "state": x["state"], "zip": x["zip"],
               "acres": x["acres"], "zoning_use": x["zoning_use"], "owner": x["owner"], "owner_type": x["owner_type"], "mail_address": x["mail_address"],
               "mail_street": x["mail_street"], "mail_city": x["mail_city"], "mail_state": x["mail_state"], "mail_zip": x["mail_zip"],
               "owner_phone": x["owner_phone"], "owner_email": x["owner_email"], "last_sale": x["last_sale"], "years_held": x["years_held"],
               "asking_price": x["asking_price"], "ev_low": round(ev["low"]) if ev else None, "ev_high": round(ev["high"]) if ev else None}
        for k in box["weights"]:
            s = x["factors"].get(k)
            row[f"{k}_pts"] = None if s is None else round(s * box["weights"][k], 1)
        row["tiebreak"] = x.get("tiebreak", "")
        row.update({"why": "; ".join(v for v in x["notes"].values()), "flags": "; ".join(x["flags"]), "motivation_signals": "; ".join(x["motivation_notes"]),
                    "sig_long_hold": "Y" if (x["years_held"] or 0) >= 10 else "", "sig_out_of_state": "Y" if "out-of-state owner" in x["motivation_notes"] else "",
                    "sig_out_of_county": "Y" if any("out-of-county" in m or "out-of-state" in m for m in x["motivation_notes"]) else "",
                    "sig_tax_delinquent": "Y" if "tax delinquent" in x["motivation_notes"] else "",
                    "sig_no_mortgage": "Y" if "no mortgage on record" in x["motivation_notes"] else "",
                    "sig_estate_heirs": "Y" if "estate / heirs" in x["motivation_notes"] else "",
                    "sig_trust": "Y" if any(m.startswith("trust owner") for m in x["motivation_notes"]) else "",
                    "sig_multiple_owners": "Y" if "multiple owners" in x["motivation_notes"] else "",
                    "owner_is_entity": "Y" if re.search(r"\b(llc|inc|corp|co|company|ltd|lp|llp|partners|partnership|holdings|trust|bank|church)\b", x["owner"] or "", re.I) else "",
                    "excluded_because": "; ".join(x["gates"]), "hard_gate_failures": "; ".join(x["gates"]), "missing_data": ", ".join(x["missing"]),
                    "research_next": x["research_next"],
                    "confidence_label": "high" if x["confidence"] >= 0.8 else ("medium" if x["confidence"] >= 0.6 else "low"),
                    "jurisdiction": x["jurisdiction"], "factor_sources": "; ".join(f"{FACTOR_LABEL[k]}: {v}" for k, v in x["sources"].items()),
                    "score_explained": explain(x, box), "lat": x["lat"], "lon": x["lon"],
                    "map_link": L.get("google_satellite", ""), "record_url": x["record_url"]})
        flat.append(row)
    out = pd.DataFrame(flat)
    out.to_csv(os.path.join(a.output_dir, "parcels_ranked.csv"), index=False)
    elig = out[out["rank"].notna()]
    top = [x for x in ranked if x["rank"] is not None][: a.top]
    report_files = []
    for x in top:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", x["apn"] or x["address"] or str(x["row"]))[:40].strip("-")
        fn = f"{int(x['rank']):02d}_{slug}.html"
        open(os.path.join(a.output_dir, "reports", fn), "w").write(report_html(x, box, anchor))
        report_files.append(fn)
    # workbook
    owners = elig[["rank", "tier", "apn", "address", "acres", "owner", "owner_type", "mail_address", "owner_phone", "owner_email", "years_held", "motivation_signals", "map_link"]].copy()
    owners["contact_status"] = np.where((owners.owner_phone.astype(str).str.len() > 0) | (owners.owner_email.astype(str).str.len() > 0), "from your file", "skip-trace needed")
    breakdown = []
    for x in top:
        for k, w in box["weights"].items():
            s = x["factors"].get(k)
            breakdown.append({"rank": x["rank"], "apn": x["apn"], "factor": FACTOR_LABEL[k], "max_pts": round(w, 1),
                              "pts": None if s is None else round(s * w, 1), "note": x["notes"].get(k, "no data - weight left out"),
                              "source": x["sources"].get(k, "")})
    gaps = pd.DataFrame([{"factor": FACTOR_LABEL[k], "weight": round(w, 1),
                          "parcels_with_data": sum(1 for x in recs if x["factors"].get(k) is not None), "parcels_total": len(recs)} for k, w in box["weights"].items()])
    # which owner signals this file could even show (a missing column means "not checked", not "no")
    sig_cols = [("long hold", C["last_sale_date"]), ("out-of-state owner", C["mail_state"] and (C["state"] or True)),
                ("out-of-county owner", C["mail_county"] or (C["mail_zip"] and C["zip"])), ("no mortgage", C["mortgage"]),
                ("tax delinquent", C["tax_delinquent"]), ("estate / heirs / trust (from the owner name)", C["owner"])]
    # what each signal is, where it comes from, and what happens when it is not available
    sig_info = {
        "long hold": ("years since the last sale (2 pts a year, up to 30)", "last sale date column (county assessor / recorder, PropStream)"),
        "out-of-state owner": ("mailing state differs from the parcel state (+25)", "mailing address columns vs parcel state"),
        "out-of-county owner": ("mailing county differs, or mailing ZIP is not one of this county's parcel ZIPs (+15 / +12)",
                                "mailing county or mailing ZIP vs the parcel ZIPs in your file"),
        "no mortgage": ("no open mortgage on record (+15)", "mortgage / loan column (PropStream, title data)"),
        "tax delinquent": ("property taxes past due (+20)", "tax delinquent column (county tax collector, PropStream)"),
        "estate / heirs / trust (from the owner name)": ("owner name says estate / heirs (+10), et al (+5) or trust (+5)", "owner name"),
    }
    signal_table = [{"signal": n, "what_it_means": sig_info[n][0], "source": sig_info[n][1],
                     "collected_this_run": (("yes (column: " + c + ")") if isinstance(c, str) else "yes") if c else "no",
                     "when_not_available": ("used" if c else "not checked: adds 0 points, is never counted as a 'no', and does not lower the score. "
                                            "Add the column (PropStream or county export) to check it.")}
                    for n, c in sig_cols]
    pd.DataFrame(signal_table).to_csv(os.path.join(a.output_dir, "motivation_signals.csv"), index=False)
    signals_had = [n for n, c in sig_cols if c]
    signals_missing = [n for n, c in sig_cols if not c]
    excl_rows = [{"apn": x["apn"], "owner": x["owner"], "excluded_as": x["excluded_owner"][0], "matched": x["excluded_owner"][1],
                  "mail_address": x["mail_address"], "acres": x["acres"],
                  "to_keep_them": ("re-run with --include-public" if x["excluded_owner"][0].startswith("public") else
                                   "re-run with --keep-all-owners, or remove the word from the owner's name if it is a person")}
                 for x in recs if x.get("excluded_owner")]
    pd.DataFrame(excl_rows, columns=["apn", "owner", "excluded_as", "matched", "mail_address", "acres", "to_keep_them"]).to_csv(
        os.path.join(a.output_dir, "excluded_owners.csv"), index=False)
    factor_cover = {FACTOR_LABEL[k]: sum(1 for x in recs if x["factors"].get(k) is not None) for k in box["weights"]}
    excl = pd.Series([g for x in recs for g in x["gates"]]).str.replace(r"\d[\d,\.]*", "#", regex=True).value_counts() if any(x["gates"] for x in recs) else pd.Series(dtype=int)
    summary = {"market": a.market, "use_case": box["use_case"], "label": box["label"], "parcels_in_file": len(recs), "eligible": int(len(elig)),
               "excluded": int(len(recs) - len(elig)), "tier_counts": elig["tier"].value_counts().to_dict(), "exclusion_reasons": excl.to_dict(),
               "weights": {FACTOR_LABEL[k]: round(v, 1) for k, v in box["weights"].items()}, "infra_layers_used": sorted(dist.keys()),
               "valuation_anchor": anchor or ({"per_acre": file_anchor, "source": "median county land/market value in file"} if file_anchor else None),
               "top": [{"rank": x["rank"], "apn": x["apn"], "acres": x["acres"], "land_score": x["land_score"], "priority": x["priority"], "confidence": x["confidence"]} for x in top],
               "thin_data_in_top": sum(1 for x in top if x["confidence"] < 0.6),
               "next_step_hint": ("Several top parcels are missing flood/wetlands/slope data: run enrich_constraints.py on parcels_ranked.csv (it is already sorted) with --limit 100-200, then score again." if sum(1 for x in top if x["confidence"] < 0.6) >= 3 else ""),
               "reports": report_files, "columns_matched": {k: v for k, v in C.items() if v},
               "owner_signals_in_data": signals_had, "owner_signals_not_in_data": signals_missing, "motivation_signal_table": signal_table,
               "ties_in_top": sum(1 for x in top if x.get("tiebreak")),
               "excluded_owners": len(excl_rows),
               "factors_unknown_everywhere": [k for k, v in factor_cover.items() if v == 0],
               "factors_unknown_somewhere": [k for k, v in factor_cover.items() if 0 < v < len(recs)],
               "preset_factors": box.get("_from_preset", [])}
    with pd.ExcelWriter(os.path.join(a.output_dir, "development_sites.xlsx"), engine="openpyxl") as xw:
        pd.DataFrame({"READ ME FIRST": [DISCLAIMER, "",
                                        "Parcels here match recent developer purchase patterns and the buy box. That is a screen, not a promise "
                                        "that any developer will buy.",
                                        "Unknown factors are left out of the score (see Data Gaps). Owner signals your data had: " +
                                        (", ".join(signals_had) or "none") + ". Not in your data (not checked): " + (", ".join(signals_missing) or "none") + ".",
                                        "Credits: OpenStreetMap contributors (ODbL), USDA NAIP via USGS, FEMA NFHL, USFWS NWI, USGS 3DEP, US Census TIGER."]}
                     ).to_excel(xw, sheet_name="Read me", index=False)
        pd.DataFrame([{"item": k, "value": json.dumps(v) if isinstance(v, (dict, list)) else v} for k, v in summary.items() if k not in ("top", "reports")]).to_excel(xw, sheet_name="Summary", index=False)
        elig.to_excel(xw, sheet_name="Ranked Sites", index=False)
        pd.DataFrame(breakdown).to_excel(xw, sheet_name="Score Breakdown", index=False)
        owners.to_excel(xw, sheet_name="Owner Outreach", index=False)
        out[out["rank"].isna()][["apn", "address", "acres", "owner", "excluded_because"]].to_excel(xw, sheet_name="Excluded", index=False)
        gaps.to_excel(xw, sheet_name="Data Gaps", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(48, max(10, max(len(str(c.value or "")) for c in col[:60]) + 2))
            ws.freeze_panes = "A2"
    json.dump(summary, open(os.path.join(a.output_dir, "summary.json"), "w"), indent=2, default=str)
    idx = "".join(f"<tr><td>{x['rank']}</td><td><a href='reports/{fn}'>{esc(x['apn'] or x['address'])}</a></td><td>{x['acres']:,.1f}</td><td>{x['land_score']:.0f}</td><td>{x['confidence']:.0%}</td><td>{x['priority']:.0f}</td><td>{esc(x['tier'])}</td><td>{esc(x['owner'])}</td></tr>" for x, fn in zip(top, report_files))
    open(os.path.join(a.output_dir, "index.html"), "w").write(f"<!doctype html><html><head><meta charset='utf-8'><title>Top development sites</title><style>{CSS}</style></head><body><h1>Top {len(top)} {esc(box['label'])} sites {esc(a.market)}</h1><p class='gray'>{len(recs)} parcels scored - {len(elig)} passed the buy box - {len(recs) - len(elig)} excluded</p><table><tr><th>#</th><th>Parcel</th><th>Acres</th><th>Land score</th><th>Confidence</th><th>Priority</th><th>Tier</th><th>Owner</th></tr>{idx}</table></body></html>")
    print(json.dumps({k: summary[k] for k in ("parcels_in_file", "eligible", "excluded", "tier_counts", "infra_layers_used", "thin_data_in_top", "next_step_hint", "top")}, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
