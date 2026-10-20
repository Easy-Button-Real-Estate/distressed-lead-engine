# Add your county

Easiest: open Claude Code in this folder and say **"set this up for Harris County, TX"**. Claude finds the public sources, tests them, and writes the config. Or do it by hand:

0. Find open-data candidates: `python -m dle.discover --county Harris --state TX --city Houston`.
1. Copy `counties/_template.yaml` to `counties/tx_harris.yaml` (state_county, lowercase).
2. Add one `sources:` entry per list you can find. Test with `python -m dle.run --county tx_harris --check`.
3. Run `python -m dle.run --county tx_harris --dry-run` and open `output/latest.csv`.

## Where each list usually lives (it varies by county, check yours)

| List | Usually found at | Usually automatic? |
|---|---|---|
| Code violations / vacant buildings | City open-data portal (Socrata, ArcGIS), 311 data | Often yes in big cities |
| Fire | City fire dept 911 dispatch open data | Sometimes (big cities) |
| Tax delinquent / tax foreclosure | County treasurer / tax collector list (CSV, PDF, open data) | Often a download; sometimes PDF only |
| Pre-foreclosure (NOD, lis pendens, notice of trustee sale) | County recorder / clerk document search, legal notice papers | Usually manual export |
| Probate | Probate / superior court case search | Usually manual (search forms, some paid) |
| Pre-probate (obituaries) | Local funeral home or newspaper obituary RSS | RSS when offered |
| Evictions | Court civil case search (unlawful detainer) | Usually manual |
| Water shut-offs | City utility, often only by public records request | Rarely public online |
| Liens | Recorder (mechanic's, HOA, IRS liens) | Usually manual |

How to search a Socrata portal fast: `https://api.us.socrata.com/api/catalog/v1?domains=data.yourcity.gov&q=code%20violation`.
ArcGIS: search "<county> arcgis rest services parcels" and look for `.../MapServer/<n>` layers.

## Court and recorder search pages (`type: search_page`)
Probate, evictions, liens and pre-foreclosures usually live behind a search form. If the results come back
as an HTML table, you can configure it once:

```yaml
  - name: Probate filings (court portal)
    list_type: probate
    type: search_page
    template: tyler_odyssey          # or landmark_web, html_table (see counties/templates/)
    url: "https://court.example.gov/Portal/Search?type={case_type}&from={from}&to={to}&page={page}"
    params: {case_type: "PR"}
    date_range: {lookback_days: 7, format: "%m/%d/%Y"}
    parse: {rows: "table#results tbody tr", header: "table#results thead th", link: "a"}
    pagination: {start: 1, max_pages: 3}
    provider: brightdata_browser      # or brightdata, scraperapi, direct; omit = auto chain
    delay_seconds: 5
    map: {owner_name: "Party Name", event_date: "File Date", details: "Case Number", source_url: url}
```
POST forms: set `method: POST` and `form: {FieldName: "{from}"}`. Placeholders: `{from} {to} {page} {offset} {county} {state}` + your `params`.
Templates: **Tyler Odyssey** (court portals, often /Portal/ or /PublicAccess/ URLs), **Landmark Web** (recorder official-records, /LandmarkWeb), **html_table** (anything with a plain results table). Every install is customized, so open one real results page and check the selectors.

**Terms of use and rate limits:** read each portal's terms before automating it. Many court portals forbid
automated searches or require you to click through a disclaimer or CAPTCHA as a person; if so, don't automate it,
use the manual CSV drop-in instead. Keep `delay_seconds` at 3+ and the date range short.

**Manual drop-in:** export the search results to CSV, name it what your YAML says (e.g. `inbox/tx_harris_probate.csv`), and the next run picks it up, dedupes it and stacks it with everything else. Map your CSV's column names in the `map:` block.

Rules: only use public records, respect each site's terms and rate limits, and don't add a source you haven't tested. Sites change. When one breaks, the run prints FAILED for that source and keeps going.
