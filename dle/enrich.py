"""Optional per-county parcel enrichment (parcel id -> address, etc.) via ArcGIS."""
from .sources import _get


def arcgis_parcels(leads, cfg):
    url, pin_field = cfg["url"].rstrip("/") + "/query", cfg.get("pin_field", "PIN")
    todo = [l for l in leads if l["parcel_id"] and not l["property_address"]]
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        pins = ",".join(f"'{l['parcel_id']}'" for l in chunk)
        data = _get(url, {"where": f"{pin_field} IN ({pins})", "outFields": "*",
                          "returnGeometry": "false", "f": "json"}).json()
        by = {f["attributes"][pin_field]: f["attributes"] for f in data.get("features", [])}
        for l in chunk:
            a = by.get(l["parcel_id"])
            if not a:
                continue
            m = cfg.get("map", {})
            l["property_address"] = (a.get(m.get("address", "ADDR_FULL")) or "").upper()
            l["city"] = (a.get(m.get("city", "POSTALCTYNAME")) or "").upper()
            l["zip"] = a.get(m.get("zip", "ZIP5")) or ""
            extra = [f"{k}: {str(a.get(v)).strip()}" for k, v in (cfg.get("extra") or {}).items() if a.get(v) not in (None, "")]
            if extra:
                l["details"] = (l["details"] + " " + ", ".join(extra)).strip()
    return leads
