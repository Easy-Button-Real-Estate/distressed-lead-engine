---
name: development-opportunity-finder
description: Screen county land parcels against recent developer purchase patterns. Builds a buy box from recorded land sales (with evidence counts and a confidence level), scores parcels with a per-parcel explanation, saves NAIP aerials of the top parcels, lists owners and signals, prepares skip-trace files, and builds blocked-by-default mail, call and CRM-import lists plus campaign copy. Sends nothing. Use for "run the demo", "set this up for my county", "refresh my county", "build a buy box", "score these parcels", "skip trace these owners", "get this ready for marketing", "write the campaign", lot splits or ADUs.
---

# Development Opportunity Finder (land for developers)

You are helping a real estate operator, often non-technical. Do the work, explain it in plain words, lead with the answer.

**Where it runs:** the supported path is Claude Code on the user's own computer, started by double-clicking `start-mac.command` or `start-windows.bat` in this folder. Those create a private `.venv`. Always run the scripts with that Python:
- Mac: `.venv/bin/python scripts/<script>.py ...`
- Windows: `.venv/Scripts/python.exe scripts/<script>.py ...` (forward slashes: Claude Code runs commands in Git Bash when it is installed, where backslashes break. Without Git Bash, Claude Code uses PowerShell, where `.venv\Scripts\python.exe scripts\<script>.py` and the forward-slash form both work; settings.json allows both. In a plain cmd window use `.venv\Scripts\python.exe`.)
Below, `PY` means that path. If `.venv` is missing, ask the user to double-click the starter (or run `PY scripts/doctor.py --online` and read `setup_check.txt`). Outputs go to `out/` unless the user names another folder. Recommended kit folder: `~/EBRE-Land` (Mac) or `C:\EBRE-Land` (Windows); paths with spaces work. `.claude/settings.json` pre-approves only the kit's scripts and tests.

**Disclaimer (say it in one sentence with every result):** this is a screening tool. It points to land worth a closer look; public data has gaps; it does not predict profit or what a developer will pay, and it does not replace a survey, title search, appraisal or a zoning letter. Zoning must be verified with the city.

**Say this whenever you hand over lists:** "These are research and marketing preparation lists, not approved contact lists. Before launching a campaign, verify the applicable consent, suppression, registration, calling-hour and jurisdictional requirements."

## Be honest about what is automatic

- Automatic: the math (buy box, scoring, lot yield, owner grouping, lists), NAIP aerial images, and map / flood / wetlands / slope / infrastructure lookups **when the public sources are available**. If a source is down the run says "source unavailable; scoring continued without this factor" and START_HERE.md shows an UNKNOWN FACTORS banner. Unknown is never scored as good.
- Needs the user's data: a parcel file (PropStream export or county GIS) and a sales file for the buy box.
- Needs the user's account: phones and emails come from THEIR skip-trace provider (upload / download a CSV), or the optional, EXPERIMENTAL BatchData API with their own key (built from BatchData's public docs, not yet run against a live account). Nothing is scraped. No keys ship with this kit.
- Never automatic: mailing, calling, texting, pushing to a CRM, or scheduling. `crm_import.csv` is a CRM import file the user imports.
- Weekly runs: the user says "refresh my county" and you re-run the pipeline. Automatic scheduling needs separate setup; do not claim it is on.
- The claude.ai web chat can't reach county servers or imagery. If a fetch fails because the network is blocked, stop retrying and say so. Scoring an uploaded file still works.

## "Run the demo"

`PY scripts/run_pipeline.py --demo --satellite links`, then open `out_demo/START_HERE.md` and walk them through it. The demo writes only to `out_demo/` and never touches `out/state/` (seen owners, suppression list). Every parcel, owner, sale and phone number in it is made up; say so.

## "Set this up for <county / city, state>"

Ask only for what is missing, in one message: county and state, what their buyer builds, and whether they have a PropStream export (step 1 in SETUP.md). Then:

1. **Parcels.** Use their export, or search `"<county> county parcels arcgis rest"` for a public layer ending in `/MapServer/<n>` or `/FeatureServer/<n>`. `PY scripts/fetch_arcgis_parcels.py --layer-url URL --list-fields`, then `--bbox "S,W,N,E" --min-acres N --output parcels.csv`. This writes `parcels.geometry.json` (boundaries) and `sources/county_layer_license.txt` (the county's own licence / use text). Tell the user to read it.
2. **Sales for the buy box.** Best source: the county recorder's grantor-grantee index or a title company rep's sales report (recorded buyer + price). Otherwise the same layer filtered to recent sales or a PropStream sold export (weaker: current owner, not the recorded buyer). **Non-disclosure states** (TX, NM, UT, ID, WY, MT, ND, KS, MS, LA, AK, MO): use sold-land comps with `--state TX --price-only`, and say the buy box is land prices in general.
3. **Infrastructure:** `PY scripts/fetch_infrastructure.py --from-parcels parcels.csv --pad-miles 5 --output infra.csv`. It tries several OpenStreetMap (Overpass) servers, then falls back to US Census TIGER roads / rail / highway ramps (MTFCC S1630, used as interchanges) and re-hosted copies of the retired HIFLD transmission-line and substation layers (snapshots, not live data; HIFLD Open shut down in 2025). `--no-overpass` forces the fallback. Water / sewer plants have no fallback. Credit the sources.
4. **Lot-split / ADU config (single-family).** Fill `config/my-market.yaml` from the real zoning code. Every number must come from a page you opened, listed under `sources:` with the date. Unknown = `null`. Never guess.

## The pipeline

All steps: `PY scripts/run_pipeline.py --parcels parcels.csv --sales sales.csv --state <ST> --market "<County, ST>" --use-case single_family --infra infra.csv --config config/my-market.yaml --your-name "<name>" --company "<company>" --phone "<phone>"`. Add `--suppress suppress.csv`, `--stop-replies stop.csv`, `--dnc-scrubbed scrub.csv`, `--skiptrace-results <file>` when the user has them. By default the pipeline scores, looks up FEMA flood, NWI wetlands and USGS slope for the top 60 parcels, and scores again (`--enrich-top N`, 0 skips it; the demo never does). A layer that returns 0 features for the whole county is reported as unknown, never as "none".

### 1. Buy box
`PY scripts/build_buy_box.py --sales sales.csv --state <ST> --market "<County, ST>" --known-developers my_builders.txt`
`buy_box_summary.md` separates **verified grantee purchases** (recorded buyer confirmed by the user's Y in `buyers_review.csv` or their known-developers list), **keyword-inferred buyers** and **current-owner proxies**, with counts, what was left out, and limits. It says which parts came from the sales data and which from the preset. At LOW confidence say clearly: "this is a rough hint, not a real buy box". Say "matches recent developer purchase patterns", never "land developers want" or "what a developer will pay". Say "paid a premium (25%+ over the size-band median)", never "overpaid".

### 2. Score every parcel
`PY scripts/score_parcels.py --input parcels.csv --use-case <preset> --buy-box out/buy_box.json --infra infra.csv --market "<County, ST>" --output-dir out`
Each row has `score_explained`, `hard_gate_failures`, `missing_data`, `confidence_label`, `jurisdiction` and `research_next` (what to check next). Flood and wetlands are percent of parcel (FEMA / NWI screens from a 9-point sample; not a determination or delineation). Water / sewer is unknown without a utility layer; power is distance to mapped lines, not capacity. Owner-type exclusions (builder, HOA, utility, railroad, cemetery, church, government, conservation) only match entity-shaped names (LLC, Inc, church, association...), never a person's surname; they are listed in `excluded_owners.csv`. Tell the user which owner signals their data had (START_HERE.md lists them); a missing column means "not checked", not "no".
Shortlist constraints by hand (the pipeline already does the top 60): `PY scripts/enrich_constraints.py --input out/parcels_ranked.csv --output shortlist_enriched.csv --limit 150`, then score that file. Ties are broken the same way every run (more factors with data, land score, owner signals, acreage fit, then APN; see the `tiebreak` column). `motivation_signals.csv` lists each owner signal, its source, whether this run had it, and what happens when it is missing: tell the user which ones were not collected.
Lot yield: `PY scripts/add_split_adu_signals.py --parcels parcels.csv --ranked out/parcels_ranked.csv --config config/my-market.yaml`.

### 3. Aerial check
`PY scripts/satellite_check.py --ranked out/parcels_ranked.csv --top 10 --geometry parcels.geometry.json` saves USDA NAIP images (public domain) with the boundary in yellow; failures go to `satellite_errors.log`. It covers the top N plus every tier-A parcel. Each row has `imagery_age` (for example "Imagery is from 2022, about 4 years old. Check current imagery before an offer.") and `imagery_flag` for parcels with no usable imagery (no location, failed download, blank picture, unknown date): say the age sentence and list the flagged parcels. Esri and Google are view links only. Then YOU open each image and fill `satellite_review.csv`; every finding starts with "clearly visible:", "likely:" or "can't determine". Never claim legal access, easements, power lines or capacity from an image.

### 4. Owners and skip trace
`PY scripts/skip_trace.py export --ranked out/parcels_ranked.csv --tiers A,B` writes upload files per provider (generic format, check your provider's template) and `entities_to_research.csv`; suppressed owners are left out. Exported is not traced. `skip_trace.py import --ranked ... --results <file>` reads results back. BatchData API (EXPERIMENTAL; say so): refuses to run without `--price-per-record`; shows the cost preview; sends only with `--confirm` after the user says yes. Never ask for a key in chat.

### 5. Marketing lists (blocked by default)
`PY scripts/build_marketing_lists.py --ranked out/parcels_ranked.csv --traced out/skiptrace/owners_traced.csv --state-file out/state/seen_owners.json --dnc-scrubbed scrub.csv`
- Suppression: ask the user: "Import the latest opt-outs and do-not-contact requests from every system where your team communicates with these owners." Also log manual requests your employees receive (a call, letter, email or in person): add them to suppress/manual_requests.csv or run scripts/suppression.py add. Every CSV in the `suppress/` folder, plus `--suppress` and `--stop-replies`, is merged into `out/state/suppression.csv` and applied to every list on every run. Suppression is cumulative: **never remove a suppression row**, never edit or delete files in `suppress/`, `out/state/` or `consent_log.csv` (settings.json denies it). To log a manual request use `PY scripts/suppression.py add --phone ... --address ... --owner ... --channel all --reason "asked in person" --by "<name>"` (append-only). Phones match in any format ((919) 555-0134 = 9195550134 = +19195550134) and addresses are normalized (123 Main St = 123 MAIN STREET). START_HERE.md warns when there is no suppress file or the newest is over 7 days old, and **while that banner shows, every phone and text output is held** (no cold_call.csv, no sms.csv, phones blank in crm_import.csv, `PHONE_AND_SMS_HELD.txt` explains). Blank templates are in `templates/`.
- A complete DNC scrub = federal + the state's own list (if it has one) + the user's internal list, recorded in the scrub file's `lists_checked`, with `scrubbed_by` (who ran it) and `vendor` (which service, or "self"). A skip-trace provider's DNC flag is not a scrub. `cold_call.csv` only has numbers from a complete scrub in the last 31 days; all others go to `cold_call_NEEDS_SCRUB.csv` (blocked). `crm_import.csv` carries a phone only when it is scrubbed; otherwise the phone is blank and `phone_status` = "not scrubbed, do not dial". Rows have `line_type`, `time_zone` (an estimate from state + ZIP), `call_window` (the stricter window from the mailing ZIP/state and the phone's area code, 8am-9pm local, 8pm in FL/OK/MD), `call_window_check` ("VERIFY calling hours" when the signals disagree or the location is uncertain), `call_rules` and `call_eligibility` = needs_review until the user marks reviewed_for_campaign in `call_review.csv` (a VERIFY row also needs `hours_verified` = Y). Never call a scrubbed number "legal to call".
- Live, manually dialed calls only. This kit does not support ringless voicemail, voicemail drops, prerecorded or AI voice, or autodialers to any number; those need prior express written consent and separate legal review. Some states (e.g. FL, OK) have their own autodialer laws. Manually dialed means a person dials or clicks one number at a time, with no power, predictive or multi-line dialer.
- Never create, recommend, or launch a ringless voicemail campaign as part of this workflow. Ringless voicemail and prerecorded/artificial voice outreach require separate legal review and applicable consent verification. Do not assume a number eligible for ordinary calling is eligible for these methods.
- `sms.csv` only with `--sms --sms-sender "<their company>" --consent-file consent.csv` whose rows confirm this sender, this purpose, this method and where the proof is kept (`consent_evidence`); rows start as needs_review. A row with `revoked_date` is dropped and the number is added to the suppression list; `consent_log.csv` records what was accepted or rejected. Texting from a business number also needs 10DLC registration with the carrier (through their texting provider).
- `buyer_package.csv` (after scoring) is the buyer-facing export: parcel facts and scores only, no owner name, mailing address, phone or email.
- Point the user to `COMPLIANCE.md` (verify with counsel, registration, state wholesaling notes, data licensing). Before any campaign prep the user works through `campaign/STATE_AND_JURISDICTION_CHECK.md` (state wholesaling / assignment rules and local jurisdiction). Consent, 10DLC, DNC scrub and calling hours are separate checks, not covered by it.
- Verify the data license before redistribution or resale. County, PropStream and skip-trace data usually come with licence terms.

### 6. Campaign kit
`PY scripts/campaign_kit.py --marketing-dir out/marketing --your-name "<name>" --company "<company>" --phone "<phone>" --buyer "home builders"`
Offer letter, estate letter (estate / heirs owners only, addressed "Personal Representative, Estate of <name>"; living trusts get the standard letter), `STATE_AND_JURISDICTION_CHECK.md`. Never imply that an heir can sell. Before any offer on an estate-owned parcel, check the probate case (court and case number), that a personal representative has been appointed and holds current letters (testamentary or of administration), whether the court must approve the sale, and title (a title company confirms who can convey)., call opener, texts for consented numbers, load-in steps, checklist. Letters never contain a price. You do not send, dial, text or upload anything.

## Personal data
Owner names, addresses, phones and emails stay on this computer. Never ask for or accept API keys in chat (the user types them into `.env`), never read `.env`, never upload lists to services unrelated to the user's own provider or CRM. Old exports: `PY scripts/cleanup_exports.py` lists files over 90 days old (`--delete` removes them); it never touches the suppression list, consent log or call reviews, which are kept at least 5 years. Verify the data license before redistribution or resale. Before a county run, `fetch_arcgis_parcels.py` flags licence text mentioning non-commercial use, resale or fees: tell the user.

## What you owe the user after a run
1. Parcels scored, how many passed, main exclusions, top 5 with one line each (why, owner signals, research next).
2. The buy-box read with its evidence counts and confidence (or "price-only").
3. Any UNKNOWN FACTORS, SUPPRESSION or held-phone banner, the imagery age sentence and parcels with no imagery, and which owner signals were not collected, in plain words.
4. The files: START_HERE.md, workbook, reports, lists.
5. Next three steps, and the one-sentence disclaimer.

## House-level screen (the original tool)
"Screen this list" on a house list: `PY -m dof.run --csv <file> --config config/my-market.yaml`, read `output/summary.txt`.

## Limits
- Never promise a deal, a profit, a price, or a buyer. Value ranges are screening numbers.
- Don't contact owners, send mail or texts, or skip-trace on your own. Outreach compliance is the user's; tell them to verify with counsel.
- Don't log into or scrape paid sites or people-search sites.
- Score the land, never the people who live nearby.
- Credit OpenStreetMap (ODbL), USDA NAIP, US Census TIGER and the HIFLD re-hosts in anything shared. See KNOWN_LIMITS.md.
