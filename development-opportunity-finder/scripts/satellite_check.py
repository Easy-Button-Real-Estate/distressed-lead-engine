#!/usr/bin/env python3
"""Step 3: aerial images of the top parcels, with the parcel boundary drawn on.

For the top N ranked parcels it saves one image per parcel and writes
satellite_review.csv, where Claude (or you) records what the image shows.

Imagery (default first)
  naip    USDA NAIP aerial imagery through the USGS National Map image service.
          Public domain (US government work), free, no key. 0.6-1 m resolution,
          flown every 2-3 years per state. This is what gets saved to disk.
  county  your county's own orthoimagery: pass --imagery-url with its public
          ArcGIS ImageServer or MapServer URL. Check the county's terms.
  Esri World Imagery and Google Maps are given as VIEW LINKS only. Their terms
  do not allow saving their imagery to disk without an account or license, so
  this kit never downloads them.

Boundaries: if parcels came from fetch_arcgis_parcels.py there is a
<parcels>.geometry.json file next to them; pass it with --geometry (run_pipeline
does this) and the real parcel outline is drawn in yellow. Without it, a dashed
square sized to the acreage is drawn and labeled "approximate".

What an image can and cannot tell you. Every finding in the sheet starts with
one of: "clearly visible:", "likely:", or "can't determine". Aerial images
cannot show legal access, easements, utility capacity, or whether a line is a
power line; do not claim them. A road touching the parcel is not legal access.

Usage:
  python scripts/satellite_check.py --ranked out/parcels_ranked.csv --top 10 --geometry parcels.geometry.json
  python scripts/satellite_check.py --ranked out/parcels_ranked.csv --offline   # links + sheet only
"""
import argparse, io, json, math, os, re, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import friendly_error, norm, num, read_rows, urlopen, write_rows  # noqa: E402

UA = {"User-Agent": "development-opportunity-finder-skill/2.1"}
NAIP_URL = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer"
R_MERC = 6378137.0
LABELS = ("clearly visible:", "likely:", "can't determine")
# One review sheet: parcel, image, capture year, status, verdict and next action come first.
REVIEW_FIELDS = ["rank", "apn", "address", "image_file", "capture_year", "imagery_age", "imagery_flag", "status", "verdict", "next_action",
                 "tier", "acres", "lat", "lon", "image_source", "boundary", "esri_view_link", "google_maps_link", "vacant", "structures", "tree_cover", "road_or_driveway_touching",
                 "water_or_wet_areas", "neighbors", "notes", "reviewed_by", "image_error"]
FINDINGS = ["vacant", "structures", "tree_cover", "road_or_driveway_touching", "water_or_wet_areas", "neighbors"]


def age_sentence(year, today=None):
    """'Imagery is from 2022, about 4 years old. Check current imagery before an offer.'"""
    import datetime as _dt
    y = int(year)
    age = max(0, (today or _dt.date.today()).year - y)
    return f"Imagery is from {y}, about {age} year{'s' if age != 1 else ''} old. Check current imagery before an offer."


def blank_image(data):
    """True when the downloaded picture is one flat colour (no imagery at this spot)."""
    try:
        from PIL import Image, ImageStat
        im = Image.open(io.BytesIO(data)).convert("L")
        return max(ImageStat.Stat(im).stddev) < 2.0
    except Exception:
        return False


def merc(lat, lon):
    lat = max(min(lat, 85.0), -85.0)
    return R_MERC * math.radians(lon), R_MERC * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def extent_for(lat, lon, acres, rings=None, pad=0.35):
    """Square extent in Web Mercator metres (only used to place pixels, never for area)."""
    if rings:
        xs, ys = zip(*[merc(p[1], p[0]) for r in rings for p in r])
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 * (1 + pad)
    else:
        cx, cy = merc(lat, lon)
        side_m = math.sqrt((acres or 5) * 4046.86) / math.cos(math.radians(lat))  # metres on the Mercator plane
        half = side_m / 2 * (1 + 2 * pad)
    half = max(half, 120.0)
    return (cx - half, cy - half, cx + half, cy + half)


def export_url(base, ext, px=800):
    base = base.rstrip("/")
    op = "exportImage" if base.lower().endswith("imageserver") else "export"
    q = {"bbox": ",".join(f"{v:.2f}" for v in ext), "bboxSR": 3857, "imageSR": 3857, "size": f"{px},{px}", "format": "jpg", "f": "image"}
    return base + "/" + op + "?" + urllib.parse.urlencode(q)


def esri_view_link(lat, lon):
    return f"https://www.arcgis.com/apps/mapviewer/index.html?center={lon:.6f},{lat:.6f}&level=17&basemapUrl=https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"


def to_px(lat, lon, ext, size):
    x, y = merc(lat, lon)
    return ((x - ext[0]) / (ext[2] - ext[0]) * size[0], (ext[3] - y) / (ext[3] - ext[1]) * size[1])


def draw_overlay(img_bytes, ext, rings=None, approx_center=None, label=""):
    """Draw the boundary (or a dashed approximate square) on the image. Returns JPEG bytes."""
    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    d = ImageDraw.Draw(im)
    if rings:
        for r in rings:
            pts = [to_px(p[1], p[0], ext, im.size) for p in r]
            if len(pts) >= 2:
                d.line(pts + [pts[0]], fill=(255, 230, 0), width=4)
    elif approx_center:
        lat, lon, acres = approx_center
        cx, cy = merc(lat, lon)
        h = math.sqrt((acres or 5) * 4046.86) / math.cos(math.radians(lat)) / 2
        x0, y0 = to_px(*_inv_merc(cx - h, cy + h), ext, im.size)
        x1, y1 = to_px(*_inv_merc(cx + h, cy - h), ext, im.size)
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            steps = 16
            for k in range(0, steps, 2):
                p0 = (a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps)
                p1 = (a[0] + (b[0] - a[0]) * (k + 1) / steps, a[1] + (b[1] - a[1]) * (k + 1) / steps)
                d.line([p0, p1], fill=(255, 230, 0), width=3)
    if label:
        d.rectangle([0, 0, im.size[0], 22], fill=(0, 0, 0))
        d.text((6, 5), label[:110], fill=(255, 255, 255))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()


def _inv_merc(x, y):
    return math.degrees(2 * math.atan(math.exp(y / R_MERC)) - math.pi / 2), math.degrees(x / R_MERC)


def naip_year(lat, lon, fetcher, base=NAIP_URL):
    """Newest NAIP capture year (and date) under this point, from the image service catalog. '' if unknown."""
    q = urllib.parse.urlencode({"geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
                                "geometryType": "esriGeometryPoint", "returnGeometry": "false", "returnCatalogItems": "true", "f": "json"})
    try:
        d = json.loads(fetcher(base + "/identify?" + q).decode())
        items = [f.get("attributes") or {} for f in (d.get("catalogItems") or {}).get("features", [])]
        items = [i for i in items if i.get("acquisition_date") or i.get("Year")]
        if not items:
            return ""
        best = max(items, key=lambda i: (i.get("acquisition_date") or 0, i.get("Year") or 0))
        if best.get("acquisition_date"):
            import datetime as _dt
            return _dt.datetime.fromtimestamp(best["acquisition_date"] / 1000, _dt.timezone.utc).strftime("%Y (%b %d)")
        return str(best.get("Year"))
    except Exception:
        return ""


def fetch(url, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urlopen(req, timeout=timeout) as r:
        data, ctype = r.read(), r.headers.get("Content-Type", "")
    if not data or ("image" not in ctype and data[:3] != b"\xff\xd8\xff" and data[:4] != b"\x89PNG"):
        raise RuntimeError("not an image (" + ctype + ")")
    return data


def fetch_json(url, timeout=60):
    with urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def load_geometry(path):
    by_apn, pts = {}, []
    if not path or not os.path.exists(path):
        return by_apn, pts
    for g in json.load(open(path)).get("parcels", []):
        if g.get("apn"):
            by_apn[norm(g["apn"])] = g["rings"]
        pts.append((g.get("lat"), g.get("lon"), g["rings"]))
    return by_apn, pts


def find_rings(row, by_apn, pts):
    r = by_apn.get(norm(row.get("apn")))
    if r:
        return r
    lat, lon = num(row.get("lat")), num(row.get("lon"))
    if lat is None or lon is None:
        return None
    for la, lo, rings in pts:
        if la is not None and abs(la - lat) < 0.0003 and abs(lo - lon) < 0.0003:
            return rings
    return None


def main(argv=None, fetcher=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ranked", required=True)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--all-tiers", default="A", help="also cover every parcel in these tiers even beyond --top (default A)")
    ap.add_argument("--geometry", help="<parcels>.geometry.json from fetch_arcgis_parcels.py (draws the real boundary)")
    ap.add_argument("--imagery-url", help="county orthoimagery ArcGIS ImageServer / MapServer URL (default: USDA NAIP via USGS)")
    ap.add_argument("--output-dir", help="default: <ranked folder>/satellite")
    ap.add_argument("--offline", action="store_true", help="do not download; write the review sheet with view links only")
    a = ap.parse_args(argv)
    fetcher = fetcher or fetch
    out = a.output_dir or os.path.join(os.path.dirname(a.ranked) or ".", "satellite")
    os.makedirs(out, exist_ok=True)
    base = a.imagery_url or NAIP_URL
    source = "county orthoimagery (" + base + ")" if a.imagery_url else "USDA NAIP (USGS National Map, public domain)"
    by_apn, pts = load_geometry(a.geometry)
    rows = [r for r in read_rows(a.ranked) if str(r.get("rank") or "").strip()]
    rows.sort(key=lambda r: num(r["rank"]) or 1e9)
    review, ok, failed, no_xy, outlines, errors = [], 0, 0, 0, 0, []
    want = {t.strip().upper() for t in (a.all_tiers or "").split(",") if t.strip()}
    cover = [r for i, r in enumerate(rows) if i < a.top or str(r.get("tier") or "")[:1].upper() in want]
    for r in cover:
        lat, lon, acres = num(r.get("lat")), num(r.get("lon")), num(r.get("acres"))
        rec = {k: r.get(k, "") for k in ("rank", "tier", "apn", "address", "acres", "lat", "lon")}
        rec["rank"] = int(num(r["rank"]))
        for k in FINDINGS + ["verdict", "notes", "reviewed_by", "image_error", "capture_year", "imagery_age"]:
            rec[k] = ""
        rec["imagery_flag"] = "NO IMAGERY: look at current imagery before an offer"
        rec["status"] = "to review"
        rec["next_action"] = "open image_file, fill the findings, then set verdict keep / downgrade / drop"
        if lat is None or lon is None:
            no_xy += 1
            rec.update(image_file="", image_source="", boundary="", esri_view_link="", google_maps_link="",
                       notes="no lat/lon in the file - look it up on the county map by APN")
            review.append(rec)
            continue
        rings = find_rings(r, by_apn, pts)
        outlines += bool(rings)
        rec["boundary"] = "parcel boundary drawn" if rings else "approximate square (no boundary in file)"
        rec["esri_view_link"] = esri_view_link(lat, lon)
        rec["google_maps_link"] = f"https://www.google.com/maps/@?api=1&map_action=map&center={lat:.6f},{lon:.6f}&zoom=17&basemap=satellite"
        rec["image_source"] = source
        rec["image_file"] = ""
        if a.offline:
            rec["imagery_flag"] = "no image saved (links-only mode): open the view links and check current imagery before an offer"
        if not a.offline:
            ext = extent_for(lat, lon, acres, rings)
            slug = re.sub(r"[^A-Za-z0-9]+", "-", str(r.get("apn") or r.get("address") or rec["rank"]))[:40].strip("-")
            path = os.path.join(out, f"{rec['rank']:02d}_{slug}.jpg")
            try:
                raw = fetcher(export_url(base, ext))
                label = f"#{rec['rank']} {r.get('apn', '')} {acres or ''} ac - " + ("parcel boundary" if rings else "APPROXIMATE area, no boundary") + " - " + ("NAIP/USGS" if not a.imagery_url else "county imagery")
                try:
                    data = draw_overlay(raw, ext, rings, None if rings else (lat, lon, acres), label)
                except ImportError:
                    data = raw
                    rec["boundary"] = "not drawn (install Pillow: pip install pillow)"
                with open(path, "wb") as f:
                    f.write(data)
                rec["image_file"] = path
                rec["capture_year"] = (naip_year(lat, lon, fetch_json if fetcher is fetch else fetcher) or "unknown (check the image service)") if not a.imagery_url else "see your county imagery metadata"
                ym = re.match(r"(\d{4})", str(rec["capture_year"]))
                if blank_image(raw):
                    rec["imagery_flag"] = "NO IMAGERY at this spot (blank picture): look at current imagery before an offer"
                elif ym:
                    rec["imagery_age"] = age_sentence(ym.group(1))
                    rec["imagery_flag"] = ""
                else:
                    rec["imagery_flag"] = "capture date unknown: treat as no dated imagery and look at current imagery before an offer"
                ok += 1
            except Exception as e:  # network blocked, service down, outside coverage, disk full
                failed += 1
                why = friendly_error(e)
                rec["image_error"] = why
                rec["notes"] = "image not saved (" + why + "). Open esri_view_link or google_maps_link to look."
                rec["next_action"] = "image failed: look with esri_view_link / google_maps_link, then set verdict"
                errors.append(f"{rec['rank']}\t{r.get('apn', '')}\t{why}\t{path}")
        review.append(rec)
    sheet = os.path.join(out, "satellite_review.csv")
    write_rows(sheet, review, REVIEW_FIELDS)
    years = sorted({re.match(r"(\d{4})", str(x["capture_year"])).group(1) for x in review if re.match(r"(\d{4})", str(x.get("capture_year") or ""))})
    flagged = [x for x in review if x.get("imagery_flag")]
    summ = ([age_sentence(y) for y in years] or ["No dated imagery was saved this run. Check current imagery before an offer."]) + [
        f"Covered {len(review)} top-ranked parcels (top {a.top}" + (f" plus every tier {', '.join(sorted(want))} parcel" if want else "") + ")."]
    if flagged:
        summ.append(f"No usable imagery for {len(flagged)}: " + "; ".join(f"#{x['rank']} {x.get('apn') or x.get('address')} ({x['imagery_flag'].split(':')[0]})" for x in flagged))
    with open(os.path.join(out, "imagery_summary.txt"), "w") as f:
        f.write("\n".join(summ) + "\n")
    log = os.path.join(out, "satellite_errors.log")
    if errors:
        import datetime as _dt
        with open(log, "a") as f:
            f.write(f"# {_dt.datetime.now().isoformat(timespec='seconds')}  source: {source}\n# rank\tapn\terror\tfile\n")
            f.write("\n".join(errors) + "\n")
    with open(os.path.join(out, "HOW_TO_REVIEW.md"), "w") as f:
        f.write(HOW)
    print(f"Aerial check: {len(review)} parcels, {ok} images saved ({outlines} with the real boundary), {failed} downloads failed, "
          f"{no_xy} without lat/lon" + (" (offline: view links only)" if a.offline else "") + f". Review sheet: {sheet}"
          + (f". Failures logged in {log}" if errors else ""))
    return review


HOW = """# Aerial review

Open each image (yellow line = parcel boundary; dashed square = approximate area only) and fill
satellite_review.csv. Start EVERY finding with one of:

- "clearly visible: ..."  you can plainly see it
- "likely: ..."           probably, but the image is not sharp or recent enough to be sure
- "can't determine"       not visible, or the image can't show it

Columns: vacant, structures, tree_cover, road_or_driveway_touching, water_or_wet_areas, neighbors.
Then verdict (keep / downgrade / drop) and a short note. "drop" removes the owner from the
marketing lists; "downgrade" stays but is noted.

What an aerial image can't tell you: legal access or easements (a road touching the parcel is not
legal access), whether a line is a power line or its capacity, utilities, zoning, wetlands
boundaries, or ownership. NAIP is flown every 2-3 years, so imagery is often several years old:
capture_year says when the newest NAIP photo under the parcel was taken (the image can mix years
at edges) and imagery_age says, for example, "Imagery is from 2022, about 4 years old. Check
current imagery before an offer." imagery_flag marks parcels with no usable imagery (no
lat/lon, download failed, blank picture or no capture date): look at current imagery for those.
satellite_review.csv is the one place for this step: parcel, image, capture year, status
("to review" until you fill it; set it to "reviewed"), verdict and next action.

Imagery: USDA NAIP via the USGS National Map (public domain), or your county's orthoimagery.
Esri and Google links are for viewing only; their imagery is not saved by this kit.
"""


def check_review(path):
    """Return rows whose findings don't start with an allowed label (used by tests and Claude)."""
    bad = []
    for r in read_rows(path):
        for k in FINDINGS:
            v = str(r.get(k) or "").strip().lower()
            if v and not v.startswith(LABELS):
                bad.append((r.get("apn"), k, v[:40]))
    return bad


if __name__ == "__main__":
    main()
