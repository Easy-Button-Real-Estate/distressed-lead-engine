"""Source types. Each county YAML lists sources; each source has a `type` below.

Every fetcher returns a list of raw dicts. The `map` block in the YAML says which
raw field becomes which lead field (address, city, zip, parcel_id, owner_name,
event_date, amount, details).
"""
import csv, io, os, re, time
import requests
import xml.etree.ElementTree as ET
from datetime import date, timedelta, datetime, timezone

UA = {"User-Agent": "distressed-lead-engine/0.1 (+public records research)"}


class _Resp:
    def __init__(self, text):
        self.text = text
        self.content = text.encode("utf-8")

    def json(self):
        import json
        return json.loads(self.text)


def _get(url, params=None, provider=None, **kw):
    """Open-data APIs: plain fetch first (free); on block/failure fall back to the keyed provider chain."""
    full = requests.Request("GET", url, params=params).prepare().url
    try:
        r = requests.get(full, headers=UA, timeout=60, **kw)
        r.raise_for_status()
        return r
    except requests.RequestException:
        from ..providers import default_chain, fetch_any
        chain = provider if isinstance(provider, list) else ([provider] if provider else default_chain())
        chain = [p for p in chain if p != "direct"]
        if not chain:
            raise
        return _Resp(fetch_any(full, provider=chain, delay=0))


def _since(src):
    return (date.today() - timedelta(days=int(src.get("lookback_days", 30)))).isoformat()


def socrata(src):
    """Socrata open data (data.seattle.gov, data.cityofchicago.org, data.kingcounty.gov ...)."""
    where = src.get("where", "")
    if src.get("date_field"):
        d = f"{src['date_field']} > '{_since(src)}'"
        where = f"({where}) AND {d}" if where else d
    params = {"$limit": src.get("limit", 5000)}
    if where:
        params["$where"] = where
    if src.get("date_field"):
        params["$order"] = f"{src['date_field']} DESC"
    return _get(src["url"], params).json()


def arcgis(src):
    """ArcGIS REST FeatureServer/MapServer layer query. Optional: date_field + lookback_days,
    out_fields (limit columns, e.g. to skip tenant phone numbers), order_by. Date fields come back as
    epoch milliseconds and are converted to YYYY-MM-DD."""
    where = src.get("where", "1=1")
    if src.get("date_field"):
        d = f"{src['date_field']} >= DATE '{_since(src)}'"
        where = f"({where}) AND {d}" if where and where != "1=1" else d
    params = {"where": where, "outFields": src.get("out_fields", "*"), "returnGeometry": "false", "f": "json",
              "resultRecordCount": src.get("limit", 2000)}
    if src.get("order_by") or src.get("date_field"):
        params["orderByFields"] = src.get("order_by") or f"{src['date_field']} DESC"
    limit, feats, data = int(src.get("limit", 2000)), [], {}
    while len(feats) < limit:          # page past the server's max record count (often 1000)
        params["resultOffset"] = len(feats)
        params["resultRecordCount"] = limit - len(feats)
        data = _get(src["url"].rstrip("/") + "/query", params, src.get("provider")).json()
        if "error" in data:
            raise RuntimeError(f"ArcGIS error: {data['error'].get('message')} {data['error'].get('details', '')}")
        page = data.get("features", [])
        feats += page
        if not page or not data.get("exceededTransferLimit"):
            break
    data["features"] = feats
    dates = {f["name"] for f in data.get("fields", []) if f.get("type") == "esriFieldTypeDate"}
    out = []
    for f in data.get("features", []):
        a = dict(f["attributes"])
        for k in dates:
            if isinstance(a.get(k), (int, float)):
                a[k] = datetime.fromtimestamp(a[k] / 1000, tz=timezone.utc).date().isoformat()
        out.append(a)
    return out


def csv_url(src):
    """Any downloadable CSV (treasurer lists, sheriff sale exports, a published Google Sheet)."""
    text = _get(src["url"]).text
    return list(csv.DictReader(io.StringIO(text)))


def manual_csv(src):
    """A CSV you drop into ./inbox/ (court probate exports, PropStream lists, water shut-off lists
    from a records request). Missing file = skipped, not an error."""
    path = src["path"]
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def rss(src):
    """RSS/Atom feed, e.g. a funeral home or newspaper obituary feed (pre-probate signal)."""
    root = ET.fromstring(_get(src["url"]).content)
    items = []
    for it in root.iter():
        if it.tag.split("}")[-1] in ("item", "entry"):
            g = {c.tag.split("}")[-1]: (c.text or c.get("href") or "") for c in it}
            items.append(g)
    return items


def _search_page(src):
    """Public-records search/results page (court or recorder portal, any county). See dle/sources/search_page.py."""
    from .search_page import run
    return run(src)


FETCHERS = {"search_page": _search_page, "socrata": socrata, "arcgis": arcgis, "csv_url": csv_url, "manual_csv": manual_csv, "rss": rss}


def pick(row, spec):
    """spec is a field name, a list of names joined with spaces, or a literal like '=WA'."""
    if spec is None:
        return ""
    if isinstance(spec, str) and spec.startswith("="):
        return spec[1:]
    names = spec if isinstance(spec, list) else [spec]
    parts = []
    for n in names:
        v = row.get(n, "")
        if isinstance(v, dict):
            v = v.get("url", "")
        if v not in (None, ""):
            parts.append(str(v))
    return " ".join(parts).strip()
