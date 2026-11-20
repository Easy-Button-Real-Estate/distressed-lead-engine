# Sample files (all made up)

Everything in this folder is fictional and exists so you can try the tool before using your own data.

- `sample_parcels.csv`: 60 land parcels in "Sample County, OH". Owners are "SAMPLE OWNER nn", APNs are "SAMPLE-nnn".
- `sample_developer_sales.csv`: 24 land sales. Builder-style buyers ("SAMPLE HOMES LLC"...), plus a bank, a family trust, a person,
  a 2022 sale and a $10 deed, so you can see the filter drop them.
- `sample_infrastructure.csv`: fictional highway, substations, rail line.
- `sample_comps.csv`: fictional sold-land comps.
- `sample_skiptrace_results.csv`: what a skip-trace provider's results file looks like. Phones are 555-01xx (reserved
  fictional numbers) and emails are @example.com.
- `sample_properties.csv`: 15 made-up houses in Seattle for the lot-split / ADU screen.
- `parcels-template.csv`: column names the scorer understands, if you need to rename an export.
- `buy-box.example.json`: a hand-written buy box, if you want to skip the sales step.

The coordinates fall in a real part of central Ohio only so map and satellite links open somewhere.
The imagery shows whatever is really there (often houses), not these fictional parcels. That is a good
example of why the satellite review step exists.

Run the whole demo: `.venv/bin/python scripts/run_pipeline.py --demo` (Windows: `.venv\Scripts\python.exe scripts\run_pipeline.py --demo`). It writes to out_demo/.

Round-2 additions (all made up):
- `sample_tx_sold_comps.csv`: sold-land comps with no buyer names, for the non-disclosure (price-only) path: `build_buy_box.py --sales samples/sample_tx_sold_comps.csv --state TX --price-only`.
- `known_developers.example.txt`: a known-developers list (one LLC that the name filter would miss).
- `sample_consent.csv`: a texting-consent file (phone, consent_date, consent_source) to try `--sms --consent-file`.
- `sample_developer_sales.csv` now includes one deed covering 3 parcels (grouped into one purchase).
