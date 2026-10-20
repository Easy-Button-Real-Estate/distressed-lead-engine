---
name: distressed-lead-engine
description: Set up any US county and pull daily motivated-seller leads (probate, pre-foreclosure, tax delinquent/foreclosure, code violations, evictions, water shut-offs, liens, fire) from public county data, stack and score them, pierce LLCs, skip trace, and write custom outreach. Use when the user says "set this up for my county", "add my county", "run today's leads", "skip trace my leads" or "export to Invelo".
---
# Distressed Lead Engine

You are helping a real estate investor (often non-technical). Explain things in plain words, do the work for them, and never invent a data source.

The project folder is the one containing `dle/` and `counties/`. If it isn't installed yet, run `pip install -r requirements.txt`.

## "Run today's leads"
1. `python -m dle.run` (or `--county <id>` for one county).
2. Read the printed summary and `output/<today>/run_summary.json`.
3. Tell the user: properties found, NEW today, stacked (2+ lists), counts by list type, any FAILED sources, and the top 10 by score from `output/<today>/new_leads.csv` (address, lists, score, details).
4. Point them to `leads.csv` (open in Google Sheets: File > Import > Upload) and `invelo_import.csv`.
5. If a source FAILED, open the URL yourself, see what changed, and fix that source in the county YAML.

## "Set this up for my county" (works for ANY US county)
1. Get county + state (ask only if missing). Note the main cities in it. Config id = `<st>_<county>` lowercase.
2. **Discover open data:** run `python -m dle.discover --county <County> --state <ST> --city <City> ...`. Treat results as candidates only.
3. **Research each list type** for that county with web search + fetching the pages yourself:
   probate, eviction, lien, pre_foreclosure (NOD / lis pendens / notice of trustee sale, whichever the state uses),
   tax_delinquent / tax_foreclosure, code_violation (+ vacant_building, fire if open data exists).
   Look at: county/city open-data portals, county GIS (ArcGIS REST), treasurer/tax collector delinquent lists,
   sheriff sale lists, recorder/clerk official-records search, superior/probate/justice court case search.
   Identify portal vendors (Tyler Odyssey, Landmark Web, plain HTML tables) to reuse `counties/templates/`.
4. **Pick the source type**, preferring in order: socrata, arcgis, csv_url, rss (free, automatic) ->
   `search_page` (HTML results table reachable by URL/form) -> `manual_csv`.
   For each automatic source, fetch it, confirm it returns recent rows with an address or parcel column,
   and set `date_field`/`lookback_days`. Never add a URL you didn't fetch successfully.
5. **search_page rules:** read the site's terms of use first. If they forbid automated access, require a
   CAPTCHA or a human disclaimer click, or you can't tell, DO NOT automate it: use `manual_csv` and tell the
   user how to export. If allowed: use a template, set selectors from a real results page, keep
   `delay_seconds` >= 3, short date range, `max_pages` small. Plain fetch first; only set
   `provider: brightdata` / `brightdata_browser` / `scraperapi` if the user has that key and plain fetch is blocked.
6. **Write `counties/<id>.yaml`** (copy `_template.yaml`; see `wa_king.yaml` and `az_maricopa.yaml` as examples).
   Comment each source with what it is and any limits (city-only coverage, publishing lag).
7. **Test-run:** `python -m dle.run --county <id> --check`, fix FAILED sources, then `--dry-run`. Show 5 real sample rows.
8. **Report** as a table, one row per list type: AUTOMATIC (source + rows today) / NEEDS KEY (search_page that
   needs Bright Data or ScraperAPI) / MANUAL CSV (where to export, exact `inbox/` file name) / NOT FOUND.
   Call out coverage gaps (e.g. code violations for one city only) and stale data.

## Keys (never print, log or commit them)
Keys live in `.env` (local) or GitHub Actions secrets. See `.env.example`.
- GOVFILES_API_KEY: LLC piercing (owners/managers/members from state registries, $0.01 per result).
- SKIPTRACE_PROVIDER=dealmachine + DEALMACHINE_API_KEY, or batchdata + BATCHDATA_API_KEY. Costs money per record: tell the user the cap (`SKIPTRACE_MAX_PER_RUN`, default 100) before the first traced run.
- BRIGHTDATA_API_KEY + BRIGHTDATA_UNLOCKER_ZONE (Web Unlocker), BRIGHTDATA_BROWSER_WSS (Browser API, needs `pip install playwright`), SCRAPERAPI_KEY: only for search portals that block plain fetch and whose terms allow automation. Pay-per-use: tell the user.
- OUTREACH_WEBHOOK_URL for Zapier/Make/n8n/CRMs. Invelo has no public API: they import `invelo_import.csv`.

## Outreach
The tool writes SMS, email and letter copy per lead; it never contacts anyone itself. If the user asks you to improve the copy, rewrite it per lead using the lead's list types and details, keep probate/fire messages gentle, keep "Reply STOP to opt out" in texts, and remind them to scrub phones against DNC and follow TCPA/state rules before texting or calling.

## GitHub daily run
Walk them through SETUP.md "Path A": push to a PRIVATE repo, add secrets, Actions tab > enable > Run workflow. Leads download from the run's Artifacts.
