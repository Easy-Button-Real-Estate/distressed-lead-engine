#!/usr/bin/env python3
"""Run the whole pipeline in one go: buy box -> score -> split/ADU signals ->
satellite -> skip-trace export (or import) -> marketing lists -> campaign kit.

Try it on the made-up sample data (works offline; writes to out_demo/ and never touches
your real out/state/ files):
  python scripts/run_pipeline.py --demo

Your market:
  python scripts/run_pipeline.py --parcels parcels.csv --sales sales.csv \
      --market "Hamilton County, IN" --use-case single_family \
      --infra infra.csv --config config/my-market.yaml --your-name "Pat Lee"

  Add --skiptrace-results their_file.csv after your skip-trace provider returns results.
  Non-disclosure state (TX etc.): --state TX --price-only --sales your_sold_comps.csv
  Texting list: --sms --consent-file my_consent.csv (numbers that gave YOU consent)

Run it weekly (say "refresh my county" to Claude). Automatic scheduling needs separate setup.
Your suppression list (out/state/suppression.csv) is applied on every run.

Every step can also be run on its own (see the scripts/ folder). Nothing is sent
to anyone. START_HERE.md in the output folder says what happened and what to do next.
"""
import argparse, contextlib, datetime as dt, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import add_split_adu_signals, build_buy_box, enrich_constraints, fetch_arcgis_parcels, build_marketing_lists, campaign_kit, satellite_check, score_parcels, skip_trace  # noqa: E402
from _common import PRIVACY_PARAGRAPH, SKIPTRACE_LINE, SOURCE_UNAVAILABLE, friendly_error, read_rows  # noqa: E402

S = os.path.join(ROOT, "samples")


def step(title, fn, argv, quiet):
    print(f"\n== {title}")
    buf = io.StringIO()
    if quiet:
        with contextlib.redirect_stdout(buf):
            res = fn(argv)
    else:
        res = fn(argv)
    return res, buf.getvalue()


BUYER_COLS = ["rank", "tier", "priority", "land_score", "apn", "address", "city", "county", "state", "zip", "acres", "zoning_use",
              "why", "flags", "missing_data", "research_next", "lat", "lon", "map_link"]


def write_buyer_package(ranked, path):
    """Buyer-facing export: parcel facts and scores only. No owner name, mailing address, phone or email."""
    if not os.path.exists(ranked):
        return 0
    rows_ = [r for r in read_rows(ranked) if str(r.get("rank") or "").strip()]
    with open(path, "w", newline="") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=BUYER_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows_:
            w.writerow({k: r.get(k, "") for k in BUYER_COLS})
    return len(rows_)


def enrich_shortlist(parcels, ranked, n, out, quiet=True, apns=None, label=None):
    """FEMA / NWI / USGS lookups for the top-n ranked parcels (in rank order), or for the given APNs, written to
    out/parcels_enriched.csv. Every other parcel is kept as is (so earlier lookups in `parcels` survive).
    Returns enrich_constraints' result plus the output path and the APNs looked up."""
    import csv as _csv
    df = score_parcels.load_table(parcels)
    apn_c = score_parcels.pick(df, "apn")
    top = list(apns) if apns is not None else [str(r.get("apn") or "") for r in read_rows(ranked) if str(r.get("rank") or "").strip()][:n]
    top = [x for x in dict.fromkeys(top) if x]
    if not top or not apn_c:
        return None
    pos = {k: i for i, k in enumerate(top)}
    df["_order"] = [pos.get(str(v), len(top) + i) for i, v in enumerate(df[apn_c])]
    df = df.sort_values("_order", kind="stable").drop(columns=["_order"])
    tmp = os.path.join(out, "_shortlist_order.csv")
    df.to_csv(tmp, index=False, quoting=_csv.QUOTE_MINIMAL)
    dest = os.path.join(out, "parcels_enriched.csv")
    print(f"\n== {label or '2a. Flood / wetlands / slope lookups for the top ' + str(len(top))} (FEMA NFHL, USFWS NWI, USGS 3DEP)")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf) if quiet else contextlib.nullcontext():
        res = enrich_constraints.main(["--input", tmp, "--output", dest, "--limit", str(len(top))])
    os.remove(tmp)
    res = dict(res or {}, output=dest, apns=top)
    print(f"   {res.get('ok', 0)} of {res.get('checked', 0)} parcels fully checked" +
          (" (NWI returned nothing for the whole area: wetlands left unknown)" if res.get("nwi_zero_everywhere") else ""))
    return res


ENRICH_MAX_ROUNDS = 6


def research_targets(ranked, top_n):
    """APNs that must have flood / wetlands / slope looked up after a rescore: every tier-A row, every row whose
    priority reaches the tier-A line (held in B only because it is unchecked) and the top max(10, --top) rows."""
    rows_ = [r for r in read_rows(ranked) if str(r.get("rank") or "").strip()]
    want = []
    for i, r in enumerate(rows_):
        try:
            pr = float(r.get("priority") or 0)
        except ValueError:
            pr = 0.0
        if i < max(10, top_n) or str(r.get("tier") or "").startswith("A") or pr >= 72:
            want.append(str(r.get("apn") or ""))
    return [x for x in want if x]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="run on the made-up sample files")
    ap.add_argument("--parcels", help="parcel export (CSV/XLSX) or fetch_arcgis_parcels.py output")
    ap.add_argument("--sales", help="recent land sales (or a parcel export with last-sale columns) for the buy box")
    ap.add_argument("--buy-box", help="use an existing buy-box JSON instead of building one from --sales")
    ap.add_argument("--parcel-layer", help="public ArcGIS parcel layer URL to pull fresh parcels (and sales) from")
    ap.add_argument("--bbox", help='area for --parcel-layer: "S,W,N,E"')
    ap.add_argument("--min-acres", type=float, default=0)
    ap.add_argument("--county-code", action="append", default=[], help="jurisdiction value meaning unincorporated county (e.g. WC in Wake)")
    ap.add_argument("--sales-bbox", help='area for the sales pull (default: the whole layer, which gives the buy box more deeds)')
    ap.add_argument("--parcel-where", help="extra filter for the parcel pull, e.g. \"BLDG_VAL = 0\" for vacant land")
    ap.add_argument("--sales-where", help="where clause for recent sales on the same layer, e.g. \"SALEDATE >= DATE '2024-11-01'\"")
    ap.add_argument("--state", default="", help="two-letter state (explains the fallback in non-disclosure states)")
    ap.add_argument("--price-only", action="store_true", help="sales file has no buyer names (sold comps / listings): build from land prices in general")
    ap.add_argument("--known-developers", help="txt/CSV of builder and developer names (and their LLCs) to always count")
    ap.add_argument("--approved-buyers", help="buyers_review.csv after you marked approve Y / N")
    ap.add_argument("--sms", action="store_true", help="build sms.csv (needs --consent-file)")
    ap.add_argument("--consent-file", help="CSV: phone, consent_date, consent_source (people who gave YOU texting consent)")
    ap.add_argument("--dnc-scrubbed", help="CSV from your own National + state DNC scrub: phone, dnc (Y/N), scrub_date")
    ap.add_argument("--dnc-scrub-date", help="YYYY-MM-DD of that scrub, for rows without a scrub_date")
    ap.add_argument("--call-review", help="your call review file (default: <output>/state/call_review.csv if it exists)")
    ap.add_argument("--suppress", action="append", default=[], help="do-not-contact CSV: phone, address, owner, date, channel (kept across runs)")
    ap.add_argument("--suppress-dir", help="drop folder read on every run (default: ./suppress, else the kit's suppress/ folder)")
    ap.add_argument("--dnc-lists", default="", help='lists your DNC scrub covered, for rows without lists_checked, e.g. "federal; state; internal"')
    ap.add_argument("--stop-replies", help="CSV of numbers that replied STOP; added to the suppression list")
    ap.add_argument("--sms-sender", help="business name your texting consent was given to (default: --company)")
    ap.add_argument("--imagery-url", help="county orthoimagery ArcGIS ImageServer/MapServer URL (default NAIP)")
    ap.add_argument("--geometry", help="parcel boundaries JSON (made automatically with --parcel-layer)")
    ap.add_argument("--use-case", default="single_family")
    ap.add_argument("--market", default="")
    ap.add_argument("--infra"); ap.add_argument("--comps")
    ap.add_argument("--config", help="city config for split/ADU signals (config/my-market.yaml)")
    ap.add_argument("--months", type=int, default=36); ap.add_argument("--as-of")
    ap.add_argument("--top", type=int, default=10, help="due-diligence reports and satellite images for the top N")
    ap.add_argument("--satellite", choices=["naip", "county", "links", "skip"], default="naip",
                    help="naip = USDA NAIP aerials (public domain, default); county = --imagery-url; links = view links only")
    ap.add_argument("--tiers", default="A,B")
    ap.add_argument("--skiptrace-results", help="your skip-trace provider's results CSV (step 4 import)")
    ap.add_argument("--your-name", default="[YOUR NAME]"); ap.add_argument("--company", default="[YOUR COMPANY]")
    ap.add_argument("--phone", default="[YOUR PHONE]"); ap.add_argument("--buyer", default="home builders and developers")
    ap.add_argument("--output-dir", help="default out/ (out_demo/ with --demo)")
    ap.add_argument("--enrich-top", type=int, default=60,
                    help="after the first scoring, look up FEMA flood, NWI wetlands and USGS slope for the top N parcels and score again "
                         "(default 60; 0 = skip; never in the demo)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)

    if a.demo:
        a.parcels = a.parcels or os.path.join(S, "sample_parcels.csv")
        a.sales = a.sales or os.path.join(S, "sample_developer_sales.csv")
        a.infra = a.infra or os.path.join(S, "sample_infrastructure.csv")
        a.config = a.config or os.path.join(ROOT, "config", "examples", "sample-county-oh-land.yaml")
        a.skiptrace_results = a.skiptrace_results or os.path.join(S, "sample_skiptrace_results.csv")
        a.market = a.market or "Sample County, OH (made-up demo data)"
        a.as_of = a.as_of or "2026-11-01"
        a.known_developers = a.known_developers or os.path.join(S, "known_developers.example.txt")
        if not a.dnc_scrubbed:
            # made-up scrub result dated today, so the demo shows the call-list routing
            a.dnc_scrubbed = os.path.join(S, "sample_dnc_scrub.csv")
            a.dnc_scrub_date = a.dnc_scrub_date or __import__("datetime").date.today().isoformat()
    out = a.output_dir or ("out_demo" if a.demo else "out")
    os.makedirs(out, exist_ok=True)
    # the demo never reads or writes the weekly state (seen owners, suppression master, call reviews)
    state_dir = None if a.demo else os.path.join(out, "state")
    master = os.path.join(state_dir, "suppression.csv") if state_dir else None
    # the suppress/ drop folder: every CSV in it is applied on every run (not in the demo)
    drop_dir = None if a.demo else (a.suppress_dir or next((p for p in (os.path.join(os.getcwd(), "suppress"), os.path.join(ROOT, "suppress"))
                                                              if os.path.isdir(p)), None))
    drop_files, drop_age, drop_info = build_marketing_lists.suppression.drop_folder(drop_dir)
    a.suppress = list(a.suppress) + drop_files
    sup_rows = build_marketing_lists.suppression.merge(master, a.suppress, a.stop_replies, persist=bool(master))
    sup_file = master
    if not master and sup_rows:
        sup_file = os.path.join(out, "suppression_this_run.csv")
        build_marketing_lists.suppression.write_rows(sup_file, sup_rows, build_marketing_lists.suppression.FIELDS)
    if a.parcel_layer:
        # fresh pull from the county (needs internet; fails in sandboxes that block outside sites)
        a.parcels = os.path.join(out, "parcels_fetched.csv")
        argv0 = ["--layer-url", a.parcel_layer, "--min-acres", str(a.min_acres), "--output", a.parcels]
        if a.bbox:
            argv0 += ["--bbox", a.bbox]
        if a.parcel_where:
            argv0 += ["--where", a.parcel_where]
        step("0. Pull parcels from the county layer", fetch_arcgis_parcels.main, argv0, not a.verbose)
        a.geometry = a.geometry or os.path.join(out, "parcels_fetched.geometry.json")
        if a.sales_where and not a.sales:
            a.sales = os.path.join(out, "sales_fetched.csv")
            argv0s = ["--layer-url", a.parcel_layer, "--where", a.sales_where, "--output", a.sales] + (["--bbox", a.sales_bbox] if a.sales_bbox else [])
            step("0b. Pull recent sales from the county layer", fetch_arcgis_parcels.main, argv0s, not a.verbose)
    if not a.parcels:
        raise SystemExit("Give --parcels <file>, --parcel-layer <url>, or --demo.")
    q = not a.verbose
    notes = []

    # 1. buy box
    box_path = a.buy_box
    if a.sales and not box_path:
        argv1 = ["--sales", a.sales, "--market", a.market, "--use-case", a.use_case, "--months", str(a.months), "--output-dir", out] + (["--parcels", a.parcels] if a.parcels else [])
        for flag, v in (("--as-of", a.as_of), ("--state", a.state), ("--known-developers", a.known_developers),
                        ("--approved-buyers", a.approved_buyers)):
            if v:
                argv1 += [flag, v]
        if a.price_only:
            argv1.append("--price-only")
        box, _ = step("1. Buy box from " + ("land sale prices (price-only)" if a.price_only else "developer purchases"), build_buy_box.main, argv1, q)
        box_path = os.path.join(out, "buy_box.json")
        act = box["developer_activity"]
        print(f"   {act['deeds_used']} deeds used, confidence {act['confidence'].upper()}; built from data: {box['built_from_data']}; "
              f"{act['premium_deeds']} {build_buy_box.PREMIUM_LABEL}. See buy_box_summary.md and buyers_review.csv")
        if act.get("price_only"):
            notes.append("Price-only buy box (no buyer names): it shows land prices in general, not what developers paid.")
        else:
            notes.append("Check buyers_review.csv: mark approve Y/N on the buyers and re-run with --approved-buyers buyers_review.csv.")
        if not box["built_from_data"]:
            notes.append("Too few developer sales to set the buy box from data; the preset was used. See buy_box_summary.md.")
    elif not box_path:
        print("\n== 1. Buy box: no --sales file, using the preset for " + a.use_case)
        notes.append("No sales file, so the buy box is the preset, not real developer activity. Add --sales to fix that.")

    # 2. score
    argv2 = ["--input", a.parcels, "--use-case", a.use_case, "--market", a.market, "--top", str(a.top), "--output-dir", out]
    for flag, v in (("--buy-box", box_path), ("--infra", a.infra), ("--comps", a.comps)):
        if v:
            argv2 += [flag, v]
    for c in a.county_code:
        argv2 += ["--county-code", c]
    summ, _ = step("2. Score every parcel against the buy box", score_parcels.main, argv2, q)
    ranked = os.path.join(out, "parcels_ranked.csv")
    enrich_info = None
    parcels_orig = a.parcels
    if a.enrich_top and not a.demo:
        # Unknown factors are left out of the score, so an unchecked parcel can climb after the rescore.
        # Repeat: look up every target that has not been looked up yet, rescore, until the post-rescore
        # tier A + top max(10, --top) are all checked (score_parcels also keeps unchecked parcels out of tier A).
        checked, rounds = set(), 0
        try:
            todo = None
            while rounds < ENRICH_MAX_ROUNDS:
                if todo is None:
                    info = enrich_shortlist(a.parcels, ranked, a.enrich_top, out, q)
                else:
                    info = enrich_shortlist(a.parcels, ranked, 0, out, q, apns=todo,
                                            label=f"2a. Round {rounds + 1}: lookups for {len(todo)} parcel(s) that rose into tier A / the top {max(10, a.top)} unchecked")
                if not info:
                    break
                rounds += 1
                checked |= set(info["apns"])
                enrich_info = dict(info, checked=len(checked), rounds=rounds,
                                   ok=(enrich_info or {}).get("ok", 0) + info.get("ok", 0) if enrich_info else info.get("ok", 0))
                a.parcels = info["output"]
                argv2[argv2.index("--input") + 1] = a.parcels
                summ, _ = step(f"2a. Score again with flood / wetlands / slope ({len(checked)} parcels looked up)", score_parcels.main, argv2, q)
                todo = [x for x in research_targets(ranked, a.top) if x not in checked]
                if not todo:
                    break
            left = [x for x in research_targets(ranked, a.top) if x not in checked]
            enrich_info = dict(enrich_info or {}, targets_unchecked=left)
            if left:
                notes.append(f"{len(left)} parcel(s) in tier A / the top {max(10, a.top)} were not looked up after {rounds} rounds "
                             "(they are held out of tier A). Re-run with a larger --enrich-top.")
        except Exception as e:  # network blocked or a source down: keep the scoring so far
            print(f"   Shortlist lookups: {SOURCE_UNAVAILABLE} ({friendly_error(e)})")
            notes.append("Flood / wetlands / slope lookups for the shortlist failed this run (" + friendly_error(e) + "). Re-run later. "
                         "Parcels without them are held out of tier A.")
    write_buyer_package(ranked, os.path.join(out, "buyer_package.csv"))
    print(f"   {summ['parcels_in_file']} parcels scored, {summ['eligible']} passed the buy box, tiers {summ['tier_counts']}")
    if summ.get("next_step_hint"):
        notes.append(summ["next_step_hint"])
    if a.config:
        step("2b. Lot split / ADU signals", add_split_adu_signals.main, ["--parcels", a.parcels, "--ranked", ranked, "--config", a.config], q)
        n = sum(1 for r in read_rows(ranked) if r.get("split_adu_signals"))
        print(f"   {n} parcels with a split / ADU / middle-housing signal")
    else:
        notes.append("No city config given, so lot-split / ADU signals were skipped. Say 'set this up for <city, state>'.")

    # 3. satellite
    if a.satellite != "skip":
        argv3 = ["--ranked", ranked, "--top", str(a.top)]
        if a.geometry and os.path.exists(a.geometry):
            argv3 += ["--geometry", a.geometry]
        if a.satellite == "links":
            argv3.append("--offline")
        elif a.satellite == "county":
            if not a.imagery_url:
                raise SystemExit("--satellite county needs --imagery-url <your county's ImageServer/MapServer URL>")
            argv3 += ["--imagery-url", a.imagery_url]
        try:
            rev, _ = step("3. Aerial images of the top parcels", satellite_check.main, argv3, q)
        except Exception as e:
            print(f"   Aerial images: {SOURCE_UNAVAILABLE} ({friendly_error(e)})")
            notes.append("Aerial images could not be made this run (" + friendly_error(e) + "). Re-run later or open the map links.")
            rev = []
        got = sum(1 for r in rev if r.get("image_file"))
        drawn = sum(1 for r in rev if r.get("image_file") and r.get("boundary") == "parcel boundary drawn")
        print(f"   {len(rev)} parcels, {got} images saved ({drawn} with the parcel boundary). Review sheet: satellite/satellite_review.csv")
        if a.satellite != "links" and got < len(rev):
            notes.append("Some aerial images did not download (network). Open the view links in satellite_review.csv instead.")

    # 4. owners / skip trace
    up, _ = step("4. Owners + skip-trace file", skip_trace.main, ["export", "--ranked", ranked, "--tiers", a.tiers] +
                 (["--suppress", sup_file] if sup_file else []), q)
    print(f"   {len(up[0])} people in skiptrace/skiptrace_upload.csv, {len(up[1])} companies/trusts in skiptrace/entities_to_research.csv")
    traced_path = None
    if a.skiptrace_results:
        tr, _ = step("4b. Import skip-trace results", skip_trace.main, ["import", "--ranked", ranked, "--results", a.skiptrace_results], q)
        traced_path = os.path.join(out, "skiptrace", "owners_traced.csv")
        print(f"   {len(tr)} owners matched, {sum(1 for t in tr if t.get('phone1'))} with a phone. See skiptrace/skiptrace_report.txt")
    else:
        notes.append("Phones and emails: nobody is traced yet. Upload skiptrace/skiptrace_upload_<provider>.csv to your skip-trace provider, "
                     "then re-run with --skiptrace-results <their file>. " + SKIPTRACE_LINE)

    # 5. marketing lists
    argv5 = ["--ranked", ranked, "--tiers", a.tiers, "--jurisdiction", a.market or ""]
    hold_why = "" if a.demo else build_marketing_lists.suppression.freshness_reason(drop_age, drop_info)
    stale = bool(hold_why)
    if stale:
        argv5 += ["--hold-phone-sms", hold_why]
    if state_dir:
        argv5 += ["--state-file", os.path.join(state_dir, "seen_owners.json"), "--suppression-master", master]
    elif sup_file:
        argv5 += ["--suppress", sup_file]
    review = a.call_review or (os.path.join(state_dir, "call_review.csv") if state_dir else None)
    if review and os.path.exists(review):
        argv5 += ["--call-review", review]
    if a.dnc_scrub_date:
        argv5 += ["--dnc-scrub-date", a.dnc_scrub_date]
    if a.dnc_lists:
        argv5 += ["--dnc-lists", a.dnc_lists]
    argv5 += ["--sms-sender", a.sms_sender or (a.company if a.company != "[YOUR COMPANY]" else "")]
    if traced_path:
        argv5 += ["--traced", traced_path]
    for flag, v in (("--consent-file", a.consent_file), ("--dnc-scrubbed", a.dnc_scrubbed)):
        if v:
            argv5 += [flag, v]
    if a.sms:
        argv5.append("--sms")
    sat = os.path.join(out, "satellite", "satellite_review.csv")
    if os.path.exists(sat):
        argv5 += ["--satellite", sat]
    m, _ = step("5. Marketing-ready lists", build_marketing_lists.main, argv5, q)
    sms_txt = str(len(m["sms"])) if (a.sms and a.consent_file) else "not built (no --sms / consent file)"
    print(f"   mail {len(m['mail'])}, cold call {len(m['call'])} (needs scrub {len(m['needs_scrub'])}), sms {sms_txt}, "
          f"CRM import file {len(m['crm'])}, new since last run {len(m['new'])}, suppressed {len(m['suppressed'])}")

    # 6. campaign
    step("6. Campaign kit (nothing is sent)", campaign_kit.main, ["--marketing-dir", os.path.join(out, "marketing"), "--your-name", a.your_name,
                                                                  "--company", a.company, "--phone", a.phone, "--buyer", a.buyer] +
         (["--state", a.state] if a.state else []), q)
    print("   campaign/STATE_AND_JURISDICTION_CHECK.md (first), offer_letter.txt, estate_letter.txt, cold_call_opener.txt, sms_opener.txt, LOAD_INTO_YOUR_TOOLS.md")

    top = [r for r in read_rows(ranked) if r.get("rank")][:5]
    act = json.load(open(box_path)).get("developer_activity", {}) if box_path and os.path.exists(box_path) else {}
    infra_down = []
    if a.infra:
        side = os.path.splitext(a.infra)[0] + ".sources.json"
        if os.path.exists(side):
            infra_down = [k + (" (0 features returned: unknown)" if str(v).startswith("unknown") else "")
                          for k, v in json.load(open(side)).get("layers", {}).items()
                          if v == SOURCE_UNAVAILABLE or str(v).startswith("unknown")]
    unknown_all, unknown_some = summ.get("factors_unknown_everywhere", []), summ.get("factors_unknown_somewhere", [])
    box_json = json.load(open(box_path)) if box_path and os.path.exists(box_path) else {}
    zoning_w = (box_json.get("weights") or {}).get("zoning")
    if zoning_w is not None and not zoning_w and "Zoning / use" not in unknown_all:
        unknown_all = list(unknown_all) + ["Zoning / use (not scored: weight 0 in this buy box)"]
    lic_flags = []
    for lic in (os.path.join(out, "sources", "county_layer_license.txt"),
                os.path.join(os.path.dirname(os.path.abspath(parcels_orig or ".")), "sources", "county_layer_license.txt")):
        if os.path.exists(lic):
            lic_flags += [ln.strip() for ln in open(lic) if ln.startswith("FLAGGED")]
    lic_flags = list(dict.fromkeys(lic_flags))
    low_box = (not act) or act.get("confidence") == "low" or act.get("price_only")
    L = ["> **" + score_parcels.DISCLAIMER + "**", "",
         "> **" + build_marketing_lists.PREPARED_NOT_APPROVED + "**", "",
         "> **" + build_marketing_lists.VOICE_LINE + "**", "",
         f"# Start here - {a.market or 'your market'}", "",
         f"**Last run: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}** (run it weekly by saying \"refresh my county\"; "
         "automatic scheduling needs separate setup; new_owners.csv shows who is new)", ""]
    if unknown_all or unknown_some or infra_down:
        L += ["> **UNKNOWN FACTORS IN THIS RUN.** " +
              (f"No data at all for: {', '.join(unknown_all)}. " if unknown_all else "") +
              (f"Missing for some parcels: {', '.join(unknown_some)}. " if unknown_some else "") +
              (f"Map sources that were unavailable: {', '.join(infra_down)}. " if infra_down else "") +
              "Unknown factors are left out of the score (not counted as good or bad), so rankings lean on what is known. "
              "Lookups are automatic when public sources are available; re-run later or add the data.", ""]
    if stale:
        L += ["> **SUPPRESSION LIST MAY BE OUT OF DATE.** " +
              hold_why[0].upper() + hold_why[1:] + ". Freshness uses the date each export was generated (from the file, or "
              "entered with scripts/suppression.py import), never the date you copied it. " +
              build_marketing_lists.OPT_OUT_SENTENCE + " " + build_marketing_lists.MANUAL_SENTENCE +
              " Save them in suppress/ and re-run. **Until then every phone and text output is held:** no cold_call.csv, "
              "no sms.csv, and phones are blank in crm_import.csv (see marketing/PHONE_AND_SMS_HELD.txt).", ""]
    if lic_flags:
        L += ["> **CHECK THE COUNTY DATA LICENCE.** The parcel layer's terms mention: " + "; ".join(x.replace("FLAGGED: ", "") for x in lic_flags)[:400] +
              ". Read sources/county_layer_license.txt before you use or share the data commercially.", ""]
    sat_summary = os.path.join(out, "satellite", "imagery_summary.txt")
    if a.satellite != "skip" and os.path.exists(sat_summary):
        L += ["> **AERIAL IMAGERY.** " + " ".join(ln.strip() for ln in open(sat_summary) if ln.strip()), ""]
    L += [f"- Parcels scored: {summ['parcels_in_file']}; passed the buy box: {summ['eligible']}; tiers: {json.dumps(summ['tier_counts'])}",
          (f"- Buy box: {act.get('deeds_used')} deeds, confidence {str(act.get('confidence', '')).upper()}" +
           (" (price-only: land prices in general, not developer buys)" if act.get("price_only") else "") +
           (" - LOW: a rough hint only, see buy_box_summary.md" if act.get("confidence") == "low" else "") if act else "- Buy box: preset (no sales file)"),
          f"- Owners in the CRM import file: {len(m['crm'])} (mail {len(m['mail'])}, call {len(m['call'])} scrubbed but still needs_review + "
          f"{len(m['needs_scrub'])} needing your DNC scrub, text {sms_txt}); new since last run: {len(m['new'])}",
          f"- Suppression list: {m['suppression_size']} entries; removed this run: {len(m['suppressed'])}"
          + (" (demo: nothing saved)" if a.demo else " (kept in state/suppression.csv)"),
          "- Owner signals your data had: " + (", ".join(summ.get("owner_signals_in_data", [])) or "none") +
          ". Not in your data, so not checked: " + (", ".join(summ.get("owner_signals_not_in_data", [])) or "none") + ".",
          f"- Owners excluded by type (builder, HOA, utility, church...): {summ.get('excluded_owners', 0)} - see excluded_owners.csv",
          (f"- Flood / wetlands / slope looked up for the top {a.enrich_top} parcels" +
           (f", plus {enrich_info['checked'] - min(a.enrich_top, enrich_info['checked'])} that rose into tier A / the top {max(10, a.top)} after rescoring"
            if enrich_info.get("rounds", 1) > 1 else "") +
           f" ({enrich_info['checked']} looked up in {enrich_info.get('rounds', 1)} round(s), {enrich_info.get('ok', 0)} fully checked) and scored again. " +
           (f"Every tier-A and top-{max(10, a.top)} parcel was looked up." if not enrich_info.get("targets_unchecked") else
            f"{len(enrich_info['targets_unchecked'])} tier-A / top-{max(10, a.top)} parcel(s) were not looked up (held out of tier A).")
           if enrich_info else ("- Flood / wetlands / slope: not looked up this run (demo, --enrich-top 0, or the lookups failed). "
                                "Tier A needs all three, so parcels without them are held in tier B.")),
          "- Tier A (\"A - research first\") needs FEMA flood, NWI wetlands and USGS slope values; a parcel missing any of them is held in "
          "tier B with a \"held out of tier A\" flag. Tier A means research first, not call first.",
          (f"- Ties: {summ.get('ties_in_top')} of the top {len(summ.get('top', []))} share a priority with another parcel. Order among ties: "
           "more factors with data, land score, owner signals, acreage fit, then APN (tiebreak column)." if summ.get("ties_in_top") else
           "- No ties in the top parcels."),
          ""]
    if box_json.get("criteria"):
        crit = box_json["criteria"]
        L += ["## Buy box criteria (" + str(act.get("confidence", "preset")).upper() + " confidence)", "",
              "| Criterion | Value | Source | Supporting purchases |", "|---|---|---|---|"] + [
              f"| {c['criterion']} | {c['value']} | {c['source']} | {c['supporting_purchases']} |" for c in crit] + ["", ""]
    sig_tab = summ.get("motivation_signal_table") or []
    if sig_tab:
        L += ["## Owner motivation signals (what was collected, from where, and what happens when it is missing)", "",
              "| Signal | Collected this run | Source | If not available |", "|---|---|---|---|"] + [
              f"| {g['signal']} | {g['collected_this_run']} | {g['source']} | {g['when_not_available']} |" for g in sig_tab] + [
              "", "Full table: motivation_signals.csv.", ""]
    L += [("## Top 5 (best fits to the buy box; the buy box is LOW confidence, so treat this as a rough sort)" if low_box
           else "## Top 5 (match recent developer purchase patterns and the buy box)"), ""]
    for r in top:
        L.append(f"{int(float(r['rank']))}. {r.get('address') or r.get('apn')} - {r['acres']} ac, {r['tier']}, priority {r['priority']}. "
                 f"Owner: {r.get('owner') or 'unknown'}. {(str(r.get('motivation_signals') or '').strip() if str(r.get('motivation_signals') or '').strip().lower() != 'nan' else '') or 'No owner signal present among the signals checked (that is not the same as unmotivated).'}"
                 + (f" Signals {r['signals_not_checked']}." if str(r.get('signals_not_checked') or '').strip() not in ('', 'nan') else ""))
        if r.get("research_next"):
            L.append(f"   Research next: {r['research_next']}")
        if r.get("tiebreak"):
            L.append(f"   Tie: {r['tiebreak']}")
    L += ["", "## Files", "- buy_box_summary.md: recent developer purchase patterns, evidence counts, what came from the preset, and where buyers " + build_buy_box.PREMIUM_LABEL,
          "- buyers_review.csv: every buyer and why it was or wasn't counted as a developer (mark approve Y/N)",
          "- index.html and reports/: due-diligence report per top parcel", "- development_sites.xlsx: everything in one workbook (Read me tab first)",
          "- excluded_owners.csv: owners left out by type, with the word that matched",
          "- buyer_package.csv: parcel facts and scores for a buyer, without any owner name, mailing address, phone or email",
          "- satellite/: aerial images with the boundary + satellite_review.csv (fill in the findings and verdicts); satellite_errors.log if any failed",
          "- skiptrace/: upload files per provider (generic format, check your provider's template), companies to research",
          "- motivation_signals.csv: which owner signals were collected, their source, and what happens when one is missing",
          "- satellite/imagery_summary.txt: imagery year and age, parcels covered, parcels with no usable imagery",
          "- marketing/: mail.csv, cold_call.csv (scrubbed in the last 31 days, needs_review), cold_call_NEEDS_SCRUB.csv (blocked), "
          "crm_import.csv (CRM import file; phones only when scrubbed, see phone_status), suppressed_this_run.csv, COMPLIANCE.md" +
          (", sms.csv, consent_log.csv" if m["sms"] else "") + (". PHONE AND TEXT OUTPUTS HELD this run (PHONE_AND_SMS_HELD.txt)" if m.get("held") else ""),
          "- campaign/: offer + estate letters, call opener, texts, LOAD_INTO_YOUR_TOOLS.md", "", "## Still to do"]
    L += ["- FIRST: campaign/STATE_AND_JURISDICTION_CHECK.md (state wholesaling and jurisdiction). Consent, 10DLC registration, "
          "DNC scrub and calling hours are separate checks in campaign/campaign_checklist.md.",
          "- Estates: never imply an heir can sell. Check the probate case, the personal representative's letters, court approval and title.",
          "- " + build_marketing_lists.DATA_LICENSE_LINE]
    L += [f"- {n}" for n in notes] + ["- Review the satellite images and fill satellite_review.csv, then re-run step 5.",
                                      "- Check zoning on the top parcels with the city.",
                                      "- Read marketing/COMPLIANCE.md before you call or text (DNC scrub, consent, registration, state wholesaling rules).",
                                      "- Nothing has been mailed, dialed or texted. You start the campaign from your own tools.",
                                      "- " + SKIPTRACE_LINE,
                                      "- Privacy: " + PRIVACY_PARAGRAPH + " Don't upload these files to unrelated services; delete old exports "
                                      "with scripts/cleanup_exports.py."]
    if a.demo:
        L.insert(2, "DEMO: every parcel, owner, sale and phone number here is made up (555-01xx numbers, example.com emails). "
                    "The DNC scrub file (samples/sample_dnc_scrub.csv) is made up and dated today. "
                    "Demo files go to out_demo/ and never touch your real out/state/ files.\n")
    with open(os.path.join(out, "START_HERE.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"\nDone. Open {os.path.join(out, 'START_HERE.md')}")
    return {"summary": summ, "marketing": m, "notes": notes}


if __name__ == "__main__":
    main()
