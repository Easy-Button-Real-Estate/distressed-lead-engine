# Development Opportunity Finder

Free screening tool for real estate investors. You give it a property list (PropStream, a county assessor export, or any CSV) and a short config for your city. It flags the rows worth a second look and ranks them.

**This is a screen, not a permit.** Zoning, overlays, lot lines, and what you can actually build have to be checked with the city (and usually a surveyor) before you make an offer. The report says that on every run.

It looks for:

- ADU / DADU eligibility
- Lot splits (short plat)
- Middle housing: duplex, triplex, fourplex, or 2–4 townhomes
- Unfinished or partly finished basements
- Garage conversions
- Under-built lots (small house on a big lot)
- Room to add a bedroom or a bathroom
- Attic or second-story potential
- Corner lots or alley access, when the file has those columns

Works in any US city or county. You fill in one config file. Four example configs ship with it so you can see the shape: Seattle, Portland, Austin, and Minneapolis. They are examples to verify, not advice.

Use it two ways:

- **Claude:** open this folder and say *"set this up for Austin, TX"* or *"screen this list"*.
- **The command**, if you like typing. See below.

Setup is in **[SETUP.md](SETUP.md)**.

## What you get (`output/`)

- `opportunities.csv`: flagged properties, highest score first. Each row has the opportunities, why it qualified, a confidence level, what to verify, and a disclaimer.
- `summary.txt`: the same thing in a short read, plus which columns were mapped and which checks were skipped because a column was missing.

Confidence describes the spreadsheet, not the city's answer:

- **high** — the gates you set were in the file and passed
- **medium** — a fact was missing or only implied (a garage type with no size, a duplex that may already be full)
- **low** — the zoning cell was blank, or that hit is only a number you set and the zone was not checked

The confidence on the row is the confidence of its strongest hit. Every opportunity still has its own.

## The config (this is the whole product)

`config/my-market.yaml` is the file you edit. It is commented in plain language. You set:

- city, county, and state
- the zoning codes that allow each use
- minimum lot size and width for an ADU or a split
- max units on a lot
- setbacks or lot coverage, if you know them
- your cutoffs for basements, under-built lots, and bed/bath mismatches

Blank means "I don't know". The screen skips that gate. It does not invent a number.

When the minimum lot size depends on the zone (Portland is the sample of this), use the optional `zones:` table in the same file. One citywide number is enough for a lot of cities. Leave the table out if you don't need it.

`config/examples/` holds the four samples. Each one is marked `kind: example`, names the pages it was checked against, and lists what was left blank on purpose.

| Example | What it illustrates | Verify before you use it |
|---|---|---|
| `seattle-wa.yaml` | NR / RSL zones, 2 ADUs, 4 units, 5,000 sqft new lots | Yards, FAR, and which lots get 6 units near transit |
| `portland-or.yaml` | Different minimums for R2.5, R5, R7, R10, R20, and the `z` overlay | Land division vs middle-housing land division |
| `austin-tx.yaml` | HOME: 3 units at 5,750 sqft, small-lot splits at 1,800 sqft | Deed restrictions. The city will not check them for you |
| `minneapolis-mn.yaml` | One ADU, no minimum lot size, 3 ft side and rear | The built-form overlay, which sets lot size and is often a different column |

Checked 2026-10-21. Codes change.

## Columns

You do not rename your export. The tool recognizes common PropStream and assessor headers (`Lot Size SqFt` and `LOTSQFT`, `APN` and `PIN`, `Square Feet` and `BLDG_SQFT`, basement and below-grade columns, garage, stories, corner, alley). The summary lists what it mapped, what it ignored, and any check it skipped because the column was not there.

A "Lot Size" column full of numbers like 0.18 is treated as acres.

## Add an opportunity type

1. Copy the commented example at the bottom of `dof/opportunities.py`.
2. Add its id under `enabled:` in `config/my-market.yaml`.
3. Add a `rules:` block with the numbers it should read.
4. Run it again.

## Commands

```
pip install -r requirements.txt
python -m dof.run --csv samples/sample_properties.csv --config config/examples/seattle-wa.yaml
python -m dof.run --csv your-export.csv --config config/my-market.yaml
python tests/test_finder.py
```

## Tested (Oct 21, 2026, offline)

`python tests/test_finder.py` passes.

`python -m dof.run --csv samples/sample_properties.csv --config config/examples/seattle-wa.yaml` screened 15 properties and flagged 11. Top row: **101 Big Lot Ave** (score 235, high) with a lot split, middle housing, an ADU, an under-built lot, an unfinished basement, a garage conversion, a second story, a missing bath, and a corner flag. Left off on purpose: a fourplex already at 4 units, a warehouse, a condo, and a retail building. A CSV with only an address skipped every check and named the missing columns. The same sample against a blank `config/my-market.yaml` does not invent ADU or split hits.

MIT License.
