#!/usr/bin/env python3
"""Add free federal constraint data to a parcel CSV (no API keys).

For each parcel it lays a 3x3 grid of sample points over a square the size of
the parcel, centred on its centroid, and checks:
  * FEMA flood hazard (NFHL)       -> fema_flood_pct, fema_zones
  * USFWS National Wetlands Inv.   -> wetlands_pct
  * USGS 3DEP elevation (EPQS)     -> slope_pct_est, buildable_pct_est (share of grid under --max-slope)

This is a screening estimate, not a survey. Irregular parcels can put sample
points outside the true boundary. Columns you already have (flood_pct,
wetlands_pct, buildable_pct) are never overwritten.

Usage:
  python enrich_constraints.py --input parcels.csv --output parcels_enriched.csv --limit 150
"""
import argparse, csv, json, math, os, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import SOURCE_UNAVAILABLE, urlopen  # noqa: E402
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "development-opportunity-finder-skill/2.0"}
FEMA = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
NWI = "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0/query"
EPQS = "https://epqs.nationalmap.gov/v1/json"


def fetch(url, params, timeout=45):
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urlopen(urllib.request.Request(full, headers=UA), timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception:
            if attempt == 2:
                return None
            time.sleep(2 * (attempt + 1))


def pip(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]; xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def in_any(pt, features):
    lon, lat = pt
    hits = []
    for f in features:
        rings = (f.get("geometry") or {}).get("rings") or []
        n = sum(1 for r in rings if pip(lon, lat, r))
        if n % 2 == 1:
            hits.append(f.get("attributes", {}))
    return hits


def grid(lat, lon, acres):
    side_ft = math.sqrt(max(acres, 0.1) * 43560) * 0.8  # stay inside the parcel edge
    dlat = side_ft / 364000.0 / 2
    dlon = side_ft / (364000.0 * math.cos(math.radians(lat))) / 2
    pts = [(lon + dx * dlon, lat + dy * dlat) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    return pts, side_ft / 2  # spacing between neighbours (ft)


def polys(url, pts, fields):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    d = fetch(url, {"geometry": f"{min(xs)},{min(ys)},{max(xs)},{max(ys)}", "geometryType": "esriGeometryEnvelope",
                    "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": fields,
                    "returnGeometry": "true", "f": "json"})
    return None if d is None or "error" in d else d.get("features", [])


def elev(pt):
    d = fetch(EPQS, {"x": pt[0], "y": pt[1], "units": "Feet", "wkid": 4326})
    try:
        v = float(d["value"]); return None if v < -1000 else v
    except Exception:
        return None


def enrich(row, max_slope):
    out = {}
    try:
        lat, lon = float(row["_lat"]), float(row["_lon"]); acres = float(row["_acres"])
    except (TypeError, ValueError, KeyError):
        return {"constraint_check": "skipped: missing lat/lon/acres"}
    pts, spacing = grid(lat, lon, acres)
    gaps = []
    fema = polys(FEMA, pts, "FLD_ZONE,SFHA_TF")
    if fema is None:
        gaps.append("FEMA flood: " + SOURCE_UNAVAILABLE)
    else:
        zones, sfha = set(), 0
        for p in pts:
            hits = in_any(p, fema)
            for h in hits:
                zones.add(str(h.get("FLD_ZONE")))
            if any(str(h.get("SFHA_TF")).upper() == "T" for h in hits):
                sfha += 1
        if not zones:
            # no FEMA polygon at any sample point: the area is not on the digital flood map.
            # That is UNKNOWN, not "safe" - leave the percent blank so scoring treats it as missing.
            out["fema_flood_pct"] = ""
            out["fema_zones"] = "UNMAPPED"
        else:
            out["fema_flood_pct"] = round(100 * sfha / len(pts), 1)
            out["fema_zones"] = "|".join(sorted(zones))
    nwi = polys(NWI, pts, "WETLAND_TYPE")
    if nwi is None:
        gaps.append("NWI wetlands: " + SOURCE_UNAVAILABLE)
    else:
        out["wetlands_pct_est"] = round(100 * sum(1 for p in pts if in_any(p, nwi)) / len(pts), 1)
        out["_nwi_features"] = len(nwi)
        types = sorted({str(h.get("WETLAND_TYPE")) for p in pts for h in in_any(p, nwi)})
        if types:
            out["wetland_types"] = "|".join(types)
    with ThreadPoolExecutor(max_workers=9) as ex:
        z = list(ex.map(elev, pts))
    if sum(v is not None for v in z) >= 6:
        grads, flat_cells = [], 0
        for i in range(9):
            r, c = divmod(i, 3); local = []
            for (dr, dc, dist) in ((0, 1, spacing), (1, 0, spacing), (0, -1, spacing), (-1, 0, spacing)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < 3 and 0 <= cc < 3 and z[i] is not None and z[rr * 3 + cc] is not None:
                    local.append(abs(z[i] - z[rr * 3 + cc]) / dist * 100)
            if local:
                m = max(local); grads.append(m)
                if m <= max_slope:
                    flat_cells += 1
        if grads:
            out["slope_pct_est"] = round(sum(grads) / len(grads), 1)
            out["buildable_pct_est"] = round(100 * flat_cells / len(grads), 1)
            vals = [v for v in z if v is not None]
            out["elev_range_ft"] = round(max(vals) - min(vals), 1)
    if "slope_pct_est" not in out:
        gaps.append("USGS slope: " + SOURCE_UNAVAILABLE)
    out["constraint_check"] = "ok" if not gaps else "partial"
    out["constraint_notes"] = "; ".join(gaps)
    return out


ZERO_LAYER = "unknown: NWI returned 0 wetland features for every checked parcel (treated as unknown, not as 0%)"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--limit", type=int, default=150, help="only check the first N rows (sort first!)")
    ap.add_argument("--max-slope", type=float, default=10.0, help="slope %% counted as buildable")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from score_parcels import load_table, pick
    df = load_table(a.input)
    lat_c, lon_c = pick(df, "lat"), pick(df, "lon")
    ac_c = pick(df, "acres")
    if not (lat_c and lon_c and ac_c):
        sys.exit("Need lat, lon and acres columns.")
    rows = df.to_dict("records")
    for r in rows:
        r["_lat"], r["_lon"], r["_acres"] = r.get(lat_c), r.get(lon_c), r.get(ac_c)
    todo = rows[: a.limit]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(lambda r: enrich(r, a.max_slope), todo))
    # A national layer that returns nothing for a whole county is unknown, not "none here".
    nwi_checked = [res for res in results if "wetlands_pct_est" in res]
    nwi_zero = len(nwi_checked) >= 5 and all(res.get("_nwi_features", 0) == 0 for res in nwi_checked)
    for res in results:
        n_feat = res.pop("_nwi_features", None)
        if nwi_zero and n_feat is not None:
            res["wetlands_pct_est"] = ""
            res["constraint_notes"] = "; ".join(x for x in (res.get("constraint_notes"), "NWI wetlands: " + ZERO_LAYER) if x)
            res["constraint_check"] = "partial"
    if nwi_zero:
        print("NWI wetlands: " + ZERO_LAYER, file=sys.stderr)
    for r, res in zip(todo, results):
        r.update(res)
    for r in rows:
        for k in ("_lat", "_lon", "_acres"):
            r.pop(k, None)
    cols = list(dict.fromkeys(k for r in rows for k in r))
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    with open(a.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    ok = sum(1 for r in todo if r.get("constraint_check") == "ok")
    for name in ("FEMA flood", "NWI wetlands", "USGS slope"):
        n = sum(1 for r in todo if f"{name}: {SOURCE_UNAVAILABLE}" in str(r.get("constraint_notes") or ""))
        if n:
            print(f"{name}: {SOURCE_UNAVAILABLE} ({n} of {len(todo)} parcels)", file=sys.stderr)
    res = {"checked": len(todo), "ok": ok, "output": a.output, "nwi_zero_everywhere": nwi_zero,
           "sources": ["FEMA NFHL", "USFWS NWI", "USGS 3DEP EPQS"]}
    print(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    main()
