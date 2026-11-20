# Where to get the data (free first)

## Parcels (required)

Any file with **acres** plus **lat/lon** works best. Owner, zoning, values and sale date make the ranking much better.

1. **County / state GIS (free).** Most US counties publish a public parcel layer. Search `"<county name> county parcels arcgis rest"` or open the county GIS map and look for a URL ending in `/MapServer/0` or `/FeatureServer/0`. Statewide layers exist in many states (for example Utah UGRC, Nevada, North Carolina, Montana, Wisconsin, Ohio's county auditors). Then:
   ```bash
   python scripts/fetch_arcgis_parcels.py --layer-url URL --list-fields
   python scripts/fetch_arcgis_parcels.py --layer-url URL --bbox "S,W,N,E" --min-acres 10 --output parcels.csv
   ```
   Only pull layers the county makes public. Some counties strip owner names from GIS; get those from the assessor's site or your list provider.
2. **A list you already pay for.** PropStream, Land Portal, Regrid, LandGlide, DataTree, BatchLeads, Reonomy. Export vacant land with acreage, lat/lon, owner and mailing address. Column names are matched automatically (see the aliases in `scripts/score_parcels.py`); rename anything that doesn't match to the names in `samples/parcels-template.csv`.
3. **A deal list from a wholesaler or broker.** Fine, as long as it has acreage and a location.

## Infrastructure (optional, free)

`scripts/fetch_infrastructure.py` pulls OpenStreetMap data through the public Overpass API (it tries several Overpass servers; if all fail it uses US Census TIGER primary / secondary roads and railroads, and HIFLD electric transmission lines; substations and interchanges then stay unknown): substations, transmission lines, interchanges / on-ramps, major highways, mainline rail, water and wastewater plants, industrial areas. Coverage is good for highways and rail and decent for power lines; small substations and private lines can be missing. Fiber is not in OSM in any useful way. Ask the user if they have a better layer, or check the utility's own hosting-capacity / interconnection map for power.

## Constraints (optional, free)

`scripts/enrich_constraints.py` samples a 3x3 grid on each parcel against FEMA NFHL flood zones, the USFWS National Wetlands Inventory and USGS 3DEP elevation. It produces `fema_flood_pct`, `wetlands_pct_est`, `slope_pct_est` and `buildable_pct_est`. It's a screening estimate. Run it on your shortlist (sorted first), not on 20,000 parcels.

## Comps (optional)

A CSV of sold land with `acres` and `sale_price` (plus `sale_date` if you have it), from your MLS, Land Portal, Redfin/Zillow sold filters, a broker, or county deed records. 5 or more clean sales in the same county and size band work best.

## Network

Claude.ai's code sandbox usually can't reach outside sites, and when network access is allowed, the approved list is mostly package managers. If a fetch script fails there, run it in Claude Code on your own computer (Python 3.10+, packages from requirements.txt via the starter), then upload the CSVs to the chat. Scoring itself runs fine in the sandbox.

## Developer sales (for the buy box)

You need recent land / lot sales with buyer name, sale date, sale price and acres.

**Best source:** the county recorder's **grantor-grantee index** (every deed with the recorded buyer and the
price or transfer tax), or a sales report from a **title company rep** (most will pull one for an investor who
orders title from them). These give the recorded buyer, so the buy box can count verified purchases. The other
sources below give the current owner, which is a weaker proxy. Free options:

1. **County parcel layer (free).** On most parcel layers the current owner is the most recent buyer, and there is a last-sale
   date and price. Pull only recent sales with a where clause (field names vary; run `--list-fields` first):
   ```bash
   python scripts/fetch_arcgis_parcels.py --layer-url URL --where "SALEDATE >= DATE '2024-11-01'" --output sales.csv
   ```
   Then `build_buy_box.py --sales sales.csv` keeps the rows whose owner looks like a builder or developer.
2. **County recorder / assessor sales download.** Many counties publish a sales file (CSV) with grantee, date and price.
3. **PropStream or another list you pay for.** Filter: vacant land, sold in the last 24-36 months, owner type corporate.
   Export with owner name, last sale date, last sale price, lot acres, zoning, city, zip, lat/lon.
4. **MLS sold land** through an agent. Buyer names are often missing there, so use `--all-buyers` only if you know
   the buyers were builders.

Add local builders and their LLCs with `--known-developers my_builders.txt` (one name per line), then review
`buyers_review.csv` and re-run with `--approved-buyers buyers_review.csv` (your Y / N wins). Deeds covering several
parcels are grouped into one purchase (same deed id / book-page, or same buyer + date + price).

**Grantee vs current owner.** A recorder or PropStream sales file names the buyer on the deed (grantee). An assessor
parcel layer only has today's owner. If a builder already re-sold the lots, the assessor file shows the new home owner,
so a buy box built from it only sees builders who still own their land (survivorship gap). Prefer a grantee file.

**Non-disclosure states** (TX, NM, UT, ID, WY, MT, ND, KS, MS, LA, AK, MO): deeds carry no price. Use sold-land comps
from your MLS or a land broker, or a PropStream sold export, with `--state TX --price-only`. The buy box then shows
what land sells for in general, not what developers paid, and cannot show premiums. Ask local builders what they pay.

## Aerial imagery

Default: USDA NAIP (National Agriculture Imagery Program) through the USGS National Map image service
(imagery.nationalmap.gov). Public domain, no key, 0.6-1 m, flown every 2-3 years per state. The parcel boundary from
`<parcels>.geometry.json` is drawn on each saved image.
County orthoimagery: many counties publish newer, sharper aerials as an ArcGIS ImageServer or MapServer; pass it with
`--imagery-url` and check the county's terms.
Esri World Imagery and Google Maps: view links only in `satellite_review.csv`. Esri's and Google's terms restrict
saving or caching their imagery outside their own apps without an account / license, so the kit does not download them.

## Skip trace (phones and emails)

The kit never scrapes people-search sites and ships with no paid keys. Two ways:

1. **Export / import (any provider).** `skip_trace.py export` writes `skiptrace_upload_<provider>.csv` in the column
   layout for BatchSkipTracing, PropStream, DealMachine, REISift or a generic layout (`references/skiptrace-templates.json`;
   check it against your provider's current template, or map columns in their uploader). Upload, download the results,
   run `skip_trace.py import --results <file>`. You get `skiptrace_report.txt` (match rate, phone types) and
   `failed_records.csv`. Owners are "not traced" until results are imported.
2. **BatchData API (optional).** Key in `BATCHDATA_API_KEY`. `skip_trace.py api --max 25 --price-per-record 0.20` shows
   a cost preview; nothing is sent without `--confirm`. Hard cap 500 per run. Built from BatchData's public docs and not
   tested against a live account in this release.

A provider's DNC flag is not a DNC scrub. Scrub against the National DNC Registry and your state list yourself.

Companies and trusts go to `entities_to_research.csv`. Look them up on the state's business-entity (Secretary of State)
search to find the person behind them.

## Data licensing (what you may do with each source)

| Source | Terms in short | Credit |
|---|---|---|
| PropStream / BatchLeads / other list providers | Licensed for your own business use; don't resell, share or publish exports | per provider |
| Skip-trace results | Your provider's terms; not consumer reports, never for credit / employment / insurance / tenant decisions (FCRA) | n/a |
| County parcel layers | Set by each county; the kit saves the layer's licence / use text to `sources/county_layer_license.txt` | the county |
| USDA NAIP (via USGS) | Public domain | "USDA NAIP imagery via USGS" |
| OpenStreetMap (Overpass) | ODbL; a database you publish from it must stay ODbL | "(c) OpenStreetMap contributors" |
| US Census TIGER (TIGERweb roads, rail, S1630 ramps); HIFLD transmission lines and substations (re-hosted snapshots; HIFLD Open retired 2025) | Public data | the agency / the re-hosting organisation |
| FEMA NFHL, USFWS NWI, USGS 3DEP | Public domain US government data | the agency |
| Esri / Google imagery | View links only; their terms don't allow saving it | n/a |

## Infrastructure fallback (when OpenStreetMap Overpass is down, or with --no-overpass)
HIFLD Open (hifld-geoplatform) was taken offline in Aug-Sep 2025. The kit uses copies re-hosted on ArcGIS Online
(checked live 2026-11-19; snapshots, not maintained):
- Transmission lines: services2.arcgis.com/LYMgRMwHfrWWEg3s/.../HIFLD_US_Electric_Power_Transmission_Lines/FeatureServer/0
  (backup: services1.arcgis.com/Hp6G80Pky0om7QvQ/.../Electric_Power_Transmission_Lines/FeatureServer/0)
- Substations: services5.arcgis.com/HDRa0B57OVrv2E1q/.../Electric_Substations/FeatureServer/0 (data last edited 2021)
- Roads, rail and highway ramps: Census TIGERweb Transportation MapServer (ramps = MTFCC S1630 in the local-roads
  layer; ramp midpoints stand in for interchanges).
