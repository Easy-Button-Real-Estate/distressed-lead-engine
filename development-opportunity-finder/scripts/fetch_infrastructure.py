#!/usr/bin/env python3
"""Pull free OpenStreetMap infrastructure for a bounding box (no API key).

Layers: power substations, transmission lines, highway interchanges / on-ramps,
major highways, rail lines, water/wastewater plants, and industrial land-use areas.

Output: one CSV of points (lines are densified into vertices) with columns
layer, name, voltage, ref, lat, lon. score_parcels.py reads it with --infra.

Usage:
  python fetch_infrastructure.py --bbox "S,W,N,E" --output infra.csv
  python fetch_infrastructure.py --from-parcels parcels.csv --pad-miles 5 --output infra.csv

Network note: Claude.ai's code sandbox usually blocks outside hosts. If this
fails there, run it on your own computer (or Claude Code / Desktop) and upload
the CSV.
"""
import argparse, csv, json, math, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import SOURCE_UNAVAILABLE, friendly_error, urlopen  # noqa: E402

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

LAYERS = {
    "substation": 'nwr["power"="substation"]',
    "transmission_line": 'way["power"="line"]',
    "highway_interchange": 'node["highway"="motorway_junction"]',
    "major_highway": 'way["highway"~"^(motorway|trunk|primary)$"]',
    "rail": 'way["railway"="rail"]["service"!~"yard|siding|spur"]',
    "water_plant": 'nwr["man_made"~"^(water_works|wastewater_plant)$"]',
    "industrial_area": 'nwr["landuse"="industrial"]',
}


def query(ql, timeout, mirrors=None):
    """Try each Overpass server in turn (at least two), once each plus one retry on a non-timeout error."""
    data = urllib.parse.urlencode({"data": ql}).encode()
    last = None
    for url in list(mirrors or MIRRORS):
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, data=data, headers={"User-Agent": "development-opportunity-finder-skill/2.2"})
                with urlopen(req, timeout=timeout) as r:
                    out = json.loads(r.read().decode())
                if url in MIRRORS:
                    MIRRORS.remove(url); MIRRORS.insert(0, url)  # stick with the server that worked
                return out
            except Exception as e:  # try the next server
                last = e
                if "timed out" in str(e) or "502" in str(e) or "504" in str(e) or "429" in str(e):
                    break  # busy server: move on to the next one right away
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(friendly_error(last) if last else "no server answered")


# Fallbacks when every Overpass server fails (or --no-overpass). Public ArcGIS services, no key.
# HIFLD Open (hifld-geoplatform) was retired in Aug/Sep 2025. The power layers below are copies of the last
# public HIFLD releases re-hosted by other ArcGIS Online organisations (checked live 2026-11-19). They are
# snapshots, not maintained: transmission lines ~2024 release (re-hosted by HARC), substations last edited
# Feb 2021 (re-hosted by the 543rd Engineer Detachment). If one goes dark the next URL is tried, then "unknown".
#   US Census TIGERweb (public domain): primary / secondary roads, railroads, ramps (MTFCC S1630) for interchanges
# Water plants and industrial areas have no fallback: they stay unknown.
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer"
FALLBACK = {
    "major_highway": [(TIGER + "/2", "US Census TIGER primary roads", None), (TIGER + "/3", "US Census TIGER secondary roads", None)],
    "rail": [(TIGER + "/9", "US Census TIGER railroads", None)],
    "highway_interchange": [(TIGER + "/8", "US Census TIGER ramps (MTFCC S1630)", "MTFCC='S1630'")],
    "transmission_line": [
        ("https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/HIFLD_US_Electric_Power_Transmission_Lines/FeatureServer/0",
         "HIFLD transmission lines (last public release, re-hosted copy; snapshot)", None),
        ("https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0",
         "HIFLD transmission lines (legacy HIFLD service, may go offline; snapshot)", None)],
    "substation": [
        ("https://services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services/Electric_Substations/FeatureServer/0",
         "HIFLD substations (2021 snapshot, re-hosted copy; not maintained)", None)],
}
POINT_LAYERS = {"substation", "highway_interchange"}


def arcgis_features(url, bbox, timeout, where=None):
    """(name, voltage, [(lat, lon), ...]) per feature; points come back as one-element lists."""
    s, w, n, e = bbox
    q = urllib.parse.urlencode({"where": where or "1=1", "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
                                "inSR": "4326", "outSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                                "outFields": "*", "returnGeometry": "true", "f": "json", "resultRecordCount": "2000"})
    req = urllib.request.Request(url + "/query", data=q.encode(), headers={"User-Agent": "development-opportunity-finder-skill/2.3"})
    with urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    if "error" in d:
        raise RuntimeError(str(d["error"])[:100])
    out = []
    for ft in d.get("features", []):
        at = ft.get("attributes") or {}
        name = str(at.get("FULLNAME") or at.get("NAME") or at.get("BASENAME") or "")
        volt = str(at.get("VOLTAGE") or at.get("MAX_VOLT") or "")
        g = ft.get("geometry") or {}
        if "x" in g and "y" in g:
            out.append((name, volt, [(g["y"], g["x"])]))
        for path in g.get("paths") or []:
            out.append((name, volt, [(p[1], p[0]) for p in path]))
    return out


arcgis_lines = arcgis_features  # old name


ZERO_FEATURES = "unknown: the source returned 0 features for this area (treated as unknown, not as 'far away')"


def fallback(layer, bbox, timeout):
    """Return (rows, source) from the first public fallback that answers WITH features, or (None, None).
    A national layer that returns 0 features for a whole county is treated as unknown, not as 'nothing nearby'."""
    rows, used = [], []
    for url, label, where in FALLBACK.get(layer, []):
        if used and layer in ("transmission_line", "substation"):
            break  # one power source is enough; later entries are backups
        try:
            feats = arcgis_features(url, bbox, timeout, where)
        except Exception:
            continue
        if not feats:
            continue  # 0 features: try the next copy; if none has any, the layer stays unknown
        for name, volt, coords in feats:
            if layer in POINT_LAYERS:
                pts = [coords[len(coords) // 2]] if coords else []  # ramp: its midpoint marks the interchange
            else:
                pts = densify(coords)
            for la, lo in pts:
                rows.append({"layer": layer, "name": name, "voltage": volt, "ref": label, "lat": round(la, 6), "lon": round(lo, 6)})
        used.append(label)
    return (rows, ", ".join(used)) if used else (None, None)


def densify(coords, step_mi=0.25):
    out = []
    for (a, b) in zip(coords, coords[1:]):
        out.append(a)
        d = hav(a[0], a[1], b[0], b[1])
        n = int(d // step_mi)
        for i in range(1, n + 1):
            t = i / (n + 1)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    if coords:
        out.append(coords[-1])
    return out


def hav(lat1, lon1, lat2, lon2):
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bbox_from_parcels(path, pad):
    lats, lons = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            low = {k.strip().lower(): v for k, v in row.items() if k}
            la = low.get("lat") or low.get("latitude") or low.get("centroid_lat")
            lo = low.get("lon") or low.get("lng") or low.get("longitude") or low.get("centroid_lon")
            try:
                lats.append(float(la)); lons.append(float(lo))
            except (TypeError, ValueError):
                pass
    if not lats:
        sys.exit("No lat/lon columns found in the parcel file; pass --bbox instead.")
    dlat = pad / 69.0
    dlon = pad / (69.0 * math.cos(math.radians(sum(lats) / len(lats))))
    return (min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", help="south,west,north,east in decimal degrees")
    ap.add_argument("--from-parcels", help="parcel CSV with lat/lon; bbox is computed from it")
    ap.add_argument("--pad-miles", type=float, default=5.0)
    ap.add_argument("--layers", default=",".join(LAYERS), help="comma list of layers")
    ap.add_argument("--output", default="infrastructure.csv")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--no-fallback", action="store_true", help="do not use TIGER / HIFLD copies when Overpass fails")
    ap.add_argument("--no-overpass", action="store_true", help="skip OpenStreetMap and use only the public fallbacks (testing, or when Overpass is down)")
    a = ap.parse_args(argv)
    if a.bbox:
        s, w, n, e = [float(x) for x in a.bbox.split(",")]
    elif a.from_parcels:
        s, w, n, e = bbox_from_parcels(a.from_parcels, a.pad_miles)
    else:
        sys.exit("Pass --bbox or --from-parcels")
    area = hav(s, w, n, w) * hav(s, w, s, e)
    if area > 5000:
        print(f"Warning: bbox is ~{area:,.0f} sq mi; Overpass may time out. Split it up if it fails.", file=sys.stderr)
    bb = f"({s},{w},{n},{e})"
    rows, counts, sources = [], {}, {}
    overpass_down = "Overpass skipped (--no-overpass)" if a.no_overpass else None  # after every server fails once, skip it
    for layer in a.layers.split(","):
        layer = layer.strip()
        if layer not in LAYERS:
            print(f"skip unknown layer {layer}", file=sys.stderr); continue
        ql = f"[out:json][timeout:{a.timeout}];{LAYERS[layer]}{bb};out tags geom;"
        try:
            if overpass_down:
                raise RuntimeError(overpass_down)
            data = query(ql, a.timeout + 30)
        except RuntimeError as ex:
            overpass_down = overpass_down or ("all Overpass servers failed: " + str(ex))
            ex = ex if not a.no_overpass else "skipped with --no-overpass"
            fb, src = (None, None) if a.no_fallback else fallback(layer, (s, w, n, e), 60)
            if fb is not None and len(fb) == 0:
                fb = None
            if fb is not None:
                rows += fb
                counts[layer], sources[layer] = f"{len(fb)} points (fallback)", src + " (OpenStreetMap unavailable: " + str(ex) + ")"
                print(f"{layer}: OpenStreetMap unavailable, used {src} instead ({len(fb)} points)", file=sys.stderr)
            else:
                counts[layer], sources[layer] = "unavailable", SOURCE_UNAVAILABLE
                print(f"{layer}: {SOURCE_UNAVAILABLE} ({ex})", file=sys.stderr)
            continue
        if not data.get("elements"):
            # 0 features from OpenStreetMap for the whole area: unknown, not "far away". Try the public fallback.
            fb, src = (None, None) if a.no_fallback else fallback(layer, (s, w, n, e), 60)
            if fb:
                rows += fb
                counts[layer], sources[layer] = f"{len(fb)} points (fallback)", src + " (OpenStreetMap returned 0 features here)"
            else:
                counts[layer], sources[layer] = 0, ZERO_FEATURES
                print(f"{layer}: {ZERO_FEATURES}", file=sys.stderr)
            continue
        n_el = 0
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name, volt, ref = tags.get("name", ""), tags.get("voltage", ""), tags.get("ref", "")
            if el["type"] == "node":
                pts = [(el["lat"], el["lon"])]
            elif "geometry" in el:
                coords = [(g["lat"], g["lon"]) for g in el["geometry"] if g]
                if layer in ("transmission_line", "major_highway", "rail"):
                    pts = densify(coords)
                else:  # polygon: use centroid of vertices
                    pts = [(sum(c[0] for c in coords) / len(coords), sum(c[1] for c in coords) / len(coords))] if coords else []
            elif el["type"] == "relation" and "bounds" in el:
                b = el["bounds"]; pts = [((b["minlat"] + b["maxlat"]) / 2, (b["minlon"] + b["maxlon"]) / 2)]
            else:
                pts = []
            for la, lo in pts:
                rows.append({"layer": layer, "name": name, "voltage": volt, "ref": ref, "lat": round(la, 6), "lon": round(lo, 6)})
            n_el += 1
        counts[layer], sources[layer] = n_el, "OpenStreetMap contributors (ODbL) via Overpass"
        print(f"{layer}: {n_el} features", file=sys.stderr)
        time.sleep(1)
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    with open(a.output, "w", newline="") as f:
        w_ = csv.DictWriter(f, fieldnames=["layer", "name", "voltage", "ref", "lat", "lon"])
        w_.writeheader(); w_.writerows(rows)
    with open(re.sub(r"\.csv$", "", a.output) + ".sources.json", "w") as f:
        json.dump({"bbox": [s, w, n, e], "layers": sources}, f, indent=1)
    res = {"bbox": [s, w, n, e], "features": counts, "points_written": len(rows), "output": a.output, "sources": sources}
    print(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    main()
