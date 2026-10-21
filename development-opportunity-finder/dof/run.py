"""Screen a property CSV and write a ranked list plus a short summary.

    python -m dof.run --csv samples/sample_properties.csv --config config/examples/seattle-wa.yaml
"""

import argparse, csv, os, sys

from dof.columns import load_csv
from dof.config import load_config
from dof.opportunities import (
    REGISTRY, activation_note, rules_for, skip_reason,
)

DISCLAIMER = (
    "Screening tool only. This is not a zoning determination. "
    "Zoning, overlays, lot lines, utilities, and what you can build must be verified "
    "with the city (and usually a surveyor) before you make an offer."
)

_CONF_RANK = {"high": 3, "medium": 2, "low": 1}
_BY_ID = {op["id"]: op for op in REGISTRY}

_CSV_FIELDS = [
    "rank", "score", "confidence", "opportunity_count", "opportunities", "why", "verify",
    "address", "city", "state", "zip", "parcel_id", "owner_name", "zoning", "property_type",
    "lot_sqft", "lot_width_ft", "building_sqft", "bedrooms", "bathrooms", "stories", "units",
    "basement_sqft", "basement_finished_sqft", "garage_sqft", "corner_lot", "alley_access",
    "disclaimer",
]


def screen(props, cfg, columns):
    """Flag and rank properties. `columns` is the column report from load_csv."""
    present = set(columns.get("present") or [])
    enabled_ids = list(cfg.get("enabled") or [])
    unknown = [op_id for op_id in enabled_ids if op_id not in _BY_ID]
    ops = [_BY_ID[op_id] for op_id in enabled_ids if op_id in _BY_ID]
    skipped = []
    runnable = []
    for op in ops:
        reason = skip_reason(op, present, cfg)
        if reason:
            skipped.append({"id": op["id"], "title": op["title"], "reason": reason})
        else:
            runnable.append(op)
    notes = []
    for op in runnable:
        note = activation_note(cfg, op["id"])
        if note:
            notes.append(note)
    if "zoning" not in present and any(op["id"] in ("adu", "middle_housing", "lot_split") for op in runnable):
        notes.append("No zoning column in this file. Zone checks only fire when a lot-size rule you set is met, and those hits stay low confidence.")

    flagged = []
    for prop in props:
        prop = dict(prop)
        prop["_present"] = present
        hits = []
        for op in runnable:
            hit = op["fn"](prop, cfg)
            if hit:
                hits.append(hit)
        hits = _apply_corner_rule(hits, cfg)
        if not hits:
            continue
        hits.sort(key=lambda h: (-h["points"], h["title"]))
        score = sum(h["points"] for h in hits)
        # The row inherits the confidence of its strongest hit. Weaker hits
        # still show their own level in the why text.
        lead = max(hits, key=lambda h: (h["points"], _CONF_RANK[h["confidence"]]))
        flagged.append({
            "prop": prop,
            "hits": hits,
            "score": score,
            "confidence": lead["confidence"],
        })
    flagged.sort(key=lambda row: (-row["score"], -len(row["hits"]), (row["prop"].get("address") or "")))
    return {
        "flagged": flagged,
        "screened": len(props),
        "skipped": skipped,
        "notes": notes,
        "unknown": unknown,
        "turned_off": [op["id"] for op in REGISTRY if op["id"] not in enabled_ids],
        "columns": columns,
    }


def _apply_corner_rule(hits, cfg):
    rules = rules_for(cfg, "corner_or_alley")
    if not rules.get("only_with_another_opportunity"):
        return hits
    if any(h["id"] != "corner_or_alley" for h in hits):
        return hits
    return [h for h in hits if h["id"] != "corner_or_alley"]


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value - round(value)) < 1e-6:
            return str(int(round(value)))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def rows_for_csv(result):
    rows = []
    for rank, item in enumerate(result["flagged"], start=1):
        prop, hits = item["prop"], item["hits"]
        rows.append({
            "rank": rank,
            "score": item["score"],
            "confidence": item["confidence"],
            "opportunity_count": len(hits),
            "opportunities": "; ".join(h["title"] for h in hits),
            "why": " || ".join(f"{h['title']} ({h['confidence']}): {h['why']}" for h in hits),
            "verify": " || ".join(f"{h['title']}: {h['verify']}" for h in hits),
            "address": prop.get("address") or "",
            "city": prop.get("city") or "",
            "state": prop.get("state") or "",
            "zip": prop.get("zip") or "",
            "parcel_id": prop.get("parcel_id") or "",
            "owner_name": prop.get("owner_name") or "",
            "zoning": prop.get("zoning") or "",
            "property_type": prop.get("property_type") or "",
            "lot_sqft": _cell(prop.get("lot_sqft")),
            "lot_width_ft": _cell(prop.get("lot_width_ft")),
            "building_sqft": _cell(prop.get("building_sqft")),
            "bedrooms": _cell(prop.get("bedrooms")),
            "bathrooms": _cell(prop.get("bathrooms")),
            "stories": _cell(prop.get("stories")),
            "units": _cell(prop.get("units")),
            "basement_sqft": _cell(prop.get("basement_sqft")),
            "basement_finished_sqft": _cell(prop.get("basement_finished_sqft")),
            "garage_sqft": _cell(prop.get("garage_sqft")),
            "corner_lot": prop.get("corner_lot") or "",
            "alley_access": prop.get("alley_access") or "",
            "disclaimer": DISCLAIMER,
        })
    return rows


def write_csv(path, result):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rows = rows_for_csv(result)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def render_summary(result, cfg, csv_path, config_path):
    market = cfg.get("market") or {}
    place = ", ".join(p for p in [market.get("city"), market.get("county"), market.get("state")] if p)
    lines = ["Development Opportunity Finder", ""]
    if cfg.get("kind") == "example":
        lines.append("EXAMPLE config. These numbers were looked up so you can try the tool. Verify them before you rely on them.")
    lines.append(f"Market: {market.get('name') or place or '(not set)'}")
    if place and market.get("name"):
        lines.append(f"Place: {place}")
    lines.append(f"Config: {config_path}")
    lines.append(f"File: {csv_path}")
    screened = result["screened"]
    flagged = len(result["flagged"])
    lines.append(f"Screened {screened} properties. {flagged} flagged. {screened - flagged} had no opportunity under your rules.")
    lines.append("")
    lines.append("DISCLAIMER: " + DISCLAIMER)
    lines.append("")
    mapped = result["columns"].get("mapped") or {}
    lines.append(f"Columns mapped ({len(mapped)}):")
    if mapped:
        for header, field in mapped.items():
            lines.append(f"  {header} -> {field}")
    else:
        lines.append("  (none)")
    unmapped = result["columns"].get("unmapped") or []
    lines.append(f"Columns not used ({len(unmapped)}):")
    lines.append("  " + (", ".join(unmapped) if unmapped else "(none)"))
    lines.append("")
    lines.append("Checks skipped because a column or a setting was missing:")
    if result["skipped"]:
        for item in result["skipped"]:
            lines.append(f"  - {item['title']}: {item['reason']}")
    else:
        lines.append("  (none)")
    if result["notes"]:
        lines.append("")
        lines.append("Config still needs:")
        for note in result["notes"]:
            lines.append(f"  - {note}")
    if result["turned_off"]:
        lines.append("")
        lines.append("Turned off in this config: " + ", ".join(result["turned_off"]))
    if result["unknown"]:
        lines.append("")
        lines.append("Unknown ids in enabled: (add a check in dof/opportunities.py): " + ", ".join(result["unknown"]))
    lines.append("")
    lines.append("Flagged properties, highest score first. The confidence on the row is the confidence of its strongest hit. Each opportunity has its own.")
    lines.append("")
    if not result["flagged"]:
        lines.append("(none)")
    for rank, item in enumerate(result["flagged"], start=1):
        prop = item["prop"]
        where = ", ".join(p for p in [prop.get("address"), prop.get("city"), prop.get("state")] if p)
        lines.append(f"{rank}. {where} — score {item['score']} — confidence {item['confidence']}")
        lines.append("   Opportunities: " + "; ".join(h["title"] for h in item["hits"]))
        for hit in item["hits"]:
            lines.append(f"   - {hit['title']} ({hit['confidence']}): {hit['why']}")
            lines.append(f"     Verify: {hit['verify']}")
        lines.append("")
    if market.get("notes"):
        lines.append("Notes from the config:")
        lines.append(market["notes"].strip())
        lines.append("")
    if cfg.get("sources"):
        lines.append("Sources cited in the config (re-check these; codes change):")
        for source in cfg["sources"]:
            lines.append(f"  - {source}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_summary(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Flag development opportunities on a property CSV.")
    parser.add_argument("--csv", required=True, help="Property list: PropStream, assessor, or any CSV")
    parser.add_argument("--config", default="config/my-market.yaml", help="Market rules YAML")
    parser.add_argument("--outdir", default="output", help="Where to write opportunities.csv and summary.txt")
    args = parser.parse_args(argv)
    if not os.path.exists(args.csv):
        print(f"Could not find {args.csv}", file=sys.stderr)
        return 2
    if not os.path.exists(args.config):
        print(f"Could not find {args.config}", file=sys.stderr)
        return 2
    cfg = load_config(args.config)
    props, columns = load_csv(args.csv)
    result = screen(props, cfg, columns)
    csv_out = os.path.join(args.outdir, "opportunities.csv")
    summary_out = os.path.join(args.outdir, "summary.txt")
    write_csv(csv_out, result)
    text = render_summary(result, cfg, args.csv, args.config)
    write_summary(summary_out, text)
    print(text)
    print(f"Wrote {csv_out}")
    print(f"Wrote {summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
