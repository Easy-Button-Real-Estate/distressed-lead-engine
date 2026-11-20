#!/usr/bin/env python3
"""List (and, with --delete, remove) old output files that hold personal data.

  PY scripts/cleanup_exports.py                 # list files older than 90 days in out/ and out_demo/
  PY scripts/cleanup_exports.py --days 30 --delete

Never touched, whatever their age: the suppression list (state/suppression.csv and the suppress/
folder), consent_log.csv, call_review.csv, seen_owners.json. Keep those at least 5 years.
Nothing is uploaded or sent anywhere.
"""
import argparse, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = {"suppression.csv", "consent_log.csv", "call_review.csv", "seen_owners.json"}
PERSONAL = (".csv", ".xlsx", ".txt", ".md", ".html", ".json", ".jpg")


def old_files(folders, days, now=None):
    now = now or time.time()
    out = []
    for top in folders:
        if not os.path.isdir(top):
            continue
        for d, dirs, files in os.walk(top):
            if os.path.basename(d) == "state" or "suppress" in os.path.relpath(d, top).split(os.sep):
                continue
            for fn in files:
                p = os.path.join(d, fn)
                if fn in KEEP or not fn.lower().endswith(PERSONAL):
                    continue
                age = (now - os.path.getmtime(p)) / 86400
                if age > days:
                    out.append((p, age))
    return sorted(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--folder", action="append", help="output folder(s) to check (default out/ and out_demo/)")
    ap.add_argument("--delete", action="store_true", help="actually delete them (default: only list)")
    a = ap.parse_args(argv)
    folders = a.folder or [os.path.join(os.getcwd(), "out"), os.path.join(os.getcwd(), "out_demo"), os.path.join(ROOT, "out"), os.path.join(ROOT, "out_demo")]
    files = old_files(dict.fromkeys(os.path.abspath(f) for f in folders), a.days)
    for p, age in files:
        print(f"{'deleting' if a.delete else 'old'}: {p} ({age:.0f} days)")
        if a.delete:
            os.remove(p)
    print(f"{len(files)} file(s) older than {a.days} days" + ("" if a.delete else ". Nothing deleted; add --delete to remove them.") +
          " The suppression list, consent log and call reviews are always kept.")
    return files


if __name__ == "__main__":
    main()
