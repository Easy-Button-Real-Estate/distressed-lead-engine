#!/usr/bin/env python3
"""Download parcels from any public ArcGIS REST parcel layer (county or state GIS).

Many US counties publish parcels for free at a URL ending in /MapServer/<n> or
/FeatureServer/<n>. This script pages through that layer inside a bounding box
(or a SQL where clause), computes each parcel's centroid and acreage from its
geometry (equal-area projection, not Web Mercator), and writes a CSV plus a
<output>.geometry.json file with the boundaries (used to draw them on satellite images). score_parcels.py reads the CSV.

Usage:
  python fetch_arcgis_parcels.py --layer-url URL --bbox "S,W,N,E" --output parcels.csv
  python fetch_arcgis_parcels.py --layer-url URL --where "ACRES >= 20" --output parcels.csv
  python fetch_arcgis_parcels.py --layer-url URL --list-fields

Only use layers the publisher makes public. No logins, no keys, no scraping of
paid sites. Owner fields are whatever the county publishes; nothing is added.
"""
import argparse, csv, json, math, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import friendly_error, urlopen  # noqa: E402

UA = {"User-Agent": "development-opportunity-finder-skill/2.0"}


def get(url, params, timeout=90):
    q = urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=q.encode(), headers=UA)
            with urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode())
            if "error" in d:
                raise RuntimeError(d["error"])
            return d
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


R_AUTHALIC = 6371007.2  # m, sphere with the same surface area as the WGS84 ellipsoid
SQM_PER_ACRE = 4046.8564224


def laea(lat, lon, lat0, lon0):
    """Lambert azimuthal equal-area projection (sphere) centred on lat0/lon0 -> metres."""
    p, l, p0, l0 = map(math.radians, (lat, lon, lat0, lon0))
    k = math.sqrt(2.0 / (1 + math.sin(p0) * math.sin(p) + math.cos(p0) * math.cos(p) * math.cos(l - l0)))
    x = R_AUTHALIC * k * math.cos(p) * math.sin(l - l0)
    y = R_AUTHALIC * k * (math.cos(p0) * math.sin(p) - math.sin(p0) * math.cos(p) * math.cos(l - l0))
    return x, y


def inv_laea(x, y, lat0, lon0):
    p0, l0 = math.radians(lat0), math.radians(lon0)
    rho = math.hypot(x, y)
    if rho < 1e-9:
        return lat0, lon0
    c = 2 * math.asin(min(1.0, rho / (2 * R_AUTHALIC)))
    lat = math.asin(math.cos(c) * math.sin(p0) + y * math.sin(c) * math.cos(p0) / rho)
    lon = l0 + math.atan2(x * math.sin(c), rho * math.cos(p0) * math.cos(c) - y * math.sin(p0) * math.sin(c))
    return math.degrees(lat), math.degrees(lon)


def ring_area_centroid(ring, lat0, lon0):
    """Signed area (m2) and centroid (x, y in metres) of a lon/lat ring in an equal-area projection.

    Acreage is computed in a Lambert azimuthal equal-area projection centred on the parcel,
    not in Web Mercator (which inflates area by about 1/cos(lat)^2).
    """
    if len(ring) < 3:
        return 0.0, None
    pts = [laea(p[1], p[0], lat0, lon0) for p in ring]
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        c = x1 * y2 - x2 * y1
        a += c; cx += (x1 + x2) * c; cy += (y1 + y2) * c
    a /= 2.0
    if abs(a) < 1e-9:
        return 0.0, None
    return a, (cx / (6 * a), cy / (6 * a))


def geom_stats(g):
    """(acres, centroid lat, centroid lon) for an Esri polygon in lon/lat (outSR 4326)."""
    rings = (g or {}).get("rings") or []
    allpts = [p for r in rings for p in r]
    if not allpts:
        return None, None, None
    lat0 = sum(p[1] for p in allpts) / len(allpts)
    lon0 = sum(p[0] for p in allpts) / len(allpts)
    tot = wx = wy = 0.0
    for r in rings:
        a, c = ring_area_centroid(r, lat0, lon0)
        if c is None:
            continue
        # Esri: outer rings clockwise (negative here), holes counter-clockwise
        tot += -a; wx += -a * c[0]; wy += -a * c[1]
    if abs(tot) < 1e-6:
        return None, None, None
    lat, lon = inv_laea(wx / tot, wy / tot, lat0, lon0)
    return abs(tot) / SQM_PER_ACRE, lat, lon


def simplify(ring, max_pts=200):
    if len(ring) <= max_pts:
        return [[round(p[0], 7), round(p[1], 7)] for p in ring]
    step = len(ring) / float(max_pts)
    out = [ring[int(i * step)] for i in range(max_pts)] + [ring[-1]]
    return [[round(p[0], 7), round(p[1], 7)] for p in out]


APN_FIELDS = ["apn", "parcelid", "parcel_id", "parcelnumber", "parcelno", "pin", "pinnum", "pin_num", "parcel", "taxid", "reid", "folio"]


def apn_of(attrs):
    m = {re.sub(r"[^a-z0-9]", "", k.lower()): v for k, v in attrs.items()}
    for f in APN_FIELDS:
        v = m.get(re.sub(r"[^a-z0-9]", "", f))
        if v not in (None, ""):
            return str(v)
    return ""


LICENSE_TERMS = [
    (r"non[- ]?commercial|not for commercial|no commercial use|commercial use (is )?(prohibited|not permitted)", "non-commercial use only"),
    (r"resale|re-?sell|redistribut|may not (be )?(sold|shared)", "resale / redistribution limits"),
    (r"\bfees?\b|subscription|purchase (the )?data|cost recovery|for a charge", "a fee or subscription"),
    (r"license agreement|licen[cs]e is required|terms of use|written permission", "a licence agreement / terms of use"),
]


def license_flags(text):
    """Words in a layer's licence / use text that limit commercial use, resale, or require a fee."""
    out = []
    for rx, label in LICENSE_TERMS:
        m = re.search(rx, text or "", re.I)
        if m:
            out.append(f"{label} (matched '{m.group(0)}')")
    return out


def write_license(url, meta, folder):
    """Save the publisher's own licence / copyright / use text for the layer next to the data."""
    svc = {}
    try:
        svc = get(re.sub(r"/\d+$", "", url), {"f": "json"}, timeout=30)
    except Exception:
        pass
    parts = []
    for label, d in (("Layer", meta), ("Service", svc)):
        for k in ("copyrightText", "licenseInfo", "accessInformation", "description", "serviceDescription"):
            v = re.sub(r"<[^>]+>", " ", str((d or {}).get(k) or "")).strip()
            if v:
                v = re.sub(r"\s+", " ", v)[:1500]
                parts.append(f"{label} {k}: {v}")
    flags = license_flags(" ".join(parts))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "county_layer_license.txt")
    import datetime as _dt
    with open(path, "a") as f:
        f.write(f"== {url}  (read {_dt.date.today().isoformat()})\n")
        for fl in flags:
            f.write(f"FLAGGED: {fl}\n")
        f.write("\n".join(parts) + "\n\n" if parts else
                "The publisher lists no licence or use terms on this layer. Ask the county GIS office before you resell or "
                "publish the data. Using it for your own research is usually fine; check their site's disclaimer.\n\n")
    for fl in flags:
        print(f"Licence check: the layer's terms mention {fl}. Read {path} before commercial use.", file=sys.stderr)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer-url", required=True, help=".../MapServer/0 or .../FeatureServer/0")
    ap.add_argument("--bbox", help="south,west,north,east")
    ap.add_argument("--where", default="1=1")
    ap.add_argument("--min-acres", type=float, default=0)
    ap.add_argument("--max-records", type=int, default=20000)
    ap.add_argument("--output", default="parcels.csv")
    ap.add_argument("--list-fields", action="store_true")
    a = ap.parse_args(argv)
    url = a.layer_url.rstrip("/")
    try:
        meta = get(url, {"f": "json"})
    except Exception as e:
        raise SystemExit(f"County parcel layer: source unavailable ({friendly_error(e)}). Check the URL, or use a PropStream / county CSV export instead.")
    fields = [f["name"] for f in meta.get("fields", [])]
    if a.list_fields:
        print(json.dumps({"name": meta.get("name"), "maxRecordCount": meta.get("maxRecordCount"), "fields": fields}, indent=2)); return
    page = min(int(meta.get("maxRecordCount") or 1000), 2000)
    base = {"where": a.where, "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json"}
    if a.bbox:
        s, w, n, e = [float(x) for x in a.bbox.split(",")]
        base.update({"geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": "4326",
                     "spatialRel": "esriSpatialRelIntersects"})
    rows, geoms, offset = [], [], 0
    while len(rows) < a.max_records:
        try:
            d = get(url + "/query", dict(base, resultOffset=offset, resultRecordCount=page))
        except Exception as e:
            if rows:
                print(f"County parcel layer stopped after {len(rows)} parcels: source unavailable ({friendly_error(e)}). Keeping what was fetched.", file=sys.stderr)
                break
            raise SystemExit(f"County parcel layer: source unavailable ({friendly_error(e)}). Try again later or use a CSV export.")
        feats = d.get("features", [])
        if not feats:
            break
        for ft in feats:
            attrs = ft.get("attributes", {})
            acres, lat, lon = geom_stats(ft.get("geometry"))
            if acres is None or acres < a.min_acres:
                continue
            row = {k: ("" if v is None else v) for k, v in attrs.items() if not k.lower().startswith("shape")}
            row.update({"gis_acres": round(acres, 3), "lat": round(lat, 6), "lon": round(lon, 6)})
            rows.append(row)
            geoms.append({"apn": apn_of(attrs), "lat": round(lat, 6), "lon": round(lon, 6),
                          "rings": [simplify(r) for r in (ft.get("geometry") or {}).get("rings") or []]})
        print(f"fetched {offset + len(feats)} features, kept {len(rows)}", file=sys.stderr)
        if not d.get("exceededTransferLimit") and len(feats) < page:
            break
        offset += len(feats)
        time.sleep(0.5)
    if not rows:
        sys.exit("No parcels returned. Check the URL, bbox order (S,W,N,E) and --where clause.")
    cols = list(dict.fromkeys(k for r in rows for k in r))
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    with open(a.output, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols); wr.writeheader(); wr.writerows(rows[: a.max_records])
    gpath = re.sub(r"\.csv$", "", a.output) + ".geometry.json"
    with open(gpath, "w") as f:
        json.dump({"note": "parcel boundaries (lon/lat) for satellite_check.py; from " + url, "parcels": geoms[: a.max_records]}, f)
    lic = write_license(url, meta, os.path.join(os.path.dirname(os.path.abspath(a.output)), "sources"))
    print(json.dumps({"layer": meta.get("name"), "boundaries": gpath, "license_file": lic, "parcels_written": min(len(rows), a.max_records), "output": a.output}, indent=2))


if __name__ == "__main__":
    main()
