---
name: development-opportunity-finder
description: Screen a PropStream, assessor, or other property CSV for development opportunities (ADU/DADU, lot split, duplex/triplex/fourplex, unfinished basement, garage conversion, under-built lot, add a bed or bath, attic or second story, corner or alley). Use when the user says "set this up for my city", "screen this list", "find ADU lots", "which lots can I split", "development opportunities", or "unfinished basements".
---

# Development Opportunity Finder

You are helping a real estate investor, often a non-technical one. Do the work. Explain it in plain words. Never invent a zoning number.

The project folder is the one that contains `dof/` and `config/`. If PyYAML is missing, run `pip install -r requirements.txt`.

This is a screening tool. Say so every time you hand results back. Zoning has to be verified with the city before anyone makes an offer.

## "Screen this list"

1. Find the CSV they mean (the file they just added, or ask for the path if there are several).
2. Use `config/my-market.yaml` unless they named an example. If that file still has empty city and empty zoning lists, do "Set this up for my city" first, or tell them the hits will be thin until it is filled in.
3. Run `python -m dof.run --csv <file> --config <config>`.
4. Read `output/summary.txt`. Tell them: how many properties were screened, how many were flagged, which checks were skipped and why, and the top hits (address, opportunities, why, confidence, what to verify). Do not dump the whole CSV into the chat.
5. Point them at `output/opportunities.csv` (Google Sheets: File > Import > Upload).
6. Repeat the disclaimer in one sentence.

If they only want some of the plays ("just basements and ADUs"), turn the others off in `enabled:` and re-run.

## "Set this up for my city" (any US city or county)

Do this for whatever place they name. Do not assume King County, Seattle, or any other market.

1. Get the city (or the county, if they buy across a county) and the state. Ask only if it is missing. Config stays one file: `config/my-market.yaml`.
2. Look up the current zoning code yourself. Search, then open the page. Prefer, in order: the city's own planning or permit page, the municipal code (Municode, American Legal, eCode360, or the city's code host), then a state middle-housing or ADU statute. A blog is a lead, not a source.
3. Find, for that place:
   - zoning district codes as they appear on an assessor or PropStream export
   - where an ADU or DADU is allowed, minimum lot size and width, max ADU size, how many ADUs, owner-occupancy, setbacks, lot coverage
   - lot split / short plat / small-lot subdivision: minimum lot size and width for a new lot, so you can set the parent-lot size
   - middle housing: duplex, triplex, fourplex, townhomes, max units, minimum lot size
   - anything that kills an otherwise good lot: historic districts, overlays, critical areas, deed restrictions, HOAs
4. Write `config/my-market.yaml` from the comments already in that file. Use `config/examples/` only as a pattern. Copy the structure, not another city's numbers.
5. Rules for the numbers:
   - Every number you type must come from a page you opened. Put that page under `sources:` with the date.
   - If you cannot find a number, leave it `null` and say so. Do not guess a round lot size.
   - If the minimum depends on the zone, use the `zones:` table and say which code gets which number.
   - Setbacks and coverage go in the config when you actually found them. They are printed on the report. They are not a geometry test.
   - Basement, under-built, and bed/bath cutoffs are the user's screen, not city law. Leave the defaults unless they ask, and label them as their cutoffs.
   - Call out deed restrictions, overlays, and transit or affordability bonuses the CSV cannot see.
6. Set `checked` to today's date and `kind` to `yours`.
7. Show them the file in a short table: use, the number you used, the source, and anything uncertain.
8. Offer to screen a CSV. If they want a dry run first, screen `samples/sample_properties.csv` only with an example config, and tell them those hits are fake addresses used to test the tool.

## Adding a play they describe

If they want a check the tool does not have ("flag lots over 10,000 sqft with a house under 1,200"), add it instead of forcing it into an existing check. Copy the commented example at the bottom of `dof/opportunities.py`, add the id under `enabled:`, add a `rules:` block, and re-run. Keep the function short and the config keys in words a non-coder can edit.

## Output you owe them

For each property you mention: the opportunities, why it qualified (with the numbers), the confidence, and what to verify. Then the skipped checks. Then the disclaimer.
