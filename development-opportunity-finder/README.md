# Development Opportunity Finder (free Claude skill)

> **Screening tool only.** Public data has gaps. It won't predict profit or replace a survey, title search,
> appraisal or zoning letter.

Find land that matches recent developer purchase patterns in your county, and get the owners ready to contact. It runs in Claude Code on your own computer (started by the double-click starter), on public data and your own
PropStream export. It prepares files; it never mails, calls or texts anyone.

Start with **SETUP.md** (4 steps). Then say "run the demo".

## What it does (6 steps)

| Step | What happens | How automatic |
|---|---|---|
| 1. Buy box | Reads recent land sales, keeps deeds bought by builders / developers (a built-in name list, your `known_developers` list, and your Y/N in `buyers_review.csv`), groups multi-parcel deeds into one purchase, and works out size, $/acre, $/lot, zoning and ZIPs over the last 36 months. Flags deeds that **paid a premium (25%+ over the size-band median)**. Shows evidence counts (verified grantee purchases vs keyword-inferred buyers vs current-owner proxies), what came from the preset, and a confidence level. | Automatic once you have a sales file. **Non-disclosure states (TX, UT, KS, MO and others):** no public prices, so it runs in price-only mode from sold comps or listings and says the result is land prices in general, not developer buys. |
| 2. Score parcels | Scores each parcel 0-100 against the buy box: size, access, highway, power (distance to mapped lines, not capacity), rail, water / sewer (only from a layer you supply, else "unknown"), zoning, FEMA flood (unmapped = unknown), NWI wetlands (screen only), slope, price vs the buy box, near developer buys. Every parcel gets a plain-English explanation: points per category, hard-gate failures, missing data, sources, confidence. Excludes builders, HOAs, utilities, railroads, cemeteries, churches, government and conservation land (entity-shaped names only; listed in excluded_owners.csv). Flood and wetlands as % of parcel. A "research next" line per parcel. Flags city / ETJ parcels; overlay zones are not checked. Shows gross and net lot yield. | Automatic when public sources are available; unknown factors are left out and flagged. |
| 3. Aerial check | Saves a USDA NAIP aerial (public domain) of each top parcel with the parcel boundary drawn on, or your county's own imagery. Esri / Google are view links only. Each image states its age ("Imagery is from 2022, about 4 years old. Check current imagery before an offer.") and parcels with no usable imagery are flagged. Claude records what it sees as "clearly visible", "likely" or "can't determine", and never claims legal access or power capacity from a picture. | Images automatic (internet needed). Review: Claude, when you ask. |
| 4. Owners + skip trace | Owner name, mailing address and signals (long hold, out-of-state / out-of-county, tax delinquent, no mortgage, estate / heirs, trust), listing which signals your data actually had from the parcel data. Upload files in a generic format per provider (check your provider's template) (BatchSkipTracing, PropStream, DealMachine, REISift, generic); reads results back with a match-rate report, failed records and phone types. Optional, EXPERIMENTAL BatchData API with your own key: needs your price per record, capped, cost preview first, needs `--confirm`. | Owner data automatic. Phones / emails via YOUR provider. Nothing is scraped. An owner is only "traced" after results come back. |
| 5. Marketing lists | Blocked by default. Your suppression list (kept across runs, STOP replies included) is applied to every list. cold_call.csv only has numbers from your own DNC scrub in the last 31 days (with who scrubbed and which vendor), with a call_window (mailing ZIP + area code, the stricter) and call_eligibility = needs_review; the rest go to cold_call_NEEDS_SCRUB.csv. The CRM import shows a phone only when it is scrubbed. While the suppression list is missing or over 7 days old, every phone and text output is held. Texting only with consent that names you, the purpose and the method. A **CRM import file** you import yourself. COMPLIANCE.md: verify with counsel, registration, state wholesaling notes, data licensing. | Automatic. Importing into your CRM is yours (it is a file, not a live integration). |
| 6. Campaign kit | Offer letter, a gentler letter for estate owners, call opener with voicemail and pushback answers, first texts (consent only), and step-by-step loading instructions. | Copy automatic. You start the campaign from your own tools. |

## What it is not
- A screening tool, not a deal guarantee. Public data has gaps. It won't predict profit or replace a survey, title
  work, an appraisal or a zoning letter. Verify zoning, access and utilities before you offer.
- It runs when you run it: say "refresh my county" weekly. Automatic scheduling needs separate setup. New data appears when the county layer or your export is
  refreshed.
- It doesn't push into your CRM, dial, text or mail. You import the files.

## Folder
- `scripts/` the pipeline (`run_pipeline.py` runs all six steps)
- `samples/` made-up demo data (555-01xx phones, "SAMPLE" owners)
- `config/` your city's lot-split / ADU numbers (`my-market.yaml`) and examples
- `references/` scoring, data sources, skip-trace templates
- `tests/` offline tests: `.venv/bin/python tests/test_pipeline.py` and `.venv/bin/python tests/test_finder.py`
- `KNOWN_LIMITS.md` what it can't do, and what has not been tested (clean Mac / Windows installs)
- `tools/build_zip.py` builds the zip (forces CRLF for .bat, LF and the exec bit for .command)
- `start-mac.command`, `start-windows.bat` one-click setup

Data credits: OpenStreetMap contributors (ODbL), USDA NAIP via USGS (public domain), FEMA NFHL, USFWS NWI, USGS 3DEP, US Census TIGER, HIFLD (re-hosted snapshots of the retired HIFLD Open layers).
