#!/usr/bin/env python3
"""Step 2b: add lot-split / ADU / middle-housing signals to the ranked parcels.

This runs the original Development Opportunity Finder screen (the dof/ package)
on the SAME parcel file you scored, using your city config
(config/my-market.yaml), and joins the hits onto parcels_ranked.csv by APN
(or address). It also estimates a rough lot yield for subdivision buyers when
your config has a minimum new-lot size (gross = acres / min lot; net = after
roads, storm water and open space, default 70%). Overlay zones are NOT checked.

These are extra signals. They do not change the Land Score or the rank.

Usage:
  python scripts/add_split_adu_signals.py --parcels parcels.csv \
      --ranked out/parcels_ranked.csv --config config/my-market.yaml

If the config is still blank (no zoning codes, no lot sizes) nothing is flagged,
and the script says so. Zoning must be verified with the city.
"""
import argparse, csv, math, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dof.columns import load_csv  # noqa: E402
from dof.config import load_config  # noqa: E402
from dof.opportunities import allowed_codes, codes_match, effective_rules  # noqa: E402
from dof.run import screen  # noqa: E402
from _common import num, read_rows, write_rows  # noqa: E402


def key(v):
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parcels", required=True, help="the parcel file you scored (CSV)")
    ap.add_argument("--ranked", help="parcels_ranked.csv from score_parcels.py (updated in place)")
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "my-market.yaml"))
    ap.add_argument("--lot-efficiency", type=float, default=0.70,
                    help="share of gross land left for lots after roads, storm water and open space (default 0.70)")
    ap.add_argument("--hits-out", help="where to write every split/ADU hit (default: next to --ranked, or out/split_adu_hits.csv)")
    a = ap.parse_args(argv)

    cfg = load_config(a.config)
    props, columns = load_csv(a.parcels)
    result = screen(props, cfg, columns)
    hits = {}
    for item in result["flagged"]:
        p = item["prop"]
        rec = {"split_adu_signals": "; ".join(h["title"] for h in item["hits"]),
               "split_adu_confidence": item["confidence"],
               "split_adu_why": " || ".join(f"{h['title']}: {h['why']}" for h in item["hits"])}
        for k in (key(p.get("parcel_id")), key(p.get("address"))):
            if k:
                hits.setdefault(k, rec)
    out_dir = os.path.dirname(a.ranked) if a.ranked else "out"
    hits_path = a.hits_out or os.path.join(out_dir or ".", "split_adu_hits.csv")
    write_rows(hits_path, [dict(parcel_id=i["prop"].get("parcel_id") or "", address=i["prop"].get("address") or "",
                                **{"signals": "; ".join(h["title"] for h in i["hits"]), "confidence": i["confidence"],
                                   "why": " || ".join(h["why"] for h in i["hits"]),
                                   "verify": " || ".join(h["verify"] for h in i["hits"])}) for i in result["flagged"]],
               ["parcel_id", "address", "signals", "confidence", "why", "verify"])
    notes = list(result.get("notes") or [])
    skipped = [s["title"] + ": " + s["reason"] for s in result.get("skipped") or []]

    added = yields = 0
    if a.ranked:
        rows = read_rows(a.ranked)
        for r in rows:
            h = hits.get(key(r.get("apn"))) or hits.get(key(r.get("address"))) or {}
            r["split_adu_signals"] = h.get("split_adu_signals", "")
            r["split_adu_confidence"] = h.get("split_adu_confidence", "")
            r["split_adu_why"] = h.get("split_adu_why", "")
            added += bool(h)
            rules, _ = effective_rules(cfg, "lot_split", r.get("zoning_use"))
            each = rules.get("min_lot_sqft")
            acres = num(r.get("acres"))
            r["est_lot_yield_gross"] = r["est_lot_yield_net"] = ""
            codes = allowed_codes(cfg, "lot_split")
            zone_ok = (any(codes_match(r.get("zoning_use"), c)[0] for c in codes) if codes else False) or "Lot split" in r["split_adu_signals"]
            if each and acres and zone_ok:
                gross = int(math.floor(acres * 43560 / float(each)))
                net = int(math.floor(acres * 43560 * a.lot_efficiency / float(each)))
                if net >= 2:
                    r["est_lot_yield_gross"], r["est_lot_yield_net"] = gross, net
                    yields += 1
            r.pop("est_lot_yield", None)
        fields = list(rows[0].keys()) if rows else []
        write_rows(a.ranked, rows, fields)
    print(f"Split/ADU screen: {len(props)} parcels, {len(result['flagged'])} with a signal, {added} joined to the ranked list, "
          f"{yields} with a lot-yield estimate.")
    for n_ in notes + skipped:
        print(" - " + n_)
    print("Lot yield: gross = acres / minimum lot size; net = gross x " + f"{a.lot_efficiency:.0%}" +
          " (roads, storm water, open space). Rough screen, not a plat.")
    print("Overlay zones, historic districts, critical areas and deed restrictions were NOT checked. "
          "These are extra signals, not a zoning answer. Verify with the city.")
    return result


if __name__ == "__main__":
    main()
