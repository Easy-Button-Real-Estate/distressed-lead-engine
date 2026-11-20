# Known limits (read before you rely on a result)

**Screening tool only.** Public data has gaps. It won't predict profit or what a developer will pay, and it does not
replace a survey, title search, appraisal, wetlands delineation, flood determination or a zoning letter.

## Setup
- **Not tested on a clean Mac or a clean Windows PC yet.** The kit is tested on Linux (Python 3.10 and 3.13)
  with the same scripts, and the Mac starter's `--check`, zip-path refusal and no-Python branches have been run
  there. `start-windows.bat` has not been executed on Windows. A GitHub Actions workflow
  (`.github/workflows/dev-skill-clean-machine.yml` in the source repo, not in this zip) runs the starters, the
  tests, the demo and the negative cases on fresh macos-latest and windows-latest runners with Python 3.10, 3.13
  and 3.14; it is written but has not been run yet. If a
  starter fails, run `bash start-mac.command --check` or `start-windows.bat /check` and send `setup_check.txt`
  to whoever supports you.
- Supported path: Claude Code on your own computer. Claude Desktop and the claude.ai web chat are not the
  supported path; claude.ai can't reach county servers or imagery.
- Weekly runs happen when you say "refresh my county". Nothing is scheduled automatically.

## Buy box
- Builder detection from names is a guess. It misses builders buying through plain LLC names and can count a
  non-builder with a builder-like name. Only deeds you confirm (buyers_review.csv Y, or your known-developers
  list) count as verified. Most first runs are LOW confidence.
- Assessor "current owner" data misses builders who already sold the lots (survivorship gap).
- Non-disclosure states have no public prices: price-only mode is land prices in general.

## Scoring and data
- Lookups are automatic when public sources are available. OpenStreetMap's Overpass servers are often busy; the
  kit tries several, then uses US Census TIGER (roads, rail, highway ramps as interchanges) and re-hosted copies of
  the retired HIFLD transmission-line and substation layers. Those copies are snapshots (substations: 2021) hosted
  by third parties and can vanish; new lines and substations are missing. Water plants and industrial areas have
  no fallback and stay unknown. Time zones are estimated from state + ZIP and
  the phone's area code (NANPA list); area codes follow the number, not the person, so a ported or moved number
  can point to the wrong zone. When the signals disagree the row says VERIFY calling hours. Unknown factors are left out
  of the score and shown in a banner.
- Flood and wetlands percentages come from a 9-point sample over a square the size of the parcel, not the true
  boundary. FEMA "unmapped" is unknown, not safe. NWI is a screen, not a delineation.
- Water / sewer is unknown unless you supply a layer. Power is distance to mapped lines, not capacity. Overlay
  zones are not checked. Zoning must be verified with the city.
- Owner signals depend on the columns in your file; a missing column means "not checked".

## Outreach
- The kit never sends anything. Lists are blocked by default: suppression applied, calls only after your own
  DNC scrub (31 days) and your review, texts only with confirmed consent.
- COMPLIANCE.md is a reminder list, not legal advice. Laws change; verify with counsel.
- Skip-trace upload templates are a generic format; check your provider's current template.
- BatchData API support is EXPERIMENTAL: built from public docs and not tested against a live account.
- Aerial imagery (NAIP) is typically 2-4 years old; every image row states its age. Parcels without usable
  imagery are flagged.
- Some owner-motivation signals (tax delinquency, liens, probate filings) are only checked when your file has
  them; motivation_signals.csv lists which were collected this run.
