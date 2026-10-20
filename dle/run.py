"""python -m dle.run --county wa_king  [--dry-run] [--check]"""
import argparse, glob, json, os, sys, traceback
from datetime import date
import yaml
from .core import lead, merge, Store, write_csv
from .sources import FETCHERS, pick
from .enrich import arcgis_parcels
from .integrations.llc import pierce
from .integrations.skiptrace import skiptrace
from .integrations.outreach import write_copy, export


def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def run_county(cfg, dry_run=False, check=False):
    name, st = cfg["county"], cfg["state"]
    raw, status = [], []
    for src in cfg["sources"]:
        if not src.get("enabled", True):
            status.append({"source": src["name"], "list_type": src["list_type"], "status": "disabled", "rows": 0,
                           "note": src.get("note", "")})
            continue
        try:
            rows = FETCHERS[src["type"]]({"county": name, "state": st, **src})
            m = src.get("map", {})
            got = [lead(name, st, src["list_type"], pick(r, m.get("address")), pick(r, m.get("city")),
                        pick(r, m.get("zip")), pick(r, m.get("parcel_id")), pick(r, m.get("owner_name")),
                        pick(r, m.get("event_date")), pick(r, m.get("amount")), pick(r, m.get("details")),
                        pick(r, m.get("source_url")) or src.get("public_url", src.get("url", "")))
                   for r in rows]
            raw += got
            status.append({"source": src["name"], "list_type": src["list_type"], "status": "ok", "rows": len(got)})
        except Exception as e:
            status.append({"source": src["name"], "list_type": src["list_type"], "status": "FAILED", "rows": 0,
                           "note": str(e)[:200]})
    if cfg.get("parcel_enrich"):
        try:
            arcgis_parcels(raw, cfg["parcel_enrich"])
        except Exception as e:
            status.append({"source": "parcel_enrich", "status": "FAILED", "note": str(e)[:200]})
    if check:
        return [], status
    rows = merge(raw)
    Store(f"data/{cfg['id']}.sqlite").mark(rows, dry_run=dry_run)
    rows.sort(key=lambda r: (r["is_new"] == "", -r["score"], -int((r["event_date"] or "0").replace("-", ""))))
    pierce(rows, st, cfg.get("sos_search_url"))
    st_cfg = cfg.get("skiptrace", {})
    rows, note = skiptrace(rows, st, st_cfg.get("min_score", 40), int(os.getenv("SKIPTRACE_MAX_PER_RUN", st_cfg.get("max_per_run", 100))))
    status.append({"source": "skiptrace", "status": note})
    mk = {"your_name": os.getenv("YOUR_NAME", "[Your Name]"), "company": os.getenv("YOUR_COMPANY", "[Company]"),
          "phone": os.getenv("YOUR_PHONE", "[Phone]")}
    for r in rows:
        write_copy(r, mk)
    return rows, status


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", action="append", help="config id in counties/ (default: all)")
    ap.add_argument("--dry-run", action="store_true", help="don't save history")
    ap.add_argument("--check", action="store_true", help="only test that each source works")
    a = ap.parse_args()
    files = [f"counties/{c}.yaml" for c in a.county] if a.county else sorted(glob.glob("counties/*.yaml"))
    files = [f for f in files if not os.path.basename(f).startswith("_")]
    today = date.today().isoformat()
    outdir = f"output/{today}"
    os.makedirs(outdir, exist_ok=True)
    all_rows, summary = [], []
    for f in files:
        cfg = yaml.safe_load(open(f))
        rows, status = run_county(cfg, a.dry_run, a.check)
        all_rows += rows
        summary.append({"county": cfg["county"], "state": cfg["state"], "sources": status})
    if not a.check:
        write_csv(all_rows, f"{outdir}/leads.csv")
        write_csv([r for r in all_rows if r["is_new"]], f"{outdir}/new_leads.csv")
        write_csv(all_rows, "output/latest.csv")
        summary.append({"outreach": export([r for r in all_rows if r["is_new"]], outdir,
                                           all_rows[0]["state"] if all_rows else "", {})})
    json.dump(summary, open(f"{outdir}/run_summary.json", "w"), indent=2)
    # human summary
    print(f"\n=== Distressed Lead Engine - {today} ===")
    for s in summary:
        if "county" in s:
            print(f"\n{s['county']} County, {s['state']}")
            for x in s["sources"]:
                print(f"  {x.get('status',''):>8}  {x.get('list_type',''):<16} {x['source']:<40} {x.get('rows','')}  {x.get('note','')}")
    if not a.check:
        from collections import Counter
        c = Counter(t for r in all_rows for t in r["list_types"].split(";"))
        print(f"\nProperties: {len(all_rows)}  NEW today: {sum(1 for r in all_rows if r['is_new'])}  "
              f"stacked (2+ lists): {sum(1 for r in all_rows if r['list_count'] > 1)}")
        print("By list:", dict(c))
        print(f"Files: {outdir}/leads.csv, {outdir}/new_leads.csv, {outdir}/invelo_import.csv")
    failed = any(x.get("status") == "FAILED" for s in summary if "sources" in s for x in s["sources"])
    sys.exit(1 if failed and os.getenv("FAIL_ON_SOURCE_ERROR") else 0)


if __name__ == "__main__":
    main()
