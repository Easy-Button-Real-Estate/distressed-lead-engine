"""Offline tests for the land pipeline (steps 1-6). From this folder:

    python tests/test_pipeline.py

Uses only the made-up files in samples/. No network: satellite runs in links-only
mode or with a fake image fetcher, and the skip-trace API uses a fake urlopen.
"""
import csv, io, json, math, os, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import add_split_adu_signals, build_buy_box, build_marketing_lists, campaign_kit, run_pipeline, satellite_check, score_parcels, skip_trace  # noqa: E402

S = os.path.join(ROOT, "samples")
LAND_CFG = os.path.join(ROOT, "config", "examples", "sample-county-oh-land.yaml")
TMP = tempfile.mkdtemp(prefix="dof-test-")


def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def quiet(fn, argv):
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(argv)


def out(name):
    d = os.path.join(TMP, name)
    os.makedirs(d, exist_ok=True)
    return d


def test_buy_box_from_developer_sales():
    d = out("bb")
    box = quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01",
                                     "--market", "Sample County, OH", "--output-dir", d])
    act = box["developer_activity"]
    used = rows(os.path.join(d, "developer_sales.csv"))
    buyers = {u["buyer"] for u in used}
    assert act["deeds_used"] == 20, act["deeds_used"]  # 19 single deeds + one 3-parcel deed counted once
    assert act["multi_parcel_deeds_grouped"] == 1
    multi = [u for u in used if u["parcels"] == "3"]
    assert len(multi) == 1 and abs(float(multi[0]["acres"]) - 30.5) < 0.01 and float(multi[0]["sale_price"]) == 640000
    assert "OAKMONT 42 LLC" not in buyers  # plain LLC name: only counted from a known-developers list
    assert not buyers & {"SAMPLE FAMILY TRUST", "JOHN Q SAMPLE", "FIRST SAMPLE BANK"}, buyers  # not developers
    assert all(u["sale_date"] >= "2023-11-01" for u in used)  # 36-month default window; 2022 sale dropped
    assert all(float(u["sale_price"]) > 1000 for u in used)  # $10 deed dropped
    over = [u for u in used if u["paid_premium"] == "Y"]
    assert len(over) == 2 and {u["zip"] for u in over} == {"43001"}, over
    assert box["built_from_data"] is True
    assert box["developer_anchor"]["per_acre"] == act["price_per_acre"]["median"]
    assert box["acres"]["min"] < box["acres"]["ideal_min"] < box["acres"]["ideal_max"] < box["acres"]["max"]
    assert "pud planned unit development" in box["zoning_keywords"]
    assert not any("agricultural" in z for z in box["zoning_keywords"])  # rural buys = rezoning plays, not a match
    assert box["weights"] == {"activity": 15} and len(box["developer_points"]) == 20
    assert act["price_per_lot_median"]  # the 18-lot takedown gives a $/lot
    md = open(os.path.join(d, "buy_box_summary.md")).read()
    assert "paid a premium (25%+ over the size-band median)" in md and "overpa" not in md.lower()
    assert "**Confidence: MEDIUM**" in md and "Verify current zoning with the city" in md
    assert os.path.exists(os.path.join(d, "buyers_review.csv"))
    print("buy box ok")


def test_buy_box_too_few_sales_keeps_preset():
    d = out("bb_thin")
    box = quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01",
                                     "--min-sales", "50", "--output-dir", d])
    assert box["built_from_data"] is False
    assert "acres" not in box and "developer_anchor" not in box
    assert "Not enough deeds to set a buy box" in open(os.path.join(d, "buy_box_summary.md")).read()
    print("thin buy box ok")


def test_buy_box_known_developers_and_manual_approval():
    d = out("bb_known")
    box = quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01",
                                     "--known-developers", os.path.join(S, "known_developers.example.txt"), "--output-dir", d])
    assert box["developer_activity"]["deeds_used"] == 21
    assert "OAKMONT 42 LLC" in {u["buyer"] for u in rows(os.path.join(d, "developer_sales.csv"))}
    # the user says N to one builder and Y to a non-builder: their choice wins
    rev = rows(os.path.join(d, "buyers_review.csv"))
    for r in rev:
        r["approve"] = "N" if r["buyer"] == "SAMPLE HOMES LLC" else ("Y" if r["buyer"] == "JOHN Q SAMPLE" else "")
    appr = os.path.join(d, "approved.csv")
    build_buy_box.write_rows(appr, rev, list(rev[0].keys()))
    d2 = out("bb_approved")
    quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01",
                               "--known-developers", os.path.join(S, "known_developers.example.txt"), "--approved-buyers", appr, "--output-dir", d2])
    buyers = {u["buyer"] for u in rows(os.path.join(d2, "developer_sales.csv"))}
    assert "SAMPLE HOMES LLC" not in buyers and "JOHN Q SAMPLE" in buyers
    print("known developers + approvals ok")


def test_sales_with_an_existing_building_are_not_land_prices():
    d = out("bb_yb")
    src = rows(os.path.join(S, "sample_developer_sales.csv"))
    for r in src:
        r["year_built"] = ""
    src[0]["year_built"] = "1998"  # a house already stood when the builder bought it
    p = os.path.join(d, "sales.csv")
    build_buy_box.write_rows(p, src, list(src[0].keys()))
    box = quiet(build_buy_box.main, ["--sales", p, "--as-of", "2026-11-01", "--output-dir", d])
    assert box["developer_activity"]["deeds_used"] == 19
    assert "price included an existing building 1" in open(os.path.join(d, "buy_box_summary.md")).read()
    print("existing-building sales skipped ok")


def test_non_disclosure_state_price_only():
    d = out("bb_tx")
    tx = os.path.join(S, "sample_tx_sold_comps.csv")
    try:
        quiet(build_buy_box.main, ["--sales", tx, "--state", "TX", "--as-of", "2026-11-01", "--output-dir", d])
        assert False, "a file with no buyer names must not silently build a developer buy box"
    except SystemExit as e:
        assert "non-disclosure" in str(e) and "--price-only" in str(e)
    box = quiet(build_buy_box.main, ["--sales", tx, "--state", "TX", "--price-only", "--as-of", "2026-11-01", "--output-dir", d])
    act = box["developer_activity"]
    assert act["price_only"] is True and act["confidence"] == "low" and act["premium_deeds"] == 0
    md = open(os.path.join(d, "buy_box_summary.md")).read()
    assert "Price-only mode" in md and "not developer-specific" in md and "not from what developers paid" in md
    print("non-disclosure price-only ok")


def _scored(name):
    d = out(name)
    quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01", "--output-dir", d])
    summ = quiet(score_parcels.main, ["--input", os.path.join(S, "sample_parcels.csv"), "--infra", os.path.join(S, "sample_infrastructure.csv"),
                                      "--use-case", "single_family", "--buy-box", os.path.join(d, "buy_box.json"), "--output-dir", d])
    return d, summ


def test_score_uses_buy_box():
    d, summ = _scored("score")
    assert "developer" in summ["valuation_anchor"]["source"]
    assert "Near developer buys" in summ["weights"]
    r = rows(os.path.join(d, "parcels_ranked.csv"))
    elig = [x for x in r if x["rank"]]
    assert elig and all(x["activity_pts"] != "" for x in elig[:10])
    assert any("size" in x["excluded_because"] for x in r)  # buy-box acreage is enforced
    for col in ("mail_street", "mail_city", "mail_state", "mail_zip", "sig_out_of_state", "sig_out_of_county", "sig_tax_delinquent",
                "sig_long_hold", "owner_is_entity", "score_explained", "hard_gate_failures", "missing_data", "confidence_label",
                "factor_sources", "jurisdiction"):
        assert col in r[0], col
    assert "sig_absentee" not in r[0]
    top = elig[0]
    assert top["score_explained"].startswith("Land score") and "[" in top["score_explained"]  # every factor names its source
    assert "Water / sewer" in top["score_explained"]
    assert all(x["hard_gate_failures"] for x in r if not x["rank"])
    assert os.path.exists(os.path.join(d, "development_sites.xlsx")) and os.listdir(os.path.join(d, "reports"))
    print("score ok")


def _score_file(name, mutate):
    """Score a copy of the sample parcels after mutate(rows) changes it."""
    d = out(name)
    src = rows(os.path.join(S, "sample_parcels.csv"))
    mutate(src)
    p = os.path.join(d, "parcels.csv")
    keys = list(dict.fromkeys(k for r in src for k in r))
    skip_trace.write_rows(p, src, keys)
    quiet(score_parcels.main, ["--input", p, "--infra", os.path.join(S, "sample_infrastructure.csv"), "--top", "3", "--output-dir", d])
    return {x["apn"]: x for x in rows(os.path.join(d, "parcels_ranked.csv"))}


def test_owner_type_exclusions_farm_value_and_unmapped_flood():
    FARM = []

    def mutate(src):
        src[1]["owner_name"] = "MAPLE CREEK HOMEOWNERS ASSOCIATION"
        src[2]["owner_name"] = "NORFOLK SOUTHERN RAILWAY CO"
        src[3]["owner_name"] = "FIRST BAPTIST CHURCH"
        src[4]["owner_name"] = "SAMPLE ELECTRIC COOPERATIVE"
        src[5]["owner_name"] = "SAMPLE COUNTY CONSERVANCY"
        for r in src:
            r["cauv_value"] = ""
        farm = next(r for r in src[8:] if not r["asking_price"] and r["land_value"])
        farm["cauv_value"] = "Y"
        FARM.append(farm["apn"])
        src[7]["flood_pct"] = ""
        src[7]["fema_zone"] = "UNMAPPED"
    r = _score_file("excl", mutate)
    for apn, word in (("SAMPLE-002", "HOA"), ("SAMPLE-003", "railroad"), ("SAMPLE-004", "church"), ("SAMPLE-005", "utility"),
                      ("SAMPLE-006", "conservation")):
        assert not r[apn]["rank"] and word in r[apn]["hard_gate_failures"], (apn, r[apn]["hard_gate_failures"])
    assert "not scored as a bargain" in r[FARM[0]]["flags"], r[FARM[0]]["flags"]
    # people whose surname is a trigger word are not excluded (seen live: "TEMPLE, JOSEPH")
    assert score_parcels.owner_exclusion("TEMPLE, JOSEPH WOOD", "") is None
    assert score_parcels.owner_exclusion("PLEASANT GROVE BAPTIST CHURCH", "") == "church / religious"
    assert "unknown, not safe" in r["SAMPLE-008"]["flags"] and "flood" in r["SAMPLE-008"]["missing_data"].lower()
    print("owner exclusions + farm value + unmapped flood ok")


def test_equal_area_acreage():
    import fetch_arcgis_parcels as f
    # a 1 x 1 statute-mile square (640 acres) at 45N, built on the ground in metres
    lat0, lon0, m = 45.0, -93.0, 1609.344
    dlat = m / 111132.954  # metres per degree of latitude near 45N
    dlon = m / (111412.84 * math.cos(math.radians(lat0)))
    ring = [[lon0, lat0], [lon0, lat0 + dlat], [lon0 + dlon, lat0 + dlat], [lon0 + dlon, lat0], [lon0, lat0]]
    acres, lat, lon = f.geom_stats({"rings": [ring]})
    assert abs(acres - 640) / 640 < 0.005, acres
    # Web Mercator would say about 2x at 45N; make sure we are nowhere near that
    assert acres < 700
    print("equal-area acreage ok")


def test_split_signals_and_lot_yield():
    d, _ = _scored("split")
    ranked = os.path.join(d, "parcels_ranked.csv")
    quiet(add_split_adu_signals.main, ["--parcels", os.path.join(S, "sample_parcels.csv"), "--ranked", ranked, "--config", LAND_CFG])
    r = rows(ranked)
    with_yield = [x for x in r if x["est_lot_yield_net"]]
    assert with_yield and all(("r-1" in x["zoning_use"] or "pud" in x["zoning_use"]) for x in with_yield)
    assert all(int(x["est_lot_yield_net"]) < int(x["est_lot_yield_gross"]) for x in with_yield)
    assert "est_lot_yield" not in r[0]
    assert any("Lot split" in x["split_adu_signals"] for x in r)
    # blank config: no invented hits
    quiet(add_split_adu_signals.main, ["--parcels", os.path.join(S, "sample_parcels.csv"), "--ranked", ranked,
                                       "--config", os.path.join(ROOT, "config", "my-market.yaml")])
    r = rows(ranked)
    assert not any(x["split_adu_signals"] for x in r) and not any(x["est_lot_yield_net"] for x in r)
    print("split signals ok")


def _blank_jpeg(px=800):
    from PIL import Image
    buf = io.BytesIO()
    im = Image.new("RGB", (px, px), (40, 80, 40))
    for y in range(0, px, 8):  # stripes, so it is not a flat "no imagery" picture
        for x in range(px):
            im.putpixel((x, y), (90, 120, 90))
    im.save(buf, "JPEG")
    return buf.getvalue()


def test_satellite_links_only_no_google_download():
    d, _ = _scored("sat")
    ranked = os.path.join(d, "parcels_ranked.csv")
    rev = quiet(satellite_check.main, ["--ranked", ranked, "--top", "5", "--offline"])
    assert len(rev) >= 5 and [x["rank"] for x in rev][:5] == [1, 2, 3, 4, 5]
    tier_a = {int(float(r["rank"])) for r in rows(ranked) if r.get("rank") and r["tier"].startswith("A")}
    assert tier_a <= {x["rank"] for x in rev}, "every tier-A parcel gets an aerial check, even beyond --top"
    assert all(x["imagery_flag"] for x in rev)  # links-only: no image saved, so every row is flagged
    assert all("World_Imagery" in x["esri_view_link"] and "google.com/maps" in x["google_maps_link"] and not x["image_file"] for x in rev)
    src = open(os.path.join(ROOT, "scripts", "satellite_check.py")).read()
    assert "GOOGLE_MAPS_API_KEY" not in src and "staticmap" not in src  # no Google download path at all
    sheet = rows(os.path.join(d, "satellite", "satellite_review.csv"))
    assert {"vacant", "structures", "tree_cover", "road_or_driveway_touching", "water_or_wet_areas", "verdict"} <= set(sheet[0])
    assert "power_lines_visible" not in sheet[0] and "visible_access" not in sheet[0]
    # findings must carry a certainty label
    sheet[0]["vacant"] = "clearly visible: open field"
    sheet[1]["structures"] = "a barn"
    p = os.path.join(d, "filled.csv")
    satellite_check.write_rows(p, sheet, list(sheet[0].keys()))
    bad = satellite_check.check_review(p)
    assert len(bad) == 1 and bad[0][1] == "structures"
    print("satellite links ok")


def test_naip_image_with_parcel_boundary_drawn():
    from PIL import Image
    d, _ = _scored("naip")
    ranked = os.path.join(d, "parcels_ranked.csv")
    top = [x for x in rows(ranked) if x["rank"]][:2]
    lat, lon = float(top[0]["lat"]), float(top[0]["lon"])
    h = 0.002
    ring = [[lon - h, lat - h], [lon - h, lat + h], [lon + h, lat + h], [lon + h, lat - h], [lon - h, lat - h]]
    geo = os.path.join(d, "parcels.geometry.json")
    json.dump({"parcels": [{"apn": top[0]["apn"], "lat": lat, "lon": lon, "rings": [ring]}]}, open(geo, "w"))
    urls = []

    def fake(url):
        urls.append(url)
        if "/identify?" in url:  # capture-year lookup in the NAIP catalog
            return json.dumps({"catalogItems": {"features": [{"attributes": {"Year": 2022, "acquisition_date": 1664236800000}},
                                                             {"attributes": {"Year": 2020, "acquisition_date": 1590000000000}}]}}).encode()
        return _blank_jpeg()
    rev = satellite_check.main(["--ranked", ranked, "--top", "2", "--geometry", geo, "--output-dir", os.path.join(d, "sat")], fetcher=fake)
    assert all("USGSNAIPImagery/ImageServer/exportImage" in u for u in urls if "/identify?" not in u)
    assert rev[0]["capture_year"].startswith("2022") and rev[0]["status"] == "to review" and rev[0]["next_action"]
    assert list(rows(os.path.join(d, "sat", "satellite_review.csv"))[0].keys())[:10] == ["rank", "apn", "address", "image_file", "capture_year",
                                                                                         "imagery_age", "imagery_flag", "status", "verdict", "next_action"]
    assert rev[0]["boundary"] == "parcel boundary drawn" and rev[1]["boundary"].startswith("approximate")
    assert "NAIP" in rev[0]["image_source"]
    # the yellow outline is where the boundary is: check a pixel on the left edge of the ring
    ext = satellite_check.extent_for(lat, lon, None, [ring])
    im = Image.open(rev[0]["image_file"]).convert("RGB")
    x, y = satellite_check.to_px(lat, lon - h, ext, im.size)
    pr, pg, pb = im.getpixel((int(round(x)), int(round(y))))
    assert pr > 180 and pg > 160 and pb < 120, (pr, pg, pb)
    cx, cy = satellite_check.to_px(lat, lon, ext, im.size)
    assert im.getpixel((int(cx), int(cy)))[2] < 120 and im.getpixel((int(cx), int(cy)))[0] < 120  # inside stays untouched
    # a county imagery URL is used instead of NAIP when given
    urls.clear()
    satellite_check.main(["--ranked", ranked, "--top", "1", "--imagery-url", "https://gis.example.gov/arcgis/rest/services/Ortho2025/ImageServer",
                          "--output-dir", os.path.join(d, "sat2")], fetcher=fake)
    assert urls and urls[0].startswith("https://gis.example.gov/arcgis/rest/services/Ortho2025/ImageServer/exportImage")
    print("NAIP + boundary ok")


def test_skip_trace_round_trip_and_api_dry_run():
    d, _ = _scored("skip")
    ranked = os.path.join(d, "parcels_ranked.csv")
    up, ent = quiet(skip_trace.main, ["export", "--ranked", ranked])
    assert up and ent
    assert all(u["Mailing Address"] and u["Owner Key"] for u in up)
    assert not any(skip_trace.split_owner(u["Owner Full Name"])["entity"] for u in up)  # companies go to research list
    hdr = rows(os.path.join(d, "skiptrace", "skiptrace_upload.csv"))[0].keys()
    assert {"First Name", "Last Name", "Mailing Address", "Mailing City", "Mailing State", "Mailing Zip", "Property Address"} <= set(hdr)
    for prov in ("generic", "batchskiptracing", "propstream", "dealmachine", "reisift"):
        pr = rows(os.path.join(d, "skiptrace", f"skiptrace_upload_{prov}.csv"))
        assert list(pr[0].keys()) == skip_trace.TEMPLATES[prov] and len(pr) == len(up), prov
    assert rows(os.path.join(d, "skiptrace", "skiptrace_upload_propstream.csv"))[0]["Owner First Name"] == up[0]["First Name"]
    log = json.load(open(os.path.join(d, "skiptrace", "export_log.json")))
    assert "NOT traced" in log["status"] and len(log["owner_keys"]) == len(up)
    tr = quiet(skip_trace.main, ["import", "--ranked", ranked, "--results", os.path.join(S, "sample_skiptrace_results.csv")])
    assert tr and any(t.get("phone1") for t in tr)
    assert all(len(t["phone1"]) == 10 for t in tr if t.get("phone1"))
    assert {t["phone1_type"] for t in tr if t.get("phone1")} <= {"mobile", "landline", "voip", "unknown"}
    rep = open(os.path.join(d, "skiptrace", "skiptrace_report.txt")).read()
    assert "match rate" in rep and "not a scrub" in rep
    assert os.path.exists(os.path.join(d, "skiptrace", "failed_records.csv"))
    assert skip_trace.phone_type("Wireless") == "mobile" and skip_trace.phone_type("Residential") == "landline" and skip_trace.phone_type("VOIP") == "voip"
    # a provider file with different headers and no DNC column, matched by mailing address
    alt = os.path.join(d, "alt_results.csv")
    u0 = up[0]
    with open(alt, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Mail Address", "Mail Zip", "Mobile 1", "Landline 1", "Email Address"])
        w.writerow([u0["Mailing Address"], u0["Mailing Zip"], "614.555.0199", "1-614-555-0198", "x@example.com"])
    tr2 = quiet(skip_trace.main, ["import", "--ranked", ranked, "--results", alt, "--output", os.path.join(d, "alt_traced.csv")])
    assert len(tr2) == 1 and tr2[0]["phone1"] == "6145550199" and tr2[0]["phone1_type"] == "mobile" and tr2[0]["phone1_dnc"] == "unknown"
    try:
        quiet(skip_trace.main, ["api", "--ranked", ranked, "--dry-run"])
        raise AssertionError("BatchData must refuse to run without --price-per-record")
    except SystemExit as e:
        assert "--price-per-record" in str(e)
    assert quiet(skip_trace.main, ["api", "--ranked", ranked, "--dry-run", "--price-per-record", "0.2"]) == []
    assert "GENERIC FORMAT, CHECK YOUR PROVIDER'S TEMPLATE" in open(os.path.join(d, "skiptrace", "README_UPLOAD.txt")).read()
    print("skip trace ok")


def test_batchdata_api_needs_confirm_and_is_capped():
    d, _ = _scored("api")
    ranked = os.path.join(d, "parcels_ranked.csv")
    sent = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None, **kw):
        body = json.loads(req.data.decode())
        sent.append(len(body["requests"]))
        return Resp(json.dumps({"results": {"persons": []}}).encode())
    old_key, old_open = os.environ.get("BATCHDATA_API_KEY"), skip_trace.urllib.request.urlopen
    os.environ["BATCHDATA_API_KEY"] = "test-not-a-real-key"
    skip_trace.urllib.request.urlopen = fake_urlopen
    try:
        assert quiet(skip_trace.main, ["api", "--ranked", ranked, "--price-per-record", "0.25"]) == []
        assert sent == [], "nothing may be sent without --confirm"
        prev = open(os.path.join(d, "skiptrace", "api_cost_preview.txt")).read()
        assert "Estimated cost: $" in prev and "--confirm" in prev
        quiet(skip_trace.main, ["api", "--ranked", ranked, "--max", "2", "--confirm", "--price-per-record", "0.25"])
        assert sent and sum(sent) <= 2, sent
        sent.clear()
        quiet(skip_trace.main, ["api", "--ranked", ranked, "--max", "100000", "--price-per-record", "0.1"])
        assert "cap 500" in open(os.path.join(d, "skiptrace", "api_cost_preview.txt")).read() and sent == []
    finally:
        skip_trace.urllib.request.urlopen = old_open
        if old_key is None:
            os.environ.pop("BATCHDATA_API_KEY", None)
        else:
            os.environ["BATCHDATA_API_KEY"] = old_key
    print("api safety ok")


def test_marketing_lists_rules():
    d, _ = _scored("mkt")
    ranked = os.path.join(d, "parcels_ranked.csv")
    quiet(skip_trace.main, ["export", "--ranked", ranked])
    quiet(skip_trace.main, ["import", "--ranked", ranked, "--results", os.path.join(S, "sample_skiptrace_results.csv")])
    traced = os.path.join(d, "skiptrace", "owners_traced.csv")
    t = rows(traced)
    # make one owner a litigator and give another only a DNC phone
    t[0]["litigator"] = "Y"
    t[1].update(phone1_dnc="Y", phone2="", phone2_dnc="", phone2_type="")
    skip_trace.write_rows(traced, t, list(t[0].keys()))
    # drop the #1 parcel in satellite review
    r = rows(ranked)
    top_apn = [x for x in r if x["rank"]][0]["apn"]
    sat = os.path.join(d, "sat.csv")
    skip_trace.write_rows(sat, [{"apn": top_apn, "verdict": "drop", "notes": "houses on it"}])
    state = os.path.join(d, "state.json")
    m = quiet(build_marketing_lists.main, ["--ranked", ranked, "--traced", traced, "--satellite", sat, "--state-file", state])
    keys = {x["owner_key"] for x in m["crm"]}
    assert all(top_apn not in x["apns"] for x in m["crm"]) and m["dropped"]
    lit = [x for x in m["crm"] if x["owner_key"] == t[0]["owner_key"]]
    assert not lit or (not lit[0]["phone1"] and lit[0]["litigator_removed"] == "Y")
    dnc = [x for x in m["call"] if x["owner_key"] == t[1]["owner_key"]]
    assert not dnc, "DNC-only owner must not be on the call list"
    assert m["sms"] == [] and not os.path.exists(os.path.join(d, "marketing", "sms.csv"))  # no --sms, no text list
    assert all(x["trace_status"] in ("hit", "no hit", "not traced") for x in m["crm"])
    assert all(x["dnc_status"] in ("provider flag only - still scrub National + state DNC", "unknown - scrub first") for x in m["call"])
    assert all(x["mail_street"] and x["mail_zip"] for x in m["mail"])
    assert len(m["new"]) == len(m["crm"])
    m2 = quiet(build_marketing_lists.main, ["--ranked", ranked, "--traced", traced, "--satellite", sat, "--state-file", state])
    assert len(m2["new"]) == 0 and {x["owner_key"] for x in m2["crm"]} == keys
    comp = open(os.path.join(d, "marketing", "COMPLIANCE.md")).read()
    assert "Do Not Call" in comp and "Ringless voicemail counts as a call" in comp and "is NOT a scrub" in comp
    for st in ("Pennsylvania", "Illinois", "Virginia", "Maryland", "Ohio", "Oklahoma", "Texas"):
        assert st in comp, st
    for t in ("Jurisdiction this run was built for:", "last verified by the kit author: 20", "Verify every point with counsel",
              "Telemarketer registration", "Optional assignment disclosure", "court-appointed personal", "Data licensing",
              "PropStream", "OpenStreetMap", "NAIP", "county_layer_license.txt"):
        assert t in comp, t
    assert "most apply to residential" not in comp.lower() and "written for residential" not in comp.lower()
    assert m["call"] == [] and m["needs_scrub"], "no DNC scrub given: nothing is callable"
    print("marketing lists ok")


def _traced(name):
    d, _ = _scored(name)
    ranked = os.path.join(d, "parcels_ranked.csv")
    quiet(skip_trace.main, ["export", "--ranked", ranked])
    quiet(skip_trace.main, ["import", "--ranked", ranked, "--results", os.path.join(S, "sample_skiptrace_results.csv")])
    return d, ranked, os.path.join(d, "skiptrace", "owners_traced.csv")


def test_sms_needs_flag_sender_and_confirmed_consent():
    d, ranked, traced = _traced("sms")
    consent = os.path.join(S, "sample_consent.csv")
    base = ["--ranked", ranked, "--traced", traced]
    m = quiet(build_marketing_lists.main, base + ["--consent-file", consent, "--sms-sender", "Sample Land Co"])
    assert m["sms"] == []  # consent file alone is not enough: --sms is the opt-in
    m = quiet(build_marketing_lists.main, base + ["--sms"])
    assert m["sms"] == [] and not os.path.exists(os.path.join(d, "marketing", "sms.csv"))  # --sms without consent
    m = quiet(build_marketing_lists.main, base + ["--sms", "--consent-file", consent])
    assert m["sms"] == [], "no --sms-sender: consent can't be matched to this sender"
    m = quiet(build_marketing_lists.main, base + ["--sms", "--consent-file", consent, "--sms-sender", "Sample Land Co"])
    assert len(m["sms"]) == 1 and m["sms"][0]["sms_phone"] == "6145550122", m["sms"]
    assert m["sms"][0]["sms_consent"].startswith("Y: 2026-10-02 / Sample Land Co / offers to buy their land / web form")
    assert m["sms"][0]["sms_review_status"] == "needs_review"
    assert any("6145550125" in r and "Some Other Company" in r for r in m["consent_rejected"])  # consent given to someone else
    assert rows(os.path.join(d, "marketing", "sms.csv"))[0]["sms_phone"] == "6145550122"
    # a row without confirmed = Y is not used
    c2 = os.path.join(d, "c2.csv")
    skip_trace.write_rows(c2, [{"phone": "6145550122", "consent_date": "2026-10-02", "consent_source": "form", "consented_to": "Sample Land Co",
                                "purpose": "land offers", "method": "web form", "consent_evidence": "form #9", "confirmed": ""}])
    m = quiet(build_marketing_lists.main, base + ["--sms", "--consent-file", c2, "--sms-sender", "Sample Land Co"])
    assert m["sms"] == [] and "confirmed" in m["consent_rejected"][0]
    print("sms consent gating ok")


def test_dnc_scrub_routing_31_days():
    d, ranked, traced = _traced("scrub")
    base = ["--ranked", ranked, "--traced", traced, "--as-of", "2026-11-19"]
    # no scrub at all: nothing is callable, everything is in NEEDS_SCRUB and blocked
    m = quiet(build_marketing_lists.main, base)
    assert m["call"] == [] and m["needs_scrub"]
    assert all(x["call_eligibility"] == "blocked" for x in m["needs_scrub"])
    assert rows(os.path.join(d, "marketing", "cold_call_NEEDS_SCRUB.csv"))
    scrub = os.path.join(d, "scrub.csv")
    skip_trace.write_rows(scrub, [{"phone": "6145550122", "dnc": "N", "scrub_date": "2026-11-10", "lists_checked": "federal; state:none; internal", "scrubbed_by": "Pat (test)", "vendor": "self (own SAN)"},   # fresh, clean
                                  {"phone": "6145550110", "dnc": "N", "scrub_date": "2026-09-01", "lists_checked": "federal; state:none; internal", "scrubbed_by": "Pat (test)", "vendor": "self (own SAN)"},   # too old
                                  {"phone": "6145550111", "dnc": "N", "scrub_date": "", "lists_checked": "federal; state:none; internal", "scrubbed_by": "Pat (test)", "vendor": "self (own SAN)"},             # no date
                                  {"phone": "6145550125", "dnc": "Y", "scrub_date": "2026-11-10", "lists_checked": "federal; state:none; internal", "scrubbed_by": "Pat (test)", "vendor": "self (own SAN)"}])  # on a DNC list
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub])
    ready = {p for x in m["call"] for p in (x["phone1"], x["phone2"], x["phone3"]) if p}
    held = {p for x in m["needs_scrub"] for p in (x["phone1"], x["phone2"], x["phone3"]) if p}
    assert ready == {"6145550122"}, ready
    assert "6145550110" in held and "6145550111" in held and "6145550125" not in ready | held
    row = [x for x in m["call"] if x["phone1"] == "6145550122"][0]
    assert row["dnc_scrub_date"] == "2026-11-10" and row["call_eligibility"] == "needs_review"
    assert row["time_zone"] and "8am-9pm" in row["calling_hours_note"]
    cc = rows(os.path.join(d, "marketing", "cold_call.csv"))
    assert {"time_zone", "calling_hours_note", "call_eligibility", "dnc_scrub_date"} <= set(cc[0].keys())
    # --dnc-scrub-date fills in rows with no date
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub, "--dnc-scrub-date", "2026-11-01"])
    assert "6145550111" in {p for x in m["call"] for p in (x["phone1"], x["phone2"], x["phone3"]) if p}
    # only the user's review file sets reviewed_for_campaign
    rv = os.path.join(d, "review.csv")
    skip_trace.write_rows(rv, [{"phone": "6145550122", "call_eligibility": "reviewed_for_campaign", "reviewed_by": "Pat", "review_date": "2026-11-18"}])
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub, "--call-review", rv])
    # 614 (Ohio, Eastern) but mailed to Arizona: the row says VERIFY, so a review without hours_verified is not enough
    r1 = [x for x in m["call"] if x["phone1"] == "6145550122"][0]
    assert r1["call_window_check"].startswith("VERIFY") and r1["call_eligibility"] == "needs_review"
    assert "Eastern" in r1["call_window_basis"] and "Arizona" in r1["call_window"]
    skip_trace.write_rows(rv, [{"phone": "6145550122", "call_eligibility": "reviewed_for_campaign", "reviewed_by": "Pat", "review_date": "2026-11-18", "hours_verified": "yes"}])
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub, "--call-review", rv])
    assert [x["call_eligibility"] for x in m["call"] if x["phone1"] == "6145550122"] == ["reviewed_for_campaign"]
    print("dnc scrub routing ok")


def test_suppression_applies_everywhere_and_persists():
    d, ranked, traced = _traced("sup")
    state = os.path.join(d, "state", "seen.json")
    base = ["--ranked", ranked, "--traced", traced, "--state-file", state, "--as-of", "2026-11-19"]
    scrub = os.path.join(d, "scrub.csv")
    skip_trace.write_rows(scrub, [{"phone": p, "dnc": "N", "scrub_date": "2026-11-15", "lists_checked": "federal; state:none; internal", "scrubbed_by": "Pat (test)", "vendor": "self (own SAN)"} for p in ("6145550110", "6145550111", "6145550123", "6145550122")])
    m0 = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub])
    assert m0["call"], "need callable owners for this test"
    victim = m0["call"][0]
    other = [x for x in m0["mail"] if x["owner_key"] != victim["owner_key"]][0]
    sup = os.path.join(d, "suppress.csv")
    skip_trace.write_rows(sup, [{"phone": "", "address": "", "owner": victim["owner"], "date": "2026-11-18", "channel": "all", "reason": "asked to stop"},
                                {"phone": "", "address": other["mail_street"], "owner": "", "date": "2026-11-18", "channel": "mail", "reason": "returned mail"}])
    stop = os.path.join(d, "stop.csv")
    skip_trace.write_rows(stop, [{"phone": "6145550122", "date": "2026-11-18"}])
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub, "--suppress", sup, "--stop-replies", stop])
    keys = lambda L: {x["owner_key"] for x in L}
    assert victim["owner_key"] not in keys(m["crm"]) | keys(m["mail"]) | keys(m["call"]) | keys(m["needs_scrub"]) | keys(m["new"])
    assert other["owner_key"] not in keys(m["mail"]) and other["owner_key"] in keys(m["crm"])
    assert "6145550122" not in {p for x in m["call"] + m["needs_scrub"] for p in (x["phone1"], x["phone2"], x["phone3"]) if p}
    master = os.path.join(d, "state", "suppression.csv")
    saved = rows(master)
    assert len(saved) == 3 and any(r["reason"] == "replied STOP" and r["phone"] == "6145550122" for r in saved)
    assert rows(os.path.join(d, "marketing", "suppressed_this_run.csv"))
    # next run WITHOUT the flags: the master list still applies
    m2 = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub])
    assert victim["owner_key"] not in keys(m2["crm"]) and other["owner_key"] not in keys(m2["mail"])
    assert "6145550122" not in {p for x in m2["call"] for p in (x["phone1"], x["phone2"], x["phone3"]) if p}
    # skip-trace export leaves out owners suppressed for every channel
    up, _ = quiet(skip_trace.main, ["export", "--ranked", ranked, "--suppress", master, "--output-dir", os.path.join(d, "st2")])
    assert victim["owner_key"] not in {u["Owner Key"] for u in up}
    print("suppression ok")


def test_demo_is_isolated_from_real_state():
    cwd = os.getcwd()
    work = out("demo_iso")
    os.chdir(work)
    try:
        os.makedirs(os.path.join("out", "state"))
        real = os.path.join("out", "state", "seen_owners.json")
        with open(real, "w") as f:
            f.write('{"keep": "2026-01-01"}')
        before = open(real).read()
        quiet(run_pipeline.main, ["--demo", "--satellite", "links"])
        assert os.path.exists(os.path.join("out_demo", "START_HERE.md"))
        assert open(real).read() == before, "demo must not touch out/state/seen_owners.json"
        assert not os.path.exists(os.path.join("out_demo", "state")), "demo keeps no state"
        assert sorted(os.listdir(os.path.join("out", "state"))) == ["seen_owners.json"]
    finally:
        os.chdir(cwd)
    print("demo isolation ok")


def test_buy_box_evidence_and_preset_labels():
    d = out("bbe")
    quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01", "--output-dir", d,
                               "--known-developers", os.path.join(S, "known_developers.example.txt")])
    summ = open(os.path.join(d, "buy_box_summary.md")).read()
    for t in ("Verified grantee purchases", "Keyword-inferred buyers", "Current-owner proxies", "grantor-grantee index",
              "title company", "From the single_family preset", "Recent developer purchase patterns", "Left out"):
        assert t in summ, t
    assert {"evidence", "counted_because"} <= set(rows(os.path.join(d, "developer_sales.csv"))[0].keys())
    d2 = out("bbe_low")
    few = rows(os.path.join(S, "sample_developer_sales.csv"))[:6]
    p = os.path.join(d2, "few.csv")
    skip_trace.write_rows(p, few, list(few[0].keys()))
    quiet(build_buy_box.main, ["--sales", p, "--as-of", "2026-11-01", "--output-dir", d2])
    low = open(os.path.join(d2, "buy_box_summary.md")).read()
    assert "**Confidence: LOW**" in low and "do not treat this as a real buy box" in low and "acres (size range)" in low.split("From the")[1]
    print("buy box evidence ok")


def test_entity_shaped_exclusions_estate_vs_trust_and_research_next():
    import pandas as pd
    df = pd.DataFrame({"TYPE_USE_DECODE": ["", ""], "LAND_CLASS_DECODE": ["Cemetery", "Vacant"]})
    assert score_parcels.pick(df, "land_use") == "LAND_CLASS_DECODE"  # skip an all-blank alias column
    assert score_parcels.owner_exclusion("CITADEL GETHSEMANE MEMORIAL ", "") == "cemetery"
    assert score_parcels.owner_exclusion("JONES, MARY", "Cemetery") == "use: cemetery"
    oe = score_parcels.owner_exclusion
    assert oe("POWER, JOHN", "") is None and oe("JOHN BUILDER", "") is None and oe("MARY TEMPLE", "") is None
    assert oe("SMITH HOMES LLC", "") == "builder / developer" and oe("GRACE BAPTIST CHURCH", "") == "church / religious"
    def mutate(src):
        src[11]["owner_name"] = "SMITH JOHN REVOCABLE LIVING TRUST"
        src[14]["owner_name"] = "ESTATE OF MARY SAMPLE"
        src[1]["owner_name"] = "OAK RIDGE HOMEOWNERS ASSOCIATION"
        src[2]["flood_pct"] = "12.5"
    r = _score_file("ent", mutate)
    assert "trust owner" in r["SAMPLE-012"]["motivation_signals"] and "estate / heirs" not in r["SAMPLE-012"]["motivation_signals"]
    assert "estate / heirs" in r["SAMPLE-015"]["motivation_signals"]
    assert "12% of parcel" in r["SAMPLE-003"]["why"] or "13% of parcel" in r["SAMPLE-003"]["why"], r["SAMPLE-003"]["why"]
    ex = rows(os.path.join(TMP, "ent", "excluded_owners.csv"))
    assert any(x["apn"] == "SAMPLE-002" and x["matched"] for x in ex)
    elig = [x for x in r.values() if x["rank"]]
    assert all(x["research_next"] and "zoning" in x["research_next"] for x in elig)
    assert campaign_kit.is_estate("ESTATE OF MARY SAMPLE") and campaign_kit.is_estate("SAMPLE OWNER 12 ESTATE")
    assert not campaign_kit.is_estate("SMITH JOHN REVOCABLE LIVING TRUST") and not campaign_kit.is_estate("ACME REAL ESTATE LLC")
    import openpyxl
    wb = openpyxl.load_workbook(os.path.join(TMP, "ent", "development_sites.xlsx"))
    assert wb.sheetnames[0] == "Read me" and "SCREENING TOOL ONLY" in str(wb["Read me"]["A2"].value)
    print("entity-shaped exclusions + estate vs trust + research next ok")


def test_source_failures_are_friendly():
    import enrich_constraints, fetch_infrastructure
    old = enrich_constraints.polys, enrich_constraints.elev
    enrich_constraints.polys = lambda *a, **k: None
    enrich_constraints.elev = lambda pt: None
    try:
        res = enrich_constraints.enrich({"_lat": 40.0, "_lon": -83.0, "_acres": 10}, 10)
    finally:
        enrich_constraints.polys, enrich_constraints.elev = old
    assert res["constraint_check"] == "partial" and "source unavailable; scoring continued without this factor" in res["constraint_notes"]
    # Overpass down: highways/rail/power fall back to TIGER / HIFLD, substations are labeled unavailable
    oq, ofb = fetch_infrastructure.query, fetch_infrastructure.fallback
    def dead(*a, **k):
        raise RuntimeError("timed out")
    fetch_infrastructure.query = dead
    fetch_infrastructure.fallback = lambda layer, bbox, t: (([{"layer": layer, "name": "x", "voltage": "", "ref": "TIGER", "lat": 40.0, "lon": -83.0}], "TIGER")
                                                           if layer in fetch_infrastructure.FALLBACK else (None, None))
    o = os.path.join(out("infra"), "infra.csv")
    try:
        res = quiet(fetch_infrastructure.main, ["--bbox", "39.9,-83.1,40.0,-83.0", "--output", o, "--layers", "rail,water_plant"])
    finally:
        fetch_infrastructure.query, fetch_infrastructure.fallback = oq, ofb
    assert "TIGER" in res["sources"]["rail"] and res["sources"]["water_plant"] == "source unavailable; scoring continued without this factor"
    # Overpass forced off: Overpass is never called; power and interchanges come from the public fallbacks
    called = []
    fetch_infrastructure.query = lambda *a, **k: called.append(1)
    fetch_infrastructure.arcgis_features = lambda url, bbox, t, where=None: [("x", "115", [(40.0, -83.0), (40.01, -83.0)])]
    try:
        res = quiet(fetch_infrastructure.main, ["--bbox", "39.9,-83.1,40.0,-83.0", "--output", o, "--no-overpass",
                                                "--layers", "substation,transmission_line,highway_interchange"])
    finally:
        fetch_infrastructure.query = oq
        import importlib; importlib.reload(fetch_infrastructure)
    assert not called
    assert "HIFLD substations" in res["sources"]["substation"] and "HIFLD transmission" in res["sources"]["transmission_line"]
    assert "S1630" in res["sources"]["highway_interchange"]
    assert all("hifld-geoplatform" not in u and "hifld.dhs" not in u for v in fetch_infrastructure.FALLBACK.values() for u, _, _ in v)
    assert len(fetch_infrastructure.MIRRORS) >= 2
    import _common
    assert _common.ssl_context() is not None
    print("friendly source failures ok")


def test_owner_with_two_parcels_is_one_row():
    d = out("group")
    r = rows(os.path.join(TMP, "score", "parcels_ranked.csv")) if os.path.exists(os.path.join(TMP, "score", "parcels_ranked.csv")) else None
    if r is None:
        d2, _ = _scored("score")
        r = rows(os.path.join(d2, "parcels_ranked.csv"))
    elig = [x for x in r if x["rank"]][:2]
    elig[1].update({k: elig[0][k] for k in ("owner", "mail_street", "mail_city", "mail_state", "mail_zip")})
    p = os.path.join(d, "two.csv")
    skip_trace.write_rows(p, elig, list(elig[0].keys()))
    m = quiet(build_marketing_lists.main, ["--ranked", p, "--tiers", "A,B,C"])
    assert len(m["crm"]) == 1 and m["crm"][0]["parcels"] == 2 and ";" in m["crm"][0]["apns"]
    print("owner grouping ok")


def test_campaign_kit_fills_merge_fields():
    d = out("camp")
    m = os.path.join(TMP, "mkt", "marketing")
    if not os.path.exists(os.path.join(m, "mail.csv")):
        test_marketing_lists_rules()
    quiet(campaign_kit.main, ["--marketing-dir", m, "--output-dir", d, "--your-name", "Pat Lee", "--company", "Lee Land Co", "--phone", "555-555-0100"])
    for fn in ("offer_letter.txt", "cold_call_opener.txt", "sms_opener.txt", "LOAD_INTO_YOUR_TOOLS.md", "campaign_checklist.md", "mail_merge.csv"):
        assert os.path.exists(os.path.join(d, fn)), fn
    merged = rows(os.path.join(d, "mail_merge.csv"))
    assert merged and all("{{" not in x["letter_text"] and "Pat Lee" in x["letter_text"] for x in merged)
    assert "Reply STOP to opt out" in open(os.path.join(d, "sms_opener.txt")).read()
    assert "consent" in open(os.path.join(d, "sms_opener.txt")).read()
    assert "State wholesaling / assignment rules" in open(os.path.join(d, "offer_letter.txt")).read()
    assert "personal representative" in open(os.path.join(d, "estate_letter.txt")).read()
    load = open(os.path.join(d, "LOAD_INTO_YOUR_TOOLS.md")).read()
    assert "ringless voicemail" in load and "call_window" in load and "manual" in load.lower()
    chk = open(os.path.join(d, "STATE_AND_JURISDICTION_CHECK.md")).read()
    assert "wholesal" in chk.lower()
    # an estate owner gets the gentle letter
    mm = os.path.join(d, "est")
    os.makedirs(mm, exist_ok=True)
    skip_trace.write_rows(os.path.join(mm, "mail.csv"), [
        {"owner": "ESTATE OF JANE SAMPLE", "first_name": "", "last_name": "", "is_company": "Y", "mail_street": "1 Sample St",
         "mail_city": "Sample", "mail_state": "OH", "mail_zip": "43000", "property_address": "2 Sample Rd", "total_acres": "12", "county": "Sample County"},
        {"owner": "JOHN SAMPLE", "first_name": "John", "last_name": "Sample", "is_company": "", "mail_street": "3 Sample St",
         "mail_city": "Sample", "mail_state": "OH", "mail_zip": "43000", "property_address": "4 Sample Rd", "total_acres": "9", "county": "Sample County"}])
    quiet(campaign_kit.main, ["--marketing-dir", mm, "--output-dir", os.path.join(d, "est_out")])
    em = rows(os.path.join(d, "est_out", "mail_merge.csv"))
    assert em[0]["letter_type"] == "estate" and "Personal Representative, Estate of JANE SAMPLE" in em[0]["letter_text"] and "ESTATE OF JANE SAMPLE\n" not in em[0]["letter_text"]
    assert "fair, no-obligation offer" not in em[0]["letter_text"]
    assert em[1]["letter_type"] == "standard"
    print("campaign kit ok")


def test_full_demo_run():
    d = out("demo")
    res = quiet(run_pipeline.main, ["--demo", "--satellite", "links", "--output-dir", d])
    assert res["summary"]["eligible"] > 0 and res["marketing"]["mail"]
    for fn in ("START_HERE.md", "buy_box.json", "buy_box_summary.md", "parcels_ranked.csv", "index.html",
               "satellite/satellite_review.csv", "skiptrace/skiptrace_upload.csv", "marketing/crm_import.csv",
               "marketing/cold_call.csv", "marketing/mail.csv", "campaign/offer_letter.txt", "campaign/estate_letter.txt",
               "buyers_review.csv", "skiptrace/skiptrace_report.txt"):
        assert os.path.exists(os.path.join(d, fn)), fn
    assert not os.path.exists(os.path.join(d, "marketing", "sms.csv"))
    start = open(os.path.join(d, "START_HERE.md")).read()
    assert "DEMO" in start and "Verify zoning with the city" in start and "Nothing has been mailed" in start
    assert start.startswith("> **SCREENING TOOL ONLY")
    assert "**Last run: " in start.split("## Top 5")[0] and "weekly" in start
    assert "CRM import file" in start and "confidence MEDIUM" in start
    print("full demo ok")


def test_skill_copies_match_and_parcel_geometry():
    a = open(os.path.join(ROOT, "SKILL.md")).read()
    b = open(os.path.join(ROOT, ".claude", "skills", "development-opportunity-finder", "SKILL.md")).read()
    assert a == b, "SKILL.md at the top and in .claude/skills must be the same file"
    import fetch_arcgis_parcels as f
    # 1,000 ft square near 40N built on the ground (metres per degree at 40N), clockwise like Esri outer rings
    lat0, lon0, m = 40.0, -83.0, 304.8
    dlat = m / 111034.6
    dlon = m / (111319.49 * math.cos(math.radians(lat0)))
    ring = [[lon0, lat0], [lon0, lat0 + dlat], [lon0 + dlon, lat0 + dlat], [lon0 + dlon, lat0], [lon0, lat0]]
    acres, lat, lon = f.geom_stats({"rings": [ring]})
    assert abs(acres - 1e6 / 43560) / (1e6 / 43560) < 0.005, acres
    assert abs(lat - (lat0 + dlat / 2)) < 1e-5 and abs(lon - (lon0 + dlon / 2)) < 1e-5, (lat, lon)
    print("skill copies + geometry ok")


def test_launchers_and_setup():
    mac = os.path.join(ROOT, "start-mac.command")
    win = os.path.join(ROOT, "start-windows.bat")
    assert os.path.exists(mac) and os.path.exists(win)
    assert os.access(mac, os.X_OK) or os.name == "nt"
    m, w = open(mac).read(), open(win).read()
    assert ".venv" in m and "python3" in m and "requirements.txt" in m
    assert ".venv" in w and "Add python.exe to PATH" in w and "requirements.txt" in w
    setup = open(os.path.join(ROOT, "SETUP.md")).read()
    steps = [l for l in setup.splitlines() if l.startswith("## ")]
    assert len(steps) == 4 and "PropStream" in steps[0], steps
    assert "claude.ai" in setup and "Add python.exe to PATH" in setup and "once a week" in setup
    assert "Open Anyway" in setup and "Sequoia" in setup and "More info" in setup and "Run anyway" in setup
    assert "Open Anyway" in m and "doctor.py" in m and "command -v claude" in m and "sys.version_info >= (3, 10)" in m
    assert "More info" in w and "Run anyway" in w and "doctor.py" in w and "where claude" in w
    for doc in ("SETUP.md", "README.md", "SKILL.md"):
        t = open(os.path.join(ROOT, doc)).read().lower()
        assert "20 minutes" not in t and "schedule this weekly" not in t, doc
    sk = open(os.path.join(ROOT, "SKILL.md")).read()
    desc = sk.split("description:", 1)[1].split("\n", 1)[0].strip()
    assert len(desc) < 800, len(desc)
    assert ".venv/bin/python" in sk and ".venv/Scripts/python.exe scripts/" in sk
    assert "python scripts/" not in sk.replace(".venv/bin/python scripts/", "").replace(".venv/Scripts/python.exe scripts/", ""), "SKILL.md must use the .venv python"
    assert os.path.exists(os.path.join(ROOT, "KNOWN_LIMITS.md")) and "Not tested on a clean Mac" in open(os.path.join(ROOT, "KNOWN_LIMITS.md")).read()
    import doctor
    res = doctor.check(online=False)
    assert any("Python" in r[1] for r in res) and any("Claude Code" in r[1] for r in res)
    print("launchers ok")


def test_repo_is_ascii_and_has_no_secrets():
    bad = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git", "out", "output", ".venv")]
        for fn in files:
            if fn.endswith((".pyc", ".zip", ".xlsx", ".jpg", ".png")) or ".venv" in root:
                continue
            data = open(os.path.join(root, fn), "rb").read()
            try:
                data.decode("ascii")
            except UnicodeDecodeError:
                bad.append(fn)
            low = data.decode("latin-1").lower()
            if fn == "test_pipeline.py":
                continue
            for pat in ("sk_" + "live_", "ai" + "za", "bearer " + "ey", "api_key" + "=", "apikey" + "="):
                assert pat not in low, (fn, pat)
    assert not bad, bad
    print("ascii + no secrets ok")


def test_round4_normalization_timezones_and_drop_folder():
    import _common, suppression, timezones, datetime as _dt
    for p in ("(919) 555-0134", "9195550134", "+19195550134", "1-919-555-0134"):
        assert _common.clean_phone(p) == "9195550134", p
    assert _common.norm_address("123 Main St") == _common.norm_address("123 MAIN STREET")
    assert _common.norm_address("45 N. Oak Ave., Apt 2") == _common.norm_address("45 north oak avenue apt 2")
    sup = suppression.Suppression([{"phone": "9195550134", "address": "123 MAIN STREET", "owner": "", "date": "", "channel": "all", "reason": "asked"}])
    assert sup.phone("+1 (919) 555-0134", "call") and sup.phone("(919) 555-0134", "sms")
    assert sup.owner("SOMEONE ELSE", ["123 Main St"], "mail")
    assert not sup.owner("SOMEONE ELSE", ["1234 Main St"], "mail")
    d = out("dropdir")
    assert suppression.drop_folder(os.path.join(d, "nope"))[:2] == ([], None)
    p = os.path.join(d, "dnc_export.csv")
    skip_trace.write_rows(p, [{"phone": "(919) 555-0134", "address": "", "owner": "", "date": "2026-11-01", "channel": "all", "reason": "x"}])
    files, age, info = suppression.drop_folder(d)
    assert files == [p] and age is None and info["undated"], "an export with no generated date is never current"
    assert suppression.freshness_reason(age, info)
    today = _dt.date.today()
    with open(p + suppression.META_SUFFIX, "w") as f:
        json.dump({"export_date": today.isoformat()}, f)
    files, age, info = suppression.drop_folder(d)
    assert files == [p] and age == 0 and suppression.freshness_reason(age, info) == ""
    with open(p + suppression.META_SUFFIX, "w") as f:
        json.dump({"export_date": (today - _dt.timedelta(days=9)).isoformat()}, f)
    os.utime(p, None)  # copied in today: the file's own date must not matter
    assert suppression.drop_folder(d)[1] == 9 > suppression.DROP_STALE_DAYS
    assert timezones.estimate("NC", "27601")[0].startswith("Eastern")
    z, basis = timezones.estimate("FL", "32501")  # Pensacola: Central
    assert z.startswith("Central") and "two time zones" in basis, (z, basis)
    z, basis = timezones.estimate("FL", "")
    assert "check" in z and "two time zones" in basis
    assert "estimate" in timezones.estimate("OH", "43000")[1]
    print("round-4 normalization / time zones / drop folder ok")


def test_round4_scrub_consent_voice_and_compliance_text():
    d, ranked, traced = _traced("r4")
    base = ["--ranked", ranked, "--traced", traced, "--as-of", "2026-11-19"]
    scrub = os.path.join(d, "scrub.csv")
    skip_trace.write_rows(scrub, [{"phone": "6145550122", "dnc": "N", "scrub_date": "2026-11-10", "lists_checked": "federal only"}])
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub])
    held = [x for x in m["needs_scrub"] if "6145550122" in (x["phone1"], x["phone2"], x["phone3"])]
    assert not any("6145550122" in (x["phone1"], x["phone2"], x["phone3"]) for x in m["call"]), "a federal-only scrub is incomplete"
    assert held and "incomplete" in json.dumps(held[0]).lower()
    skip_trace.write_rows(scrub, [{"phone": "6145550122", "dnc": "N", "scrub_date": "2026-11-10", "lists_checked": "federal; state:none; internal", "scrubbed_by": "Pat (test)", "vendor": "self (own SAN)"}])
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub])
    row = [x for x in m["call"] if x["phone1"] == "6145550122"][0]
    assert "line_type" in row and row["call_rules"] == build_marketing_lists.VOICE_LINE
    assert row["time_zone"] and row["time_zone_basis"].startswith("estimate")
    cc = rows(os.path.join(d, "marketing", "cold_call.csv"))
    assert {"line_type", "time_zone_basis", "call_rules"} <= set(cc[0].keys())
    comp = open(os.path.join(d, "marketing", "COMPLIANCE.md")).read()
    for t in (build_marketing_lists.VOICE_LINE, build_marketing_lists.RVM_PARAGRAPH, build_marketing_lists.PREPARED_NOT_APPROVED,
              "10DLC", "federal", "internal", "Personal data", "revoc"):
        assert t in comp, t[:40]
    for st in ("Colorado", "Florida", "Indiana", "Louisiana", "Massachusetts", "Mississippi", "Missouri", "Oklahoma", "Pennsylvania",
               "Tennessee", "Texas", "Wyoming"):
        assert st in comp, st
    sk = open(os.path.join(ROOT, "SKILL.md")).read()
    assert build_marketing_lists.RVM_PARAGRAPH in sk and build_marketing_lists.VOICE_LINE in sk
    # consent: evidence required; a revoked row is rejected and added to suppression
    cons = os.path.join(d, "consent.csv")
    base_c = {"consented_to": "Acme Land", "purpose": "land offers", "method": "sms", "consent_date": "2026-10-01",
              "consent_source": "web form", "confirmed": "Y"}
    skip_trace.write_rows(cons, [dict(base_c, phone="6145550122", consent_evidence="form #9", revoked_date=""),
                                 dict(base_c, phone="6145550110", consent_evidence="", revoked_date=""),
                                 dict(base_c, phone="6145550111", consent_evidence="form #10", revoked_date="2026-11-02")])
    state = os.path.join(d, "state", "seen.json")
    m = quiet(build_marketing_lists.main, base + ["--sms", "--sms-sender", "Acme Land", "--consent-file", cons, "--state-file", state])
    sms_phones = {x.get("phone") or x.get("phone1") for x in m["sms"]}
    assert "6145550110" not in sms_phones and "6145550111" not in sms_phones
    log = rows(os.path.join(d, "marketing", "consent_log.csv"))
    assert len(log) == 3 and any("revoked" in json.dumps(x).lower() for x in log)
    master = os.path.join(d, "state", "suppression.csv")
    assert any(r["phone"] == "6145550111" for r in rows(master)), "revoked consent must land on the suppression list"
    print("round-4 scrub / consent / voice / compliance ok")


def test_round4_start_here_buyer_package_and_stale_suppression():
    d = out("r4run")
    sup = out("r4sup")
    argv = ["--parcels", os.path.join(S, "sample_parcels.csv"), "--sales", os.path.join(S, "sample_developer_sales.csv"),
            "--infra", os.path.join(S, "sample_infrastructure.csv"), "--config", LAND_CFG, "--state", "OH",
            "--skiptrace-results", os.path.join(S, "sample_skiptrace_results.csv"), "--as-of", "2026-11-01",
            "--satellite", "links", "--suppress-dir", sup, "--output-dir", d, "--enrich-top", "0"]
    quiet(run_pipeline.main, argv)
    start = open(os.path.join(d, "START_HERE.md")).read()
    assert build_marketing_lists.PREPARED_NOT_APPROVED in start and build_marketing_lists.VOICE_LINE in start
    assert "SUPPRESSION LIST MAY BE OUT OF DATE" in start
    bp = rows(os.path.join(d, "buyer_package.csv"))
    assert bp and list(bp[0].keys()) == run_pipeline.BUYER_COLS
    for col in bp[0]:
        assert not any(w in col for w in ("owner", "mail", "phone", "email")), col
    import suppression, datetime as _dt
    today = _dt.date.today()
    # an undated export copied in today does not count
    skip_trace.write_rows(os.path.join(sup, "today.csv"), [{"phone": "6145550999", "address": "", "owner": "", "date": "2026-11-19", "channel": "all", "reason": "x"}])
    quiet(run_pipeline.main, argv)
    assert "SUPPRESSION LIST MAY BE OUT OF DATE" in open(os.path.join(d, "START_HERE.md")).read()
    os.remove(os.path.join(sup, "today.csv"))
    # an OLD export (its header says it was generated 30 days ago) copied in today must not pass: fail closed
    src = out("r4src")
    old_exp = os.path.join(src, "crm_optouts.csv")
    with open(old_exp, "w") as f:
        f.write(f"# Exported: {(today - _dt.timedelta(days=30)).isoformat()}\nphone,owner,date,channel,reason\n6145550999,,2026-10-01,all,x\n")
    quiet(suppression.main, ["import", old_exp, "--folder", sup, "--source", "CRM", "--by", "test"])
    assert os.path.getmtime(os.path.join(sup, "crm_optouts.csv")) > _dt.datetime.now().timestamp() - 600, "copied today"
    quiet(run_pipeline.main, argv)
    start = open(os.path.join(d, "START_HERE.md")).read()
    assert "SUPPRESSION LIST MAY BE OUT OF DATE" in start and "generated 30 days ago" in start, "an old export imported today must not pass"
    assert os.path.exists(os.path.join(d, "marketing", "PHONE_AND_SMS_HELD.txt"))
    # the file says 30 days old: entering today's date on import does not override what the file says
    quiet(suppression.main, ["import", old_exp, "--folder", sup, "--export-date", today.isoformat()])
    assert suppression.drop_folder(sup)[1] == 30
    # an undated export: import refuses without --export-date, then records the date the user enters
    und = os.path.join(src, "dialer_dnc.csv")
    skip_trace.write_rows(und, [{"phone": "6145550998", "address": "", "owner": "", "date": "", "channel": "call", "reason": "x"}])
    try:
        quiet(suppression.main, ["import", und, "--folder", sup])
        raise AssertionError("import without a generated date must refuse")
    except SystemExit as e:
        assert "generated date" in str(e) and not os.path.exists(os.path.join(sup, "dialer_dnc.csv"))
    try:
        quiet(suppression.main, ["import", und, "--folder", sup, "--export-date", (today + _dt.timedelta(days=2)).isoformat()])
        raise AssertionError("a future export date must refuse")
    except SystemExit as e:
        assert "future" in str(e)
    quiet(suppression.main, ["import", und, "--folder", sup, "--export-date", (today - _dt.timedelta(days=1)).isoformat(), "--source", "dialer"])
    quiet(run_pipeline.main, argv)
    start = open(os.path.join(d, "START_HERE.md")).read()
    assert "SUPPRESSION LIST MAY BE OUT OF DATE" not in start
    assert any(r["phone"] == "6145550999" for r in rows(os.path.join(d, "state", "suppression.csv")))
    print("round-4 START_HERE / buyer package / stale suppression ok")


def test_round4_buy_box_funnel_probable_grantee_and_low_wording():
    d = out("r4bb")
    src = rows(os.path.join(S, "sample_developer_sales.csv"))
    sales = os.path.join(d, "owner_sales.csv")
    conv = []
    for i, r in enumerate(src):
        r = dict(r)
        r["owner"] = r.pop("buyer_name")
        r["deed_date"] = r["sale_date"] if i % 2 == 0 else "2019-01-01"
        conv.append(r)
    skip_trace.write_rows(sales, conv, list(conv[0].keys()))
    par = rows(os.path.join(S, "sample_parcels.csv"))
    pfile = os.path.join(d, "parcels.csv")
    par[0] = dict(par[0], **{k: "SAMPLE HOMES LLC" for k in par[0] if k.lower() in ("owner", "owner_name")})
    skip_trace.write_rows(pfile, par, list(par[0].keys()))
    quiet(build_buy_box.main, ["--sales", sales, "--as-of", "2026-11-01", "--parcels", pfile, "--output-dir", d])
    summ = open(os.path.join(d, "buy_box_summary.md")).read()
    assert "## How the sales were narrowed down" in summ and "sales in the file -> " in summ
    import re as _re
    pg = int(_re.search(r"Probable grantees[^:]*: (\d+)", summ).group(1))
    assert pg > 0, summ
    assert any("probable grantee" in u.get("evidence", "") for u in rows(os.path.join(d, "developer_sales.csv")))
    assert "Builder-owned land now (from your parcel file" in summ and os.path.exists(os.path.join(d, "builder_owned_parcels.csv"))
    assert int(_re.search(r"Builder-owned land now[^:]*: (\d+) parcels", summ).group(1)) >= 1
    # few deeds: no premium claims, and LOW wording never says "matches recent developer purchase patterns"
    d2 = out("r4bb_low")
    few = os.path.join(d2, "few.csv")
    skip_trace.write_rows(few, src[:6], list(src[0].keys()))
    quiet(build_buy_box.main, ["--sales", few, "--as-of", "2026-11-01", "--min-sales", "3", "--output-dir", d2])
    s2 = open(os.path.join(d2, "buy_box_summary.md")).read()
    assert "Not shown" in s2 and "paid a premium (25%" not in s2.split("## Premiums")[-1].split("##")[0].replace("Not shown", "")
    if "LOW" in s2:
        assert "matches recent developer purchase patterns" not in s2
    print("round-4 buy box ok")


def test_round4_small_items():
    import fetch_arcgis_parcels, cleanup_exports, doctor, time as _t
    fl = fetch_arcgis_parcels.license_flags("For non-commercial use only. Resale prohibited. A fee applies to bulk data.")
    assert len(fl) >= 3 and any("non-commercial" in x for x in fl)
    assert fetch_arcgis_parcels.license_flags("Public data, no restrictions.") == []
    assert campaign_kit.decedent_name("ESTATE OF JANE SAMPLE") == "JANE SAMPLE"
    assert campaign_kit.decedent_name("SAMPLE, JOHN ESTATE") == "SAMPLE, JOHN"
    assert "Personal Representative, Estate of {{decedent}}" in campaign_kit.ESTATE if hasattr(campaign_kit, "ESTATE") else True
    links = skip_trace.sos_links("ABC LAND LLC", "nc")
    assert "secretary+of+state" in links["sos_search_link"].lower() and links["opencorporates_link"].endswith("us_nc?q=ABC+LAND+LLC")
    # entities_to_research has the SoS link and registered agent columns
    d, _ = _scored("r4ent")
    quiet(skip_trace.main, ["export", "--ranked", os.path.join(d, "parcels_ranked.csv")])
    ent = os.path.join(d, "skiptrace", "entities_to_research.csv")
    assert os.path.exists(ent)
    if True:
        hdr = open(ent).readline()
        assert "sos_search_link" in hdr and "registered_agent" in hdr, hdr
    # cleanup never touches the suppression list / consent log
    c = out("r4clean")
    for fn in ("crm_import.csv", "suppression.csv", "consent_log.csv"):
        p = os.path.join(c, fn)
        open(p, "w").write("x\n")
        os.utime(p, (_t.time() - 200 * 86400, _t.time() - 200 * 86400))
    found = [os.path.basename(p) for p, _ in cleanup_exports.old_files([c], 90)]
    assert found == ["crm_import.csv"], found
    quiet(cleanup_exports.main, ["--folder", c, "--delete"])
    assert sorted(os.listdir(c)) == ["consent_log.csv", "suppression.csv"]
    assert doctor.folder_problem(r"C:\Users\a\AppData\Local\Temp\Temp1_kit.zip\dof").startswith("Right-click the zip > Extract All first")
    assert doctor.folder_problem("/Users/a/EBRE Land/dof") == ""
    print("round-4 small items ok")


def test_round4_setup_files():
    m = open(os.path.join(ROOT, "start-mac.command")).read()
    w = open(os.path.join(ROOT, "start-windows.bat")).read()
    for t in ("python3.15", "python3.13", "python3.10", "for v in 3.15 3.14", "/Library/Frameworks/Python.framework", '"/usr/bin/python3" ] && continue', "--check", "EBRE-Land", "Allow"):
        assert t in m, t
    for t in ("py -3", "py -%%V", "(3.15 3.14 3.13 3.12 3.11 3.10)", "where pymanager", ":nopyruntime",
              "Python install manager found but no Python installed. Run: py install 3.14", "WindowsApps", "Right-click the zip ^> Extract All first", "/check", "C:\\EBRE-Land", "\\AppData\\Local\\Temp\\"):
        assert t in w, t
    st = json.load(open(os.path.join(ROOT, ".claude", "settings.json")))
    assert "Bash(.venv/bin/python scripts/*)" in st["permissions"]["allow"] and "Read(./.env)" in st["permissions"]["deny"]
    assert os.path.exists(os.path.join(ROOT, "CLAUDE.md"))
    for t in ("consent.csv", "call_review.csv", "suppress.csv"):
        hdr = open(os.path.join(ROOT, "templates", t)).read().strip()
        assert hdr and "\n" not in hdr, t  # header only, no rows
    sec = open(os.path.join(ROOT, "SECURITY.md")).read()
    assert "What the starter runs" in sec and "Where owner data goes" in sec and "safeguards, not guarantees" in sec and "SHA256SUMS.txt" in sec
    assert "What stays local" not in sec and "never uploads" not in sec
    # the CI workflow lives in the source repo (../.github/workflows/), not in the zip
    wfp = os.path.join(os.path.dirname(ROOT), ".github", "workflows", "dev-skill-clean-machine.yml")
    assert not os.path.exists(os.path.join(ROOT, ".github"))
    if os.path.exists(wfp):
        wf = open(wfp).read()
        for t in ("macos-latest", "windows-latest", '"3.10", "3.13", "3.14", "3.15"', "allow-prereleases: true",
                  "Python install manager found but no Python installed. Run: py install 3.14", "tags:", '"v*"', "branches:",
                  "development-opportunity-finder-${{ steps.ref.outputs.name }}", "./start-mac.command --check", "cmd /c start-windows.bat /check",
                  "ditto -xk", "Expand-Archive", "EBRE Land (1)", "sha256", "test_pipeline.py", "test_finder.py", "--demo",
                  "Python 3.10 or newer was not found", "inside the zip or a temporary folder", "Python.PythonInstallManager",
                  "upload-artifact", "workflow_dispatch", "setup_check.txt", "KIT: development-opportunity-finder"):
            assert t in wf, t
    print("round-4 setup files ok")



# ------------------------------------------------------------------ round 5
def _zip_path():
    z = os.environ.get("DOF_ZIP")
    if z and os.path.exists(z):
        return z
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import build_zip
    z = os.path.join(TMP, "built", "development-opportunity-finder.zip")
    os.makedirs(os.path.dirname(z), exist_ok=True)
    build_zip.build(ROOT, z)
    return z


def test_round5_zip_line_endings_and_exec_bits():
    import stat as _st
    import zipfile
    z = zipfile.ZipFile(_zip_path())
    names = z.namelist()
    top = {n.split("/")[0] for n in names}
    assert top == {"development-opportunity-finder"}, top
    assert not any(p in n for n in names for p in ("/.venv/", "/out/", "/out_demo/", "/.github/", "__pycache__", "setup_check.txt"))
    seen = set()
    for info in z.infolist():
        n = info.filename
        mode = (info.external_attr >> 16) & 0o777
        if n.endswith(".bat"):
            data = z.read(n)
            assert b"\r\n" in data and data.count(b"\n") == data.count(b"\r\n"), n + " must be CRLF only"
            assert mode & 0o111 == 0, n
            seen.add("bat")
        if n.endswith((".command", ".sh")):
            data = z.read(n)
            assert b"\r" not in data, n + " must be LF only"
            assert mode & 0o755 == 0o755 and _st.S_ISREG(info.external_attr >> 16), (n, oct(mode))
            seen.add("command")
    assert seen == {"bat", "command"}
    # the source files are already in the shipped form, so SHA256SUMS.txt matches the zip
    for fn in ("start-windows.bat", "start-mac.command"):
        assert open(os.path.join(ROOT, fn), "rb").read() == z.read("development-opportunity-finder/" + fn), fn
    print("round-5 zip line endings / exec bits ok")


def test_round5_windows_starter_branches():
    w = open(os.path.join(ROOT, "start-windows.bat"), "rb").read().decode("ascii")
    lines = [x.strip() for x in w.split("\r\n")]
    assert 'if /i not "%HERE:\\AppData\\Local\\Temp\\=%"=="%HERE%" goto inzip' in lines
    assert 'if /i not "%HERE:.zip\\=%"=="%HERE%" goto inzip' in lines
    # an explicit not-found branch, reached by goto, with nothing falling through into :inzip or :nopython
    assert "goto nopython" in lines and "PROBLEM: Python 3.10 or newer was not found." in w
    for label in (":inzip", ":nopython", ":badfolder", ":venvfail", ":pipfail", ":noclaude", ":checkdone", ":try", ":havepy"):
        i = lines.index(label)
        prev = [x for x in lines[:i] if x and not x.upper().startswith("REM")][-1]
        assert prev.lower().startswith(("exit /b", "goto ")), (label, prev)
    # every candidate is version-checked with stdin from nul (py -3 can't sit at a first-run prompt)
    assert 'sys.exit(0 if sys.version_info >= (3, 10) else 1)" <nul' in w
    assert "call :try py -3" in w and "('where python 2^>nul') do call :try" in w and "('where python3 2^>nul') do call :try" in w
    assert "PYTHON_MANAGER_FIRST_RUN=false" in w and "PYTHON_MANAGER_AUTOMATIC_INSTALL=false" in w
    assert "pythoncore-3.*" in w and "Git\\bin\\bash.exe" in w and "CLAUDE_CODE_GIT_BASH_PATH" in w
    assert "PAID Claude plan" in w and "setup_check.txt" in w
    assert not any(x.endswith("(") for x in lines), "no parenthesized blocks (paths with ( ) break them)"
    assert all(ord(c) < 128 for c in w)
    m = open(os.path.join(ROOT, "start-mac.command")).read()
    assert "PAID Claude plan" in m and "Python 3.10 or newer was not found" in m and "setup_check.txt" in m
    print("round-5 windows starter ok")


def test_round5_mac_starter_runs_refusals_and_no_python():
    import subprocess
    if os.name == "nt" or not os.path.exists("/bin/bash"):
        print("round-5 mac starter: skipped (no bash)")
        return
    base = os.path.join(ROOT, "out", "_starter_test")
    shutil.rmtree(base, ignore_errors=True)
    zdir = os.path.join(base, "Kit (1).zip", "development-opportunity-finder")
    os.makedirs(zdir)
    shutil.copy(os.path.join(ROOT, "start-mac.command"), zdir)
    r = subprocess.run(["/bin/bash", os.path.join(zdir, "start-mac.command"), "--check"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=60)
    assert r.returncode == 1 and "inside a zip" in r.stdout, r.stdout
    plain = os.path.join(base, "EBRE Land (1)")
    os.makedirs(plain)
    shutil.copy(os.path.join(ROOT, "start-mac.command"), plain)
    r = subprocess.run(["/bin/bash", os.path.join(plain, "start-mac.command"), "--check"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=60, env={"PATH": "/nonexistent", "EBRE_PATH_ONLY": "1", "HOME": base})
    assert r.returncode == 1 and "Python 3.10 or newer was not found" in r.stdout, r.stdout
    assert not os.path.exists(os.path.join(plain, ".venv"))
    r = subprocess.run(["/bin/bash", os.path.join(plain, "start-mac.command"), "--which-python"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=60, env=dict(os.environ, EBRE_PYTHON=sys.executable))
    assert r.returncode == 0 and "Python" in r.stdout, r.stdout
    shutil.rmtree(base, ignore_errors=True)
    print("round-5 mac starter ok")


def test_round5_settings_powershell_env_and_protected_files():
    st = json.load(open(os.path.join(ROOT, ".claude", "settings.json")))
    allow, deny = st["permissions"]["allow"], st["permissions"]["deny"]
    assert any(x.startswith("PowerShell(") and "Scripts" in x for x in allow)
    assert any(x.startswith("Bash(") and ".venv/Scripts/python.exe" in x for x in allow)
    for t in ("Bash(* .env)", "PowerShell(* .env)", "Read(./.env)", "Edit(./suppress/**)", "Edit(./out/state/**)", "Edit(./**/consent_log.csv)",
              "Write(./suppress/**)"):
        assert t in deny, t
    assert any(x.startswith("PowerShell(") and "suppress" in x for x in deny)
    for t in ("Bash(rm *suppress/*)", "Bash(* >> *suppress/*)", "Bash(rm *out/state/*)", "Bash(* > *consent_log.csv*)", "PowerShell(Remove-Item *)",
              "PowerShell(Set-Content *suppress*)", "PowerShell(Out-File *out\\state*)"):
        assert t in deny, t
    # the kit's own scripts may still name those paths (e.g. --state-file out/state/seen_owners.json): no blanket path deny
    assert "Bash(* out/state/*)" not in deny and "PowerShell(* suppress*)" not in deny
    assert any(x.startswith("PowerShell(") and "consent_log" in x for x in deny)
    assert not any("suppress" in x or "out/state" in x for x in allow if x.startswith(("Edit", "Write")))
    print("round-5 settings ok")


def test_round5_phone_gating_hold_and_scrub_columns():
    d, ranked, traced = _traced("r5phone")
    base = ["--ranked", ranked, "--traced", traced, "--as-of", "2026-11-19"]
    m = quiet(build_marketing_lists.main, base)
    assert all(not x["phone1"] for x in m["crm"])  # nothing scrubbed: no phone in the CRM import
    assert any(x["phone_status"] == build_marketing_lists.NOT_SCRUBBED for x in m["crm"])
    crm = rows(os.path.join(d, "marketing", "crm_import.csv"))
    assert "phone_status" in crm[0] and "call_window" in crm[0] and "unscrubbed_phones" not in crm[0]
    assert all(not x["phone1"] for x in crm)
    # a scrub row without scrubbed_by / vendor is not a complete scrub
    scrub = os.path.join(d, "scrub.csv")
    skip_trace.write_rows(scrub, [{"phone": "6145550122", "dnc": "N", "scrub_date": "2026-11-10", "lists_checked": "federal; state:none; internal",
                                   "scrubbed_by": "", "vendor": ""}])
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub])
    assert m["call"] == []
    skip_trace.write_rows(scrub, [{"phone": "6145550122", "dnc": "N", "scrub_date": "2026-11-10", "lists_checked": "federal; state:none; internal",
                                   "scrubbed_by": "Pat", "vendor": "self"}])
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub])
    assert [x["phone1"] for x in m["call"]] == ["6145550122"]
    crm = rows(os.path.join(d, "marketing", "crm_import.csv"))
    row = [x for x in crm if x["phone1"] == "6145550122"][0]
    assert row["phone_status"].startswith("scrubbed") and "Pat" in row["phone_status"]
    assert build_marketing_lists.MANUALLY_DIALED in open(os.path.join(d, "marketing", "cold_call.csv")).read()
    tmpl = open(os.path.join(ROOT, "templates", "dnc_scrub.csv")).read().strip().split(",")
    assert {"scrubbed_by", "vendor", "lists_checked"} <= set(tmpl)
    # hold: no phone or text output at all, and old lists are removed
    m = quiet(build_marketing_lists.main, base + ["--dnc-scrubbed", scrub, "--hold-phone-sms", "no file with entries in the suppress/ folder"])
    mk = os.path.join(d, "marketing")
    assert m["held"] and m["call"] == [] and m["sms"] == []
    assert not os.path.exists(os.path.join(mk, "cold_call.csv")) and not os.path.exists(os.path.join(mk, "sms.csv"))
    assert not os.path.exists(os.path.join(mk, "cold_call_NEEDS_SCRUB.csv"))
    held = open(os.path.join(mk, "PHONE_AND_SMS_HELD.txt")).read()
    assert build_marketing_lists.OPT_OUT_SENTENCE in held
    crm = rows(os.path.join(mk, "crm_import.csv"))
    assert all(not x["phone1"] and not x.get("sms_phone") for x in crm)
    assert any(x["phone_status"] == build_marketing_lists.HOLD_STATUS for x in crm)
    print("round-5 phone gating / hold ok")


def test_round5_call_window_area_code_and_verify():
    import area_codes
    import timezones
    assert len(area_codes.AREA_CODES) > 300 and area_codes.AREA_CODES["919"][0] == "NC"
    E, SUN = timezones.ESTIMATED, " Mon-Sat (Sundays / holidays: see sunday_holiday_rule)"
    LOC = timezones.LOCATION_NOT_ESTABLISHED
    z, _b = timezones.estimate("NC", "27601")
    w, basis, chk = timezones.call_window("NC", z, ["9195550134"])
    assert w == E + "8am-9pm Eastern" + SUN and chk.startswith("ok (estimate)") and LOC in chk, (w, chk)
    assert "G.S. 75-102" in basis or "75-102" in basis
    z, _b = timezones.estimate("FL", "33101")
    w, basis, chk = timezones.call_window("FL", z, ["8505550134"])  # 850 covers Eastern and Central; FL ends at 8pm
    assert w == E + "9am-8pm Eastern (= 8am-7pm Central)" + SUN and chk.startswith("VERIFY") and "FL" in basis, (w, chk)
    z, _b = timezones.estimate("CA", "94105")
    w, basis, chk = timezones.call_window("CA", z, ["2125550134"])  # NY number, CA owner: legal in both
    assert w == E + "8am-6pm Pacific (= 11am-9pm Eastern)" + SUN and chk.startswith("VERIFY"), (w, chk)
    assert "federal window; CA, NY hours not coded, VERIFY" in chk
    # an uncoded state never gets "ok", even when the signals agree
    w, basis, chk = timezones.call_window("AZ", timezones.estimate("AZ", "85001")[0], ["6025550134"])
    assert chk.startswith("VERIFY") and "federal window; AZ hours not coded, VERIFY" in chk and w.startswith(E + "8am-9pm"), (w, chk)
    w, basis, chk = timezones.call_window("OH", timezones.estimate("OH", "43215")[0], ["6145550134"])
    assert chk.startswith("VERIFY") and "OH hours not coded" in chk
    assert timezones.call_window("NC", "Eastern", [])[2].startswith("ok so far")  # no phone yet: not "agree"
    w, basis, chk = timezones.call_window("", None, [])
    assert chk.startswith("VERIFY")
    # every coded state: source, last-checked date, and the window it produces
    for st in ("TX", "LA", "MS", "AL", "NC", "VA", "MD"):
        h = timezones.STATE_HOURS[st]
        assert h["source"] and h["checked"] == "2026-11-19" and h["note"], st
    for st, zp, ph, want in (("TX", "75201", "2145550134", "9am-9pm Central"), ("LA", "70112", "5045550134", "8am-8pm Central"),
                             ("MS", "39201", "6015550134", "9am-8pm Central"), ("AL", "35203", "2055550134", "8am-8pm Central"),
                             ("VA", "23219", "8045550134", "8am-9pm Eastern"), ("MD", "21201", "4105550134", "8am-8pm Eastern")):
        w, basis, chk = timezones.call_window(st, timezones.estimate(st, zp)[0], [ph])
        assert w == E + want + SUN and chk.startswith("ok (estimate)") and "last checked 2026-11-19" in basis, (st, w, chk)
    # Sunday / holiday flag
    assert timezones.sunday_holiday("TX") == "TX: Sunday noon-9pm only; no state holiday rule coded"
    assert "no calls on Sunday" in timezones.sunday_holiday("LA") and "legal holidays" in timezones.sunday_holiday("LA")
    assert "no calls on Sunday" in timezones.sunday_holiday("MS") and "no calls on Sunday" in timezones.sunday_holiday("AL")
    assert "legal holidays" in timezones.sunday_holiday("AL")
    assert timezones.sunday_holiday("OH") == "OH: Sunday / holiday rules not coded, VERIFY"
    assert "TX" in timezones.sunday_holiday("NC", ["2145550134"])  # a TX area code brings in TX's Sunday rule
    assert "power, predictive or multi-line" in timezones.MANUALLY_DIALED
    tm = open(os.path.join(ROOT, "templates", "call_review.csv")).read()
    assert "hours_verified" in tm
    print("round-5 call window ok")


def test_round5_suppression_cumulative_and_manual_add():
    import suppression
    d = out("r5sup")
    master = os.path.join(d, "state", "suppression.csv")
    a = os.path.join(d, "a.csv")
    skip_trace.write_rows(a, [{"phone": "6145550101", "address": "", "owner": "", "date": "2026-11-18", "channel": "all", "reason": "x"}])
    suppression.merge(master, [a])
    os.remove(a)  # the export is gone next week: the row must stay
    suppression.merge(master, [])
    assert [r["phone"] for r in rows(master)] == ["6145550101"]
    folder = os.path.join(d, "suppress")
    p = suppression.add(folder, phone="(614) 555-0102", reason="asked on a call", by="Pat")
    p2 = suppression.add(folder, owner="JANE SAMPLE", channel="mail", by="Lee")
    assert p == p2 and len(rows(p)) == 2 and rows(p)[0]["phone"] == "6145550102" and rows(p)[0]["logged_by"] == "Pat"
    quiet(suppression.main, ["add", "--address", "9 Sample Rd", "--folder", folder, "--by", "Pat"])
    assert len(rows(p)) == 3
    files, age, info = suppression.drop_folder(folder)
    assert files == [p] and age is None, "manual_requests.csv is applied but is not a current system export"
    src = open(os.path.join(ROOT, "scripts", "suppression.py")).read()
    assert "never remove" in src.lower() and "Refusing to shrink" in src
    assert suppression.OPT_OUT_SENTENCE == ("Import the latest opt-outs and do-not-contact requests from every system where your team "
                                            "communicates with these owners.")
    sk = open(os.path.join(ROOT, "SKILL.md")).read()
    assert "never remove a suppression row" in sk and suppression.OPT_OUT_SENTENCE in sk and "suppression.py add" in sk
    print("round-5 suppression ok")


def test_round5_voice_estate_wholesaling_and_license_text():
    v = build_marketing_lists.VOICE_LINE
    assert v == ("Live, manually dialed calls only. This kit does not support ringless voicemail, voicemail drops, prerecorded or AI voice, "
                 "or autodialers to any number; those need prior express written consent and separate legal review. Some states "
                 "(e.g. FL, OK) have their own autodialer laws.")
    for fn in ("SKILL.md", "SETUP.md", "CLAUDE.md"):
        assert v in open(os.path.join(ROOT, fn)).read().replace("\n  ", " "), fn
    sk = open(os.path.join(ROOT, "SKILL.md")).read()
    assert build_marketing_lists.MANUALLY_DIALED in sk and "STATE_AND_JURISDICTION_CHECK.md" in sk
    assert build_marketing_lists.ESTATE_RULE in sk and build_marketing_lists.DATA_LICENSE_LINE in sk
    assert sk == open(os.path.join(ROOT, ".claude", "skills", "development-opportunity-finder", "SKILL.md")).read()
    d, ranked, traced = _traced("r5comp")
    quiet(build_marketing_lists.main, ["--ranked", ranked, "--traced", traced, "--as-of", "2026-11-19"])
    comp = open(os.path.join(d, "marketing", "COMPLIANCE.md")).read()
    for t in ("wholesal", "STATE_AND_JURISDICTION_CHECK.md", build_marketing_lists.DATA_LICENSE_LINE, build_marketing_lists.ESTATE_RULE,
              build_marketing_lists.OPT_OUT_SENTENCE, "10DLC", "calling hours"):
        assert t in comp, t
    camp = out("r5camp")
    quiet(campaign_kit.main, ["--marketing-dir", os.path.join(d, "marketing"), "--output-dir", camp, "--state", "PA"])
    chk = open(os.path.join(camp, "STATE_AND_JURISDICTION_CHECK.md")).read()
    assert "PA" in chk and "wholesal" in chk.lower()
    est = open(os.path.join(camp, "estate_letter.txt")).read().lower()
    assert "personal representative" in est and "family can sell" not in est and "heirs can sell" not in est
    cl = open(os.path.join(camp, "campaign_checklist.md")).read()
    for t in ("10DLC", "consent", "calling hours", "DNC"):
        assert t.lower() in cl.lower(), t
    print("round-5 voice / estate / wholesaling / license ok")


def test_round5_buy_box_criteria_and_preset_labels():
    d = out("r5bb")
    box = quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01", "--output-dir", d])
    js = json.load(open(os.path.join(d, "buy_box.json")))
    crit = js["criteria"]
    names = [c["criterion"] for c in crit]
    assert {"Size", "Zoning", "Flood", "Price"} <= {n.split()[0] for n in names}, names
    assert any(c["source"] == "EBRE default, not derived from your county" for c in crit)
    assert all("supporting_purchases" in c for c in crit)
    summ = open(os.path.join(d, "buy_box_summary.md")).read()
    assert "Buy box criteria and how much supports each one" in summ and "EBRE default, not derived from your county" in summ
    d2 = out("r5bb_low")
    src = rows(os.path.join(S, "sample_developer_sales.csv"))
    few = os.path.join(d2, "few.csv")
    skip_trace.write_rows(few, src[:4], list(src[0].keys()))
    quiet(build_buy_box.main, ["--sales", few, "--as-of", "2026-11-01", "--min-sales", "3", "--output-dir", d2])
    s2 = open(os.path.join(d2, "buy_box_summary.md")).read()
    assert "LOW" in s2 and "Buy box criteria" in s2
    print("round-5 buy box criteria ok")


def test_round5_tiebreak_and_motivation_signal_table():
    d1, s1 = _scored("r5tie1")
    d2, s2 = _scored("r5tie2")
    r1 = [(x["rank"], x["apn"]) for x in rows(os.path.join(d1, "parcels_ranked.csv"))]
    r2 = [(x["rank"], x["apn"]) for x in rows(os.path.join(d2, "parcels_ranked.csv"))]
    assert r1 == r2
    ranked = [x for x in rows(os.path.join(d1, "parcels_ranked.csv")) if x["rank"]]
    assert "tiebreak" in ranked[0]
    # parcels with the same priority are ordered by the documented keys, ending with APN
    for a_, b_ in zip(ranked, ranked[1:]):
        assert float(a_["priority"]) >= float(b_["priority"])
    sig = rows(os.path.join(d1, "motivation_signals.csv"))
    assert sig and {"signal", "source", "collected_this_run", "when_not_available"} <= set(sig[0])
    assert s1["motivation_signal_table"] and "ties_in_top" in s1
    # a full tie: two identical parcels with different APNs are ordered by APN, every run
    par = rows(os.path.join(S, "sample_parcels.csv"))
    twin = [dict(par[0]), dict(par[0])]
    apn_col = [k for k in par[0] if k.lower() in ("apn", "parcel_id", "pin")][0]
    twin[0][apn_col], twin[1][apn_col] = "Z-200", "A-100"
    p = os.path.join(d1, "twins.csv")
    skip_trace.write_rows(p, twin, list(twin[0].keys()))
    quiet(score_parcels.main, ["--input", p, "--use-case", "single_family", "--buy-box", os.path.join(d1, "buy_box.json"), "--output-dir", os.path.join(d1, "tw")])
    tw = [x for x in rows(os.path.join(d1, "tw", "parcels_ranked.csv")) if x["rank"]]
    if len(tw) == 2:
        assert [x["apn"] for x in tw] == ["A-100", "Z-200"] and tw[1]["tiebreak"]
    print("round-5 tiebreak / motivation signals ok")


def test_round5_zero_feature_layers_are_unknown():
    import enrich_constraints
    import fetch_infrastructure
    d = out("r5zero")
    old = (fetch_infrastructure.query, fetch_infrastructure.arcgis_features, fetch_infrastructure.time.sleep)
    fetch_infrastructure.query = lambda ql, timeout, mirrors=None: {"elements": []}
    fetch_infrastructure.arcgis_features = lambda url, bbox, timeout, where=None: []
    fetch_infrastructure.time.sleep = lambda s: None
    try:
        res = quiet(fetch_infrastructure.main, ["--bbox", "39.9,-83.1,40.0,-83.0", "--layers", "substation,rail", "--output", os.path.join(d, "infra.csv")])
    finally:
        fetch_infrastructure.query, fetch_infrastructure.arcgis_features, fetch_infrastructure.time.sleep = old
    side = json.load(open(os.path.join(d, "infra.sources.json")))
    assert all(v == fetch_infrastructure.ZERO_FEATURES for v in side["layers"].values()), side
    assert res["points_written"] == 0
    # NWI answering with 0 features for every parcel: wetlands unknown, not 0%
    par = [{"apn": f"P{i}", "lat": 39.95 + i * 0.001, "lon": -83.05, "acres": 10} for i in range(6)]
    pin = os.path.join(d, "p.csv")
    skip_trace.write_rows(pin, par, ["apn", "lat", "lon", "acres"])
    old = (enrich_constraints.polys, enrich_constraints.elev)
    enrich_constraints.polys = lambda url, pts, fields: []
    enrich_constraints.elev = lambda pt: 900.0
    try:
        r = quiet(enrich_constraints.main, ["--input", pin, "--output", os.path.join(d, "e.csv")])
    finally:
        enrich_constraints.polys, enrich_constraints.elev = old
    assert r["nwi_zero_everywhere"]
    er = rows(os.path.join(d, "e.csv"))
    assert all(x["wetlands_pct_est"] == "" and "NWI" in x["constraint_notes"] for x in er)
    assert all(x["fema_zones"] == "UNMAPPED" and x["fema_flood_pct"] == "" for x in er)
    print("round-5 zero-feature layers ok")


def test_round5_satellite_age_coverage_and_no_imagery_flags():
    d, _ = _scored("r5sat")
    ranked = os.path.join(d, "parcels_ranked.csv")
    assert satellite_check.age_sentence(2022, __import__("datetime").date(2026, 11, 19)) == \
        "Imagery is from 2022, about 4 years old. Check current imagery before an offer."

    def fake(url):
        if "/identify?" in url:
            return json.dumps({"catalogItems": {"features": [{"attributes": {"Year": 2022}}]}}).encode()
        if "fail" in url:
            raise OSError("down")
        return _blank_jpeg()
    rev = satellite_check.main(["--ranked", ranked, "--top", "3", "--output-dir", os.path.join(d, "sat")], fetcher=fake)
    tier_a = {int(float(r["rank"])) for r in rows(ranked) if r.get("rank") and r["tier"].startswith("A")}
    assert {1, 2, 3} | tier_a <= {x["rank"] for x in rev}
    with_img = [x for x in rev if x["image_file"]]
    assert with_img and all(x["imagery_age"].startswith("Imagery is from 2022, about") and not x["imagery_flag"] for x in with_img)
    assert all(x["imagery_flag"] for x in rev if not x["image_file"])
    summ = open(os.path.join(d, "sat", "imagery_summary.txt")).read()
    assert "Imagery is from 2022" in summ and "Check current imagery before an offer." in summ

    def flat(url):
        from PIL import Image
        if "/identify?" in url:
            return json.dumps({"catalogItems": {"features": [{"attributes": {"Year": 2022}}]}}).encode()
        buf = io.BytesIO()
        Image.new("RGB", (600, 600), (255, 255, 255)).save(buf, "JPEG")
        return buf.getvalue()
    rev = satellite_check.main(["--ranked", ranked, "--top", "2", "--all-tiers", "", "--output-dir", os.path.join(d, "sat2")], fetcher=flat)
    assert len(rev) == 2 and all("NO IMAGERY" in x["imagery_flag"] for x in rev)
    assert "No usable imagery for 2" in open(os.path.join(d, "sat2", "imagery_summary.txt")).read()
    print("round-5 satellite age / no-imagery ok")


def test_round5_pipeline_enrichment_and_start_here():
    d = out("r5run")
    sup = out("r5sup2")
    seen = {}
    real = run_pipeline.enrich_constraints.main

    def fake_enrich(argv):
        a = dict(zip(argv[::2], argv[1::2]))
        src = rows(a["--input"])
        seen.setdefault("calls", []).append([r.get("apn") for r in src[: int(a["--limit"])]])
        for r in src[: int(a["--limit"])]:
            r.update(fema_flood_pct="0", fema_zones="X", wetlands_pct_est="0", slope_pct_est="2", buildable_pct_est="100",
                     constraint_check="ok")
        skip_trace.write_rows(a["--output"], src, list(dict.fromkeys(k for r in src for k in r)))
        return {"checked": int(a["--limit"]), "ok": int(a["--limit"]), "output": a["--output"], "nwi_zero_everywhere": False}
    run_pipeline.enrich_constraints.main = fake_enrich
    argv = ["--parcels", os.path.join(S, "sample_parcels.csv"), "--sales", os.path.join(S, "sample_developer_sales.csv"),
            "--infra", os.path.join(S, "sample_infrastructure.csv"), "--config", LAND_CFG, "--state", "OH",
            "--skiptrace-results", os.path.join(S, "sample_skiptrace_results.csv"), "--as-of", "2026-11-01",
            "--satellite", "links", "--suppress-dir", sup, "--output-dir", d, "--enrich-top", "3"]
    try:
        quiet(run_pipeline.main, argv)
    finally:
        run_pipeline.enrich_constraints.main = real
    ranked = [x for x in rows(os.path.join(d, "parcels_ranked.csv")) if x["rank"]]
    first = seen["calls"][0]
    assert len(first) == 3, "round 1 looks up the --enrich-top parcels"
    assert len(seen["calls"]) >= 2, "the top 10 after rescoring were not all checked in round 1, so it must repeat"
    # Blocker 2: after the loop, no tier-A or top-10 row may have a blank flood, wetlands or slope value
    must = [x for x in ranked if x["tier"].startswith("A")] + ranked[:10]
    assert must
    for x in must:
        for k in ("flood", "wetlands", "slope"):
            assert x[k + "_screen"].strip(), (x["apn"], x["rank"], x["tier"], k)
        assert not x["constraints_unchecked"], x["apn"]
    looked = {apn for call in seen["calls"] for apn in call}
    assert {x["apn"] for x in must} <= looked
    assert all(x["tier"] != "A - call first" for x in ranked) and any(x["tier"] == "A - research first" for x in ranked)
    assert os.path.exists(os.path.join(d, "parcels_enriched.csv"))
    start = open(os.path.join(d, "START_HERE.md")).read()
    assert "looked up for the top 3" in start
    from _common import PRIVACY_PARAGRAPH, SKIPTRACE_LINE
    assert PRIVACY_PARAGRAPH in " ".join(start.split()) and SKIPTRACE_LINE in start
    assert "A - research first" in start or "research first" in start
    assert build_marketing_lists.OPT_OUT_SENTENCE in start and "every phone and text output is held" in start
    assert os.path.exists(os.path.join(d, "marketing", "PHONE_AND_SMS_HELD.txt"))
    assert not os.path.exists(os.path.join(d, "marketing", "cold_call.csv"))
    assert "STATE_AND_JURISDICTION_CHECK.md" in start and "Owner motivation signals" in start and "Buy box criteria" in start
    assert "AERIAL IMAGERY" in start
    assert os.path.exists(os.path.join(d, "campaign", "STATE_AND_JURISDICTION_CHECK.md"))
    # demo: no enrichment, no hold
    print("round-5 pipeline enrichment / START_HERE ok")


def test_round5_batchdata_experimental_and_docs():
    st = open(os.path.join(ROOT, "scripts", "skip_trace.py")).read()
    assert "EXPERIMENTAL" in st
    setup = open(os.path.join(ROOT, "SETUP.md")).read()
    for t in ("paid Claude plan", "Run the sample first", "setup_check.txt` in the kit folder", "Optional paid services (not needed for basic use)",
              "EXPERIMENTAL"):
        assert t in setup, t
    kl = open(os.path.join(ROOT, "KNOWN_LIMITS.md")).read()
    assert "EXPERIMENTAL" in kl and "has not been run yet" in kl
    print("round-5 BatchData label / docs ok")



# ------------------------------------------------------------------ round 6
def _nc_owner(name):
    """Sample run with one owner (SAMPLE OWNER 38) moved to Raleigh NC with a 919 number and a complete DNC scrub."""
    d, _ = _scored(name)
    ranked = os.path.join(d, "parcels_ranked.csv")
    rk = rows(ranked)
    for x in rk:
        if x["owner"].upper().startswith("SAMPLE OWNER 38") and "43000" in x["mail_zip"]:
            x["mail_state"], x["mail_zip"], x["mail_city"] = "NC", "27601", "RALEIGH"
    skip_trace.write_rows(ranked, rk, list(rk[0].keys()))
    quiet(skip_trace.main, ["export", "--ranked", ranked])
    quiet(skip_trace.main, ["import", "--ranked", ranked, "--results", os.path.join(S, "sample_skiptrace_results.csv")])
    tr = os.path.join(d, "skiptrace", "owners_traced.csv")
    t = rows(tr)
    for x in t:
        if x["owner_key"].startswith("sampleowner38|"):
            x["phone1"], x["phone1_type"], x["phone1_dnc"] = "9195550123", "Mobile", ""
    skip_trace.write_rows(tr, t, list(t[0].keys()))
    scrub = os.path.join(d, "scrub.csv")
    skip_trace.write_rows(scrub, [{"phone": "9195550123", "dnc": "N", "scrub_date": "2026-11-10", "lists_checked": "federal; state:none; internal",
                                   "scrubbed_by": "Pat (test)", "vendor": "self (own SAN)"}])
    return d, ["--ranked", ranked, "--traced", tr, "--as-of", "2026-11-19", "--dnc-scrubbed", scrub,
                "--state-file", os.path.join(d, "state", "seen_owners.json")]


def test_round6_hours_verified_required_even_when_ok():
    d, base = _nc_owner("r6hv")
    m = quiet(build_marketing_lists.main, base)
    r = [x for x in m["call"] if x["phone1"] == "9195550123"][0]
    assert r["call_window"].startswith("estimated window: 8am-9pm Eastern") and "verified" not in r["call_window"].lower()
    assert r["call_window_check"].startswith("ok (estimate)") and "current location not established" in r["call_window_check"]
    assert r["sunday_holiday_rule"].startswith("NC:") and r["hours_verified"] == ""
    rv = os.path.join(d, "review.csv")
    skip_trace.write_rows(rv, [{"phone": "9195550123", "call_eligibility": "reviewed_for_campaign", "reviewed_by": "Pat", "review_date": "2026-11-18"}])
    m = quiet(build_marketing_lists.main, base + ["--call-review", rv])
    r = [x for x in m["call"] if x["phone1"] == "9195550123"][0]
    assert r["call_eligibility"] == "needs_review", "an 'ok' estimate still needs a person to verify local time"
    assert "add hours_verified = Y" in r["call_window_check"]
    skip_trace.write_rows(rv, [{"phone": "9195550123", "call_eligibility": "reviewed_for_campaign", "reviewed_by": "Pat", "review_date": "2026-11-18",
                                "hours_verified": "Y"}])
    m = quiet(build_marketing_lists.main, base + ["--call-review", rv])
    r = [x for x in m["call"] if x["phone1"] == "9195550123"][0]
    assert r["call_eligibility"] == "reviewed_for_campaign" and r["hours_verified"] == "Y"
    cc = rows(os.path.join(d, "marketing", "cold_call.csv"))
    assert {"sunday_holiday_rule", "hours_verified", "motivation_note", "signals_not_checked"} <= set(cc[0].keys())
    comp = open(os.path.join(d, "marketing", "COMPLIANCE.md")).read()
    assert "Calling hours coded in this kit" in comp
    for st in ("TX", "LA", "MS", "AL", "NC", "VA", "MD"):
        assert f"| {st} |" in comp and "2026-11-19" in comp, st
    assert "hours not coded, VERIFY" in comp
    from _common import PRIVACY_PARAGRAPH
    assert PRIVACY_PARAGRAPH in " ".join(comp.split()) and "safeguard, not a guarantee" in comp
    print("round-6 hours_verified / coded hours ok")


def test_round6_state_check_record_nc_va_md():
    import state_rules, campaign_kit
    for st in ("NC", "VA", "MD"):
        n = state_rules.STATE_NOTES[st]
        assert n["checked"] == state_rules.CHECKED == "2026-11-19" and n["source"] and n["law"] and n["license"] and n["disclosures"], st
    assert "93A" in state_rules.STATE_NOTES["NC"]["source"] and "54.1-2100" in state_rules.STATE_NOTES["VA"]["source"]
    assert "10-715" in state_rules.STATE_NOTES["MD"]["source"]
    assert all(state_rules.STATE_NOTES[s]["checked"] == state_rules.CARRIED for s in ("PA", "IL", "OH", "OK", "TX"))
    for f in ("law_that_applies", "licensing_needed", "disclosures_apply", "verified_by", "verified_on"):
        assert f in state_rules.RECORD_FIELDS, f
    d, base = _nc_owner("r6sc")
    quiet(build_marketing_lists.main, base)
    quiet(campaign_kit.main, ["--marketing-dir", os.path.join(d, "marketing"), "--output-dir", os.path.join(d, "campaign"), "--state", "NC,VA,MD"])
    rec = rows(os.path.join(d, "campaign", "state_check_record.csv"))
    got = {r["state"]: r for r in rec}
    for st in ("NC", "VA", "MD"):
        assert st in got, (st, list(got))
        r = got[st]
        assert r["kit_source"] and r["kit_last_checked"] == "2026-11-19" and r["why_in_scope"]
        assert r["verified_by"] == "" and r["verified_on"] == "" and r["law_that_applies"] == "", "the user fills these in"
    chk = open(os.path.join(d, "campaign", "STATE_AND_JURISDICTION_CHECK.md")).read()
    assert "state_check_record.csv" in chk and "verified_by" in chk
    comp = open(os.path.join(d, "marketing", "COMPLIANCE.md")).read()
    assert "North Carolina" in comp and "Virginia" in comp and "Maryland" in comp
    cl = open(os.path.join(d, "campaign", "campaign_checklist.md")).read()
    from _common import DNC_NOT_CONSENT, SKIPTRACE_LINE
    assert DNC_NOT_CONSENT in cl and SKIPTRACE_LINE in cl and "10DLC" in cl
    print("round-6 state check record ok")


def test_round6_motivation_signal_states():
    import build_marketing_lists as bml
    d = out("r6sig")
    src = rows(os.path.join(S, "sample_parcels.csv"))
    cols = [c for c in src[0].keys() if c != "mortgage"]          # no mortgage column: not-checked
    for i, r in enumerate(src):
        r.pop("mortgage", None)
        if i % 2 == 0:
            r["tax_delinquent"] = ""                                  # column present, value blank: unavailable-from-source
    p = os.path.join(d, "parcels.csv")
    skip_trace.write_rows(p, src, cols)
    quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01", "--output-dir", d])
    quiet(score_parcels.main, ["--input", p, "--infra", os.path.join(S, "sample_infrastructure.csv"), "--use-case", "single_family",
                               "--buy-box", os.path.join(d, "buy_box.json"), "--output-dir", d])
    rk = rows(os.path.join(d, "parcels_ranked.csv"))
    states = set(score_parcels.SIG_STATES)
    for x in rk:
        for k in ("long_hold", "out_of_state", "out_of_county", "no_mortgage", "tax_delinquent", "estate_heirs", "trust", "multiple_owners"):
            assert x["sig_" + k] in states, (k, x["sig_" + k])
        assert x["sig_no_mortgage"] == "not-checked"
        assert "no mortgage" in x["signals_not_checked"]
    assert any(x["sig_tax_delinquent"] == "unavailable-from-source" for x in rk)
    assert any(x["sig_tax_delinquent"] in ("present", "checked-not-present") for x in rk)
    # owner level: present wins; checked-not-present only when every parcel was checked
    assert bml.merge_signal(bml.merge_signal(None, "checked-not-present"), "present") == "present"
    assert bml.merge_signal(bml.merge_signal(None, "checked-not-present"), "not-checked") == "not-checked"
    assert bml.merge_signal(bml.merge_signal(None, "checked-not-present"), "unavailable-from-source") == "unavailable-from-source"
    assert bml.merge_signal(bml.merge_signal(None, "checked-not-present"), "checked-not-present") == "checked-not-present"
    note = bml.motivation_note({"sig": {k: ("not-checked" if k == "no_mortgage" else "checked-not-present") for k in bml.SIG_KEYS}})
    assert "not 'unmotivated'" in note and "no signal present" in note
    assert bml.motivation_note({"sig": {}}).count("not checked") >= 1  # nothing known: never "unmotivated"
    # a missing signal never reads as unmotivated in the owner-level exports
    quiet(skip_trace.main, ["export", "--ranked", os.path.join(d, "parcels_ranked.csv")])
    quiet(skip_trace.main, ["import", "--ranked", os.path.join(d, "parcels_ranked.csv"), "--results", os.path.join(S, "sample_skiptrace_results.csv")])
    m = quiet(build_marketing_lists.main, ["--ranked", os.path.join(d, "parcels_ranked.csv"), "--traced",
                                           os.path.join(d, "skiptrace", "owners_traced.csv"), "--as-of", "2026-11-19"])
    crm = rows(os.path.join(d, "marketing", "crm_import.csv"))
    for x in crm:
        assert x["sig_no_mortgage"] == "not-checked" and "no mortgage" in x["signals_not_checked"], x["owner"]
        assert "unmotivated" not in x["motivation_note"].replace("not 'unmotivated'", ""), x["motivation_note"]
    mail = rows(os.path.join(d, "marketing", "mail_list.csv")) if os.path.exists(os.path.join(d, "marketing", "mail_list.csv")) else []
    for x in mail:
        if "sig_no_mortgage" in x:
            assert x["sig_no_mortgage"] == "not-checked"
    print("round-6 motivation signal states ok")


def test_round6_privacy_and_wording_in_every_doc():
    from _common import PRIVACY_PARAGRAPH, SKIPTRACE_LINE, DNC_NOT_CONSENT
    assert PRIVACY_PARAGRAPH == ("The kit's local scripts store and process owner data in your kit folder and do not send owner data to public "
                                 "map servers. However, when Claude Code reads file contents or includes them in prompts, that information may "
                                 "be transmitted to Anthropic for processing under your Claude plan or API account terms and settings. Only use "
                                 "this workflow with data you are authorized to share with that service. Keep API keys in the local .env file "
                                 "and never paste them into chat.")
    assert SKIPTRACE_LINE == "Bring skip-trace results back through the kit before dialing. Never load the vendor file straight into your dialer."
    flat = lambda t: " ".join(t.split())
    for doc in ("SECURITY.md", "SETUP.md", "SKILL.md", "CLAUDE.md", "README.md", "KNOWN_LIMITS.md",
                os.path.join(".claude", "skills", "development-opportunity-finder", "SKILL.md")):
        t = flat(open(os.path.join(ROOT, doc)).read())
        assert PRIVACY_PARAGRAPH in t, doc
    bad = ("stays on this computer", "stay on this computer", "stays on your computer", "data stays on", "never uploads",
           "stays in this folder", "what stays local", "nothing leaves")
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git", "out", "out_demo", ".venv", "tests")]
        for fn in files:
            if fn.endswith((".md", ".py", ".txt", ".command", ".bat", ".json")):
                low = open(os.path.join(root, fn), encoding="latin-1").read().lower()
                for b in bad:
                    assert b not in low, (fn, b)
    for st in ("start-mac.command", "start-windows.bat"):
        t = open(os.path.join(ROOT, st), encoding="latin-1").read()
        head = t.split("Folder:")[0]  # the first screen, before anything runs
        echo = flat(" ".join(l.split("echo", 1)[1].strip().strip('"') for l in head.splitlines() if l.strip().startswith("echo")))
        assert flat("PRIVACY: " + PRIVACY_PARAGRAPH) in echo, st
        assert "safeguard, not a guarantee" in echo, st
    for doc in ("SECURITY.md", "SKILL.md", "CLAUDE.md", "SETUP.md"):
        t = flat(open(os.path.join(ROOT, doc)).read())
        assert "not a guarantee" in t or "not guarantees" in t, doc
    for doc in ("SKILL.md", "SETUP.md", "CLAUDE.md"):
        assert SKIPTRACE_LINE in flat(open(os.path.join(ROOT, doc)).read()), doc
    assert SKIPTRACE_LINE in open(os.path.join(ROOT, "scripts", "skip_trace.py")).read() or "SKIPTRACE_LINE" in open(os.path.join(ROOT, "scripts", "skip_trace.py")).read()
    for doc in ("SKILL.md", "SETUP.md"):
        assert DNC_NOT_CONSENT in flat(open(os.path.join(ROOT, doc)).read()), doc
    assert "10DLC registration is a separate requirement" in DNC_NOT_CONSENT and "A DNC scrub is not consent" in DNC_NOT_CONSENT
    setup = open(os.path.join(ROOT, "SETUP.md")).read()
    assert "Open Anyway" in setup and "Control-click" in setup and "no longer" in setup and "to be confirmed by the home-machine run" in setup
    assert setup.count("[Screenshot placeholder") >= 6 and "More info" in setup and "Run anyway" in setup
    sc = open(os.path.join(ROOT, "references", "scoring.md")).read()
    assert "A - research first" in sc and "call first" not in sc
    # nothing a test or a mistyped flag wrote may sit in the kit folder (it would ship in the zip)
    allowed = {".claude", ".gitignore", "CLAUDE.md", "KNOWN_LIMITS.md", "LICENSE", "README.md", "SECURITY.md", "SETUP.md",
               "SHA256SUMS.txt", "SKILL.md", "config", "dof", "references", "requirements.txt", "samples", "scripts",
               "start-mac.command", "start-windows.bat", "suppress", "templates", "tests", "tools",
               ".venv", "out", "out_demo", "output", "setup_check.txt", "__pycache__", ".DS_Store", "development-opportunity-finder.zip"}
    extra = sorted(set(os.listdir(ROOT)) - allowed)
    assert not extra, f"unexpected files in the kit folder: {extra}"
    print("round-6 privacy / wording ok")


def test_round6_skiptrace_line_buy_box_size_and_start_here():
    d = out("r6bb")
    quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01", "--min-sales", "50",
                               "--output-dir", d])
    box = json.load(open(os.path.join(d, "buy_box.json")))
    size = [c for c in box["criteria"] if c["criterion"].startswith("Size")][0]
    pre = json.load(open(os.path.join(ROOT, "references", "use-cases.json")))
    assert size["value"].startswith("EBRE default ") and "county purchases seen; 50 needed to set from data" in size["value"], size["value"]
    d2 = out("r6bb2")
    quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01", "--output-dir", d2])
    b2 = json.load(open(os.path.join(d2, "buy_box.json")))
    s2 = [c for c in b2["criteria"] if c["criterion"].startswith("Size")][0]
    assert s2["value"].startswith(f"{b2['acres']['min']}-{b2['acres']['max']} ac from your sales"), s2["value"]
    from _common import SKIPTRACE_LINE
    d3 = out("r6st")
    quiet(build_buy_box.main, ["--sales", os.path.join(S, "sample_developer_sales.csv"), "--as-of", "2026-11-01", "--output-dir", d3])
    quiet(score_parcels.main, ["--input", os.path.join(S, "sample_parcels.csv"), "--infra", os.path.join(S, "sample_infrastructure.csv"),
                               "--use-case", "single_family", "--buy-box", os.path.join(d3, "buy_box.json"), "--output-dir", d3])
    quiet(skip_trace.main, ["export", "--ranked", os.path.join(d3, "parcels_ranked.csv")])
    assert SKIPTRACE_LINE in open(os.path.join(d3, "skiptrace", "README_UPLOAD.txt")).read()
    print("round-6 skip-trace line / buy-box size ok")

if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print("ok")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
