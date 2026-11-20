#!/usr/bin/env python3
"""Step 4: owner lookup and skip trace, through YOUR skip-trace provider.

Owner name, mailing address and motivation signals (long hold, out-of-state,
out-of-county, tax delinquent, no mortgage, estate / trust) already come from the
assessor / parcel data in parcels_ranked.csv. This script gets phones and
emails for those owners without scraping anything:

  export   writes skiptrace_upload_<provider>.csv (generic, batchskiptracing, propstream,
           dealmachine, reisift; see references/skiptrace-templates.json) plus
           export_log.json. Exporting does NOT mean traced: owners stay "not traced"
           until you import urllib.parse
import results. Upload the file to your provider and download
           the results CSV.
  import   reads your provider's results CSV back and writes owners_traced.csv
           with phone 1-5 (number, type: mobile / landline / voip / unknown, the
           provider's DNC flag), email 1-3 and litigator flags, plus
           skiptrace_report.txt (match rate) and failed_records.csv. A provider's DNC
           flag does NOT replace your own National + state DNC scrub.
  api      OPTIONAL and EXPERIMENTAL. BatchData skip-trace API with YOUR key (BATCHDATA_API_KEY env var).
           Always shows a cost preview first (records x --price-per-record) and sends
           nothing without --confirm. Capped by --max (default 25, hard cap 500).
           Built from BatchData's public docs; not tested against a live account.

Companies (LLC, Inc, trust): skip tracers do poorly on these. They are listed in
entities_to_research.csv so you (or Claude) can look up the officers or
registered agent on the state's business-entity search.

Usage:
  python scripts/skip_trace.py export --ranked out/parcels_ranked.csv --tiers "A,B"
  python scripts/skip_trace.py import --ranked out/parcels_ranked.csv --results my_results.csv
  python scripts/skip_trace.py api    --ranked out/parcels_ranked.csv --tiers A --max 50
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import SKIPTRACE_LINE, clean_phone, norm, num, pick, read_rows, split_owner, urlopen, write_rows, yes  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = json.load(open(os.path.join(HERE, "..", "references", "skiptrace-templates.json")))
UPLOAD_FIELDS = TEMPLATES["generic"]
API_HARD_CAP = 500
TRACED_FIELDS = ["owner_key", "owner", "first_name", "last_name", "trace_status"] + \
    [f"phone{i}{s}" for i in range(1, 6) for s in ("", "_type", "_dnc")] + ["email1", "email2", "email3", "litigator", "trace_source"]


def sos_links(owner, state):
    """Links to look up a company: the state's Secretary of State business search (via a search for the official page,
    since states move them), and OpenCorporates (free, covers every US state)."""
    q = urllib.parse.quote_plus
    st = (state or "").strip().upper()
    return {"sos_search_link": "https://www.google.com/search?q=" + q(f"{st or 'state'} secretary of state business entity search"),
            "opencorporates_link": f"https://opencorporates.com/companies" + (f"/us_{st.lower()}" if len(st) == 2 else "") + "?q=" + q(str(owner or "").strip())}


def phone_type(v):
    t = str(v or "").strip().lower()
    if re.search(r"mobile|wireless|cell", t):
        return "mobile"
    if re.search(r"land ?line|residential|wired|fixed", t):
        return "landline"
    if "voip" in t:
        return "voip"
    return "unknown"


def provider_row(rec, provider):
    """Map the generic record onto a provider's column names."""
    m = {"Owner First Name": rec["First Name"], "Owner Last Name": rec["Last Name"], "Owner Name": rec["Owner Full Name"],
         "Property Street Address": rec["Property Address"], "Property Zip Code": rec["Property Zip"],
         "Mailing Street Address": rec["Mailing Address"], "Mailing Zip Code": rec["Mailing Zip"]}
    return {c: rec.get(c, m.get(c, "")) for c in TEMPLATES[provider]}


def owner_key(owner, mail_street, mail_zip):
    return (norm(owner)[:40] + "|" + norm(mail_street)[:30] + "|" + str(mail_zip or "")[:5]).strip("|")


def load_ranked(path, tiers, top):
    rows = [r for r in read_rows(path) if str(r.get("rank") or "").strip()]
    rows.sort(key=lambda r: num(r["rank"]) or 1e9)
    if tiers:
        want = [t.strip().upper() for t in tiers.split(",") if t.strip()]
        rows = [r for r in rows if str(r.get("tier") or "")[:1].upper() in want]
    return rows[:top] if top else rows


def owners_from(rows):
    """One record per owner (an owner with 3 parcels is traced once)."""
    out = {}
    for r in rows:
        k = owner_key(r.get("owner"), r.get("mail_street") or r.get("mail_address"), r.get("mail_zip"))
        if not norm(r.get("owner")):
            continue
        o = out.setdefault(k, {"owner_key": k, "owner": (r.get("owner") or "").strip(), "rows": []})
        o["rows"].append(r)
    return list(out.values())


def _suppression(paths):
    import suppression
    rows = []
    for p in paths or []:
        rows += suppression.load(p)
    return suppression.Suppression(rows)


def _suppressed(sup, o):
    if not len(sup):
        return False
    r = o["rows"][0]
    addrs = [" ".join(str(x) for x in (r.get("mail_street"), r.get("mail_city"), r.get("mail_state"), r.get("mail_zip")) if x),
             r.get("mail_street") or "", r.get("address") or ""]
    return bool(sup.owner(o["owner"], addrs, "all"))


def cmd_export(a):
    rows = load_ranked(a.ranked, a.tiers, a.top)
    sup = _suppression(getattr(a, "suppress", None))
    owners = owners_from(rows)
    skipped_sup = [o for o in owners if _suppressed(sup, o)]
    owners = [o for o in owners if not _suppressed(sup, o)]
    up, ent = [], []
    for o in owners:
        r = o["rows"][0]
        sp = split_owner(o["owner"])
        rec = {"First Name": sp["first"], "Last Name": sp["last"], "Owner Full Name": o["owner"],
               "Mailing Address": r.get("mail_street", ""), "Mailing City": r.get("mail_city", ""),
               "Mailing State": r.get("mail_state", ""), "Mailing Zip": r.get("mail_zip", ""),
               "Property Address": r.get("address", ""), "Property City": r.get("city", ""),
               "Property State": r.get("state", ""), "Property Zip": r.get("zip", ""),
               "APN": "; ".join(x.get("apn", "") for x in o["rows"]), "Owner Key": o["owner_key"]}
        if sp["entity"]:
            st_ = (r.get("mail_state") or r.get("state") or "").strip().upper()
            ent.append({"owner": o["owner"], "mailing": " ".join(x for x in (r.get("mail_street"), r.get("mail_city"), r.get("mail_state"), r.get("mail_zip")) if x),
                        "apns": rec["APN"], "state_to_search": st_, **sos_links(o["owner"], st_),
                        "next_step": "Open sos_search_link (your state's Secretary of State business search) and search the exact name. "
                                     "Fill registered_agent and officer_or_agent, then skip-trace that person. Trusts: ask for the trustee.",
                        "registered_agent": "", "officer_or_agent": "", "notes": ""})
        if not a.include_entities and sp["entity"]:
            continue
        if not rec["Mailing Address"]:
            continue
        up.append(rec)
    out = a.output_dir or os.path.join(os.path.dirname(a.ranked) or ".", "skiptrace")
    providers = [p for p in TEMPLATES if not p.startswith("_")] if a.provider == "all" else ["generic", a.provider]
    for prov in dict.fromkeys(providers):
        if prov not in TEMPLATES:
            raise SystemExit("Unknown provider " + prov + ". Pick: " + ", ".join(k for k in TEMPLATES if not k.startswith("_")))
        write_rows(os.path.join(out, f"skiptrace_upload_{prov}.csv"), [provider_row(u, prov) for u in up], TEMPLATES[prov])
    write_rows(os.path.join(out, "skiptrace_upload.csv"), up, UPLOAD_FIELDS)
    with open(os.path.join(out, "README_UPLOAD.txt"), "w") as f:
        f.write("Skip-trace upload files - GENERIC FORMAT, CHECK YOUR PROVIDER'S TEMPLATE.\n\n"
                "Each skiptrace_upload_<provider>.csv follows that provider's commonly used column names as of Nov 2026.\n"
                "Providers change their templates. Before you upload, download your provider's current template and map\n"
                "or rename the columns to match. Owner Key must come back in the results file so they can be matched.\n"
                f"Owners left out because they are on your suppression list: {len(skipped_sup)}.\n\n"
                + SKIPTRACE_LINE + "\n(skip_trace.py import, then build_marketing_lists.py: suppression, DNC scrub and calling-hour checks happen there.)\n")
    import datetime as _dt
    with open(os.path.join(out, "export_log.json"), "w") as f:
        json.dump({"exported_on": _dt.date.today().isoformat(), "status": "exported - NOT traced until results are imported",
                   "owner_keys": [u["Owner Key"] for u in up]}, f, indent=1)
    write_rows(os.path.join(out, "entities_to_research.csv"), ent,
               ["owner", "mailing", "apns", "state_to_search", "sos_search_link", "opencorporates_link", "next_step", "registered_agent",
                "officer_or_agent", "notes"])
    print(f"Skip-trace export: {len(owners)} owners from {len(rows)} parcels -> {len(up)} people in skiptrace_upload.csv, "
          f"{len(ent)} companies/trusts in entities_to_research.csv"
          + ("" if a.include_entities else " (not in the upload; add --include-entities to send them anyway)") + ".")
    print("Upload skiptrace_upload_<your provider>.csv (generic format, check your provider's template) to your skip-trace provider, "
          "then run: skip_trace.py import --results <their file>")
    print(SKIPTRACE_LINE)
    return up, ent


# ---- import ---------------------------------------------------------------
PHONE_WORD = r"(phone|mobile|cell|wireless|landline|telephone)"


def _hn(h):
    h = re.sub(r"[_\-#]+", " ", str(h)).lower()
    h = re.sub(r"\b(owner|contact|person|number|num|no)\b", " ", h)
    h = re.sub(r"([a-z])(\d)", r"\1 \2", h)
    return re.sub(r"\s+", " ", h).strip()


def find_phone_columns(headers):
    """Return [(phone_col, type_col, dnc_col, implied_type)] in file order.

    Handles "Phone 1" / "Phone1" / "phone_1" / "Mobile 2" / "Landline 1", with
    sibling "Phone 1 Type" and "Phone 1 DNC" (or "Phone1_DNC") columns.
    """
    norm_h = {h: _hn(h) for h in headers}
    out = []
    for h in headers:
        m = re.fullmatch(PHONE_WORD + r"(?: (\d+))?", norm_h[h])
        if not m:
            continue
        word, idx = m.group(1), m.group(2) or ""
        implied = "mobile" if word in ("mobile", "cell", "wireless") else ("landline" if word == "landline" else "")
        prefix = (word + " " + idx).strip()
        tcol = next((h2 for h2 in headers if norm_h[h2].startswith(prefix + " ") and "type" in norm_h[h2]), None)
        dcol = next((h2 for h2 in headers if norm_h[h2].startswith(prefix + " ") and re.search(r"\bdnc\b|do not call", norm_h[h2])), None)
        out.append((h, tcol, dcol, implied))
    return out


def cmd_import(a):
    res = read_rows(a.results)
    if not res:
        raise SystemExit("Results file is empty.")
    H = list(res[0].keys())
    phones = find_phone_columns(H)
    emails = [h for h in H if re.match(r"^(owner\s*)?e-?mail\s*(address)?\s*\d*$", re.sub(r"[_\-]+", " ", h).strip(), re.I)]
    c_key = pick(H, ["Owner Key", "owner_key"])
    c_apn = pick(H, ["APN", "Parcel", "Parcel Number", "parcel_id"])
    c_first, c_last = pick(H, ["First Name", "Owner First Name", "first_name"]), pick(H, ["Last Name", "Owner Last Name", "last_name"])
    c_full = pick(H, ["Owner Full Name", "Owner Name", "Full Name", "owner"])
    c_maddr, c_mzip = pick(H, ["Mailing Address", "Mail Address", "mailing_street"]), pick(H, ["Mailing Zip", "Mail Zip", "mailing_zip"])
    c_lit = pick(H, ["Litigator", "Is Litigator", "TCPA Litigator", "litigator"])
    if not phones and not emails:
        raise SystemExit("Could not find phone or email columns in the results file. Columns seen: " + ", ".join(H))

    owners = {o["owner_key"]: o for o in owners_from(load_ranked(a.ranked, None, None))}
    by_apn = {}
    for k, o in owners.items():
        for r in o["rows"]:
            if r.get("apn"):
                by_apn[norm(r["apn"])] = k
    by_mail = {(norm(o["rows"][0].get("mail_street"))[:30], str(o["rows"][0].get("mail_zip") or "")[:5]): k for k, o in owners.items()}

    traced, unmatched, unmatched_list = [], 0, []
    for r in res:
        k = (r.get(c_key) or "").strip() if c_key else ""
        if k not in owners and c_apn:
            for ap_ in re.split(r"[;,]", r.get(c_apn) or ""):
                if norm(ap_) in by_apn:
                    k = by_apn[norm(ap_)]; break
        if k not in owners and c_maddr:
            k = by_mail.get((norm(r.get(c_maddr))[:30], str(r.get(c_mzip) or "")[:5]) if c_mzip else None, "")
        if k not in owners:
            unmatched += 1
            unmatched_list.append({"reason": "result row did not match any owner", **{h: r.get(h, "") for h in H[:8]}})
            continue
        rec = {"owner_key": k, "owner": owners[k]["owner"],
               "first_name": r.get(c_first, "") if c_first else "", "last_name": r.get(c_last, "") if c_last else "",
               "litigator": "Y" if c_lit and yes(r.get(c_lit)) else "", "trace_source": os.path.basename(a.results)}
        n = 0
        for pc, tc, dc, implied in phones:
            p = clean_phone(r.get(pc))
            if not p or n >= 5:
                continue
            n += 1
            rec[f"phone{n}"] = p
            rec[f"phone{n}_type"] = phone_type(r.get(tc) if tc else implied)
            flag = yes(r.get(dc)) if dc else None
            rec[f"phone{n}_dnc"] = "Y" if flag is True else ("N" if flag is False else "unknown")
        m = 0
        for ec in emails:
            e = (r.get(ec) or "").strip()
            if "@" in e and m < 3:
                m += 1
                rec[f"email{m}"] = e
        if c_full and not rec["first_name"]:
            rec["first_name"] = split_owner(r.get(c_full)).get("first", "")
        rec["trace_status"] = "hit" if (rec.get("phone1") or rec.get("email1")) else "no hit"
        traced.append(rec)
    out = a.output or os.path.join(os.path.dirname(a.ranked) or ".", "skiptrace", "owners_traced.csv")
    write_rows(out, traced, TRACED_FIELDS)
    with_phone = sum(1 for t in traced if t.get("phone1"))
    mobiles = sum(1 for t in traced if any(t.get(f"phone{i}_type") == "mobile" for i in range(1, 6)))
    sent = []
    log = os.path.join(os.path.dirname(out), "export_log.json")
    if os.path.exists(log):
        sent = json.load(open(log)).get("owner_keys", [])
    got = {t["owner_key"] for t in traced}
    failed = [{"reason": "uploaded, no result row", "owner_key": k} for k in sent if k not in got] + \
             [{"reason": "no phone or email found", "owner_key": t["owner_key"], "owner": t["owner"]} for t in traced if t["trace_status"] == "no hit"] + \
             unmatched_list
    write_rows(os.path.join(os.path.dirname(out), "failed_records.csv"), failed)
    hits = {t["owner_key"] for t in traced if t["trace_status"] == "hit"}
    base = len(sent) or len(traced)
    nhit = len(hits & set(sent)) if sent else len(hits)
    report = [f"Skip-trace results: {os.path.basename(a.results)}",
              f"Owners uploaded (export_log.json): {len(sent) if sent else 'unknown'}",
              f"Result rows matched to an owner: {len(traced)}; not matched: {unmatched}",
              f"Uploaded owners with a hit (phone or email): {nhit} of {base} = {(100.0 * nhit / base) if base else 0:.0f}% match rate",
              f"With a phone: {with_phone}; with a mobile number: {mobiles}",
              f"Phone types: " + ", ".join(f"{k} {v}" for k, v in sorted(
                  {ty: sum(1 for t in traced for i in range(1, 6) if t.get(f"phone{i}_type") == ty) for ty in ("mobile", "landline", "voip", "unknown")}.items())),
              "Failed / no-hit records: failed_records.csv",
              "The provider's DNC flag is a convenience, not a scrub. Scrub every number against the National DNC Registry and your state list yourself."]
    with open(os.path.join(os.path.dirname(out), "skiptrace_report.txt"), "w") as f:
        f.write("\n".join(report) + "\n")
    print(f"Skip-trace import: {len(traced)} owners matched ({with_phone} with a phone), {unmatched} result rows not matched. -> {out}")
    if any(t.get(f"phone{i}_dnc") == "unknown" for t in traced for i in range(1, 6)):
        print("Your results file has no DNC column, so DNC status is 'unknown'. Scrub against the DNC registry before calling or texting.")
    return traced


# ---- api (optional, BatchData) -------------------------------------------
BATCHDATA_URL = "https://api.batchdata.com/api/v1/property/skip-trace"


def cmd_api(a):
    if a.price_per_record is None or a.price_per_record <= 0:
        raise SystemExit("BatchData needs --price-per-record <your plan's price, e.g. 0.12>. The kit will not run (or even preview) "
                         "a paid lookup without a known cost. Find the price on your BatchData plan page.")
    key = os.environ.get("BATCHDATA_API_KEY", "").strip()
    cap = min(a.max, API_HARD_CAP)
    rows = load_ranked(a.ranked, a.tiers, None)
    sup = _suppression(a.suppress)
    owners = [o for o in owners_from(rows) if not split_owner(o["owner"])["entity"] and not _suppressed(sup, o)]
    reqs = []
    for o in owners:
        r = o["rows"][0]
        if r.get("address") and r.get("city") and r.get("state"):
            addr = {"street": r["address"], "city": r["city"], "state": r["state"], "zip": r.get("zip", "")}
        elif r.get("mail_street"):
            # vacant land often has no situs address: trace the owner at their mailing address
            addr = {"street": r["mail_street"], "city": r.get("mail_city", ""), "state": r.get("mail_state", ""), "zip": r.get("mail_zip", "")}
        else:
            continue
        reqs.append((o, {"propertyAddress": addr}))
    reqs = reqs[:cap]
    cost = f"${len(reqs) * a.price_per_record:,.2f} at ${a.price_per_record:.2f}/record"
    preview = ["EXPERIMENTAL: built from BatchData's public docs and not yet run against a live account. Check the first results by hand.",
               f"BatchData skip-trace preview: {len(reqs)} records (cap {cap}; companies skipped).",
               f"Estimated cost: {cost}. Billed to YOUR BatchData account.",
               "Nothing is sent without --confirm."]
    out_dir = os.path.join(os.path.dirname(a.ranked) or ".", "skiptrace")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "api_cost_preview.txt"), "w") as f:
        f.write("\n".join(preview) + "\n")
    print("\n".join(preview))
    if not a.confirm or a.dry_run:
        return []
    if not key:
        print("No BATCHDATA_API_KEY set, so nothing was sent. Use export/import with any provider instead.")
        return []
    out_rows = []
    for i in range(0, len(reqs), 50):
        chunk = reqs[i:i + 50]
        body = json.dumps({"requests": [q for _, q in chunk]}).encode()
        req = urllib.request.Request(BATCHDATA_URL, data=body, method="POST",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
        except Exception as e:
            raise SystemExit("BatchData call failed: " + str(e)[:200] + ". Use export/import instead.")
        persons = ((d.get("results") or {}).get("persons")) or []
        for j, (o, _) in enumerate(chunk):
            p = persons[j] if j < len(persons) else {}
            rec = {"Owner Key": o["owner_key"], "First Name": ((p.get("name") or {}).get("first") or ""),
                   "Last Name": ((p.get("name") or {}).get("last") or ""), "Litigator": "Y" if p.get("litigator") else ""}
            for n, ph in enumerate((p.get("phoneNumbers") or [])[:5], 1):
                rec[f"Phone {n}"] = ph.get("number", "")
                rec[f"Phone {n} Type"] = ph.get("type", "")
                rec[f"Phone {n} DNC"] = "Y" if ph.get("dnc") else "N"
            for n, em in enumerate((p.get("emails") or [])[:3], 1):
                rec[f"Email {n}"] = em.get("email", "") if isinstance(em, dict) else str(em)
            out_rows.append(rec)
        time.sleep(1)
    out_dir = os.path.join(os.path.dirname(a.ranked) or ".", "skiptrace")
    cols = ["Owner Key", "First Name", "Last Name", "Litigator"] + \
        [f"Phone {n}{x}" for n in range(1, 6) for x in ("", " Type", " DNC")] + [f"Email {n}" for n in range(1, 4)]
    raw = write_rows(os.path.join(out_dir, "batchdata_results.csv"), out_rows, cols)
    a.results, a.output = raw, None
    return cmd_import(a)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export"); e.add_argument("--ranked", required=True); e.add_argument("--tiers", default="A,B")
    e.add_argument("--top", type=int, default=0, help="only the top N parcels (0 = all in the tiers)")
    e.add_argument("--include-entities", action="store_true"); e.add_argument("--output-dir")
    e.add_argument("--provider", default="all", help="generic, batchskiptracing, propstream, dealmachine, reisift, or all (default)")
    e.add_argument("--suppress", action="append", default=[], help="suppression CSV(s); owners suppressed for every channel are not exported")
    i = sub.add_parser("import"); i.add_argument("--ranked", required=True); i.add_argument("--results", required=True); i.add_argument("--output")
    p = sub.add_parser("api"); p.add_argument("--ranked", required=True); p.add_argument("--tiers", default="A")
    p.add_argument("--max", type=int, default=25, help=f"most records to send (hard cap {API_HARD_CAP})")
    p.add_argument("--price-per-record", type=float, help="REQUIRED: your plan's price per record, for the cost preview")
    p.add_argument("--suppress", action="append", default=[], help="suppression CSV(s); suppressed owners are not sent")
    p.add_argument("--confirm", action="store_true", help="actually send (after you have read the cost preview)")
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    return {"export": cmd_export, "import": cmd_import, "api": cmd_api}[a.cmd](a)


if __name__ == "__main__":
    main()
