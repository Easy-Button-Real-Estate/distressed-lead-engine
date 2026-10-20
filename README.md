# Distressed Lead Engine - works in any US county

Free, open-source motivated-seller lead finder for real estate investors, wholesalers and flippers.
**Tell Claude your county and state** ("set this up for Harris County, TX") and it researches that county's
public sources for probate, evictions, liens, pre-foreclosures / NODs, tax delinquents and code violations,
writes the county config, test-runs it, and tells you exactly what comes in automatically and what needs a
quick manual CSV export. Two example configs ship with it: King County, WA and Maricopa County, AZ.

Every day it pulls fresh leads from **public county and city data**, stacks properties that show up on more than one list, scores them, finds the people behind LLCs, skip traces (with your own provider key), and writes custom text, email and letter copy for each property. You get it all in a spreadsheet you can open in Google Sheets or import into Invelo.

Use it two ways:
- **Claude Code:** open the folder and say *"set this up for my county"* or *"run today's leads"*.
- **GitHub:** runs on its own every morning with GitHub Actions. Download the spreadsheet from the run page.

Setup takes about 15 minutes. See **[SETUP.md](SETUP.md)**.

## What you get each day (`output/<date>/`)
- `leads.csv`: every property, highest score first. Columns: list types, score, address, parcel, owner, event date, details, source links, LLC principals, phones/emails (if skip traced), and SMS / email / letter copy.
- `new_leads.csv`: only properties that are new (or hit a new list) since your last run.
- `invelo_import.csv`: ready for Invelo (More > Import Data > Properties).
- `run_summary.json`: which sources worked and which failed.

## Lists it handles
probate, pre-probate (obituaries), pre-foreclosure, tax delinquent / tax foreclosure, code violations and vacant buildings, evictions, water shut-offs, liens and fire.
**Each county publishes different things.** Some lists come in automatically from open data. Others (often probate, pre-foreclosure, evictions, water shut-offs) only exist behind court or recorder search forms. For those you export a CSV and drop it in `inbox/`, and the engine merges it in. Claude tells you which is which for your county.

## How it gets data in any county
1. **Open data** (Socrata, ArcGIS, CSV downloads, RSS): free and automatic. `python -m dle.discover --county X --state ST` searches the national open-data catalogs for candidates.
2. **Public records search pages** (court and recorder portals): the `search_page` source type takes a URL template, date range, a CSS table parse spec and pagination. Ready-made templates for common portal vendors live in `counties/templates/`: **Tyler Odyssey** court portals, **Landmark Web** recorder systems, and **generic HTML tables**.
3. **Fetch providers** for portals that block plain scripts or need a real browser, using *your own* key:
   - **Bright Data** (primary): [Web Unlocker API](https://docs.brightdata.com/scraping-automation/web-unlocker/send-your-first-request) and [Browser API / Scraping Browser](https://docs.brightdata.com/scraping-automation/scraping-browser/introduction) for JavaScript search forms.
   - **ScraperAPI** (backup): [docs](https://docs.scraperapi.com).
   - **Plain fetch** (default, free). With no keys, everything still runs on open data.
   The engine tries Bright Data, then ScraperAPI, then plain fetch, or whatever you set in `SCRAPER_PROVIDER`.
4. **Manual CSV drop-in** for anything else: export from the portal, drop it in `inbox/`.

**Respect each site's terms of use and rate limits.** Many court portals prohibit automated searching or
bulk copying even though the records are public. If a site's terms say no, use its export button, buy its
bulk data, or file a records request, and use the manual CSV drop-in. The engine waits between requests
(`FETCH_DELAY_SECONDS`, default 2) and only pulls a short date range each day. You're responsible for how you use it.

## Scoring (0-100)
Each list has a weight (probate/pre-foreclosure/tax foreclosure highest). A property on 2+ lists gets a stacking bonus. Fresh events (last 7 / 30 days) and estate or trust owners score higher. Edit `WEIGHTS` in `dle/core.py`.

## Integrations (each person uses their own key; all optional)
| What | Provider | How |
|---|---|---|
| LLC piercing | [GovFiles](https://docs.govfiles.dev) | `GOVFILES_API_KEY`. Searches state registries for the LLC and lists owners, managers and members ($0.01 per result). No key: you get a free Secretary of State search link per LLC. |
| Skip tracing | [DealMachine API](https://api.docs.dealmachine.com) | `SKIPTRACE_PROVIDER=dealmachine` + `DEALMACHINE_API_KEY` (Enrich by Address, owner phones/emails with DNC flags) |
| Skip tracing | [BatchData](https://developer.batchdata.com) | `SKIPTRACE_PROVIDER=batchdata` + `BATCHDATA_API_KEY` |
| Hard-to-scrape portals | [Bright Data](https://docs.brightdata.com) / [ScraperAPI](https://docs.scraperapi.com) | `BRIGHTDATA_API_KEY` + `BRIGHTDATA_UNLOCKER_ZONE` (and `BRIGHTDATA_BROWSER_WSS` for JS portals), or `SCRAPERAPI_KEY` |
| Outreach | Invelo | No public API, so it writes `invelo_import.csv`. Send mail, SMS (smrtPhone) or email with an Invelo Workflow. |
| Outreach | Anything else | `OUTREACH_WEBHOOK_URL`. New leads are POSTed as JSON (Zapier, Make, n8n, GoHighLevel, REsimpli...). |

The engine **never texts, emails or mails anyone by itself**. You review, then send from your own tools.

## Example config 1: King County, WA (tested live Oct 20, 2026)
- Tax foreclosure: King County Treasury foreclosure parcels (data.kingcounty.gov `nx4x-daw6`), converted to addresses with the KC GIS parcel layer.
- Code violations: Seattle code complaints and violations (data.seattle.gov `ez4a-iug7`), filtered to vacant buildings, landlord/tenant, emergency and construction cases.
- Fire: Seattle Fire real-time 911 dispatch (data.seattle.gov `kzjm-xkqj`), building and residential fires. These are dispatch calls, not confirmed damage.
- Probate and pre-foreclosure: manual drop-in. King County court and recorder records aren't open data.
- Code violations and fire cover the City of Seattle only, not the whole county.

## Example config 2: Maricopa County, AZ (tested live Oct 20, 2026, plain fetch, no keys)
- Tax delinquent + unsold tax-lien parcels: Maricopa County Enterprise GIS (county-wide).
- Evictions: City of Phoenix eviction filings layer (published with a lag; newest filing was Feb 2026 on test day).
- Code violations: Mesa and Scottsdale open data.
- Probate, Notices of Trustee Sale and recorded liens: manual drop-in (court/recorder search apps), or `search_page` with Bright Data where the site's terms allow.

## Be honest with yourself
- County websites change and sometimes block scripts, so a source will break now and then. The run tells you which one, and Claude can fix it.
- A list hit is a lead to verify, not a guaranteed motivated seller.
- Skip-traced numbers need DNC scrubbing, and texting or calling must follow TCPA and your state's rules. Be kind with probate and fire leads.
- If you add skip tracing, keep your GitHub repo **private**, because the files contain phone numbers.

MIT License.
