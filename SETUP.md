# Setup (about 15 minutes)

## Path B (easiest): Claude Code
1. You need a paid Claude plan and **Claude Code** installed (claude.com/claude-code). You also need Python 3.10+ (python.org/downloads).
2. Unzip this folder somewhere (e.g. Documents/distressed-lead-engine).
3. Open a terminal in that folder and type `claude`.
4. Say: **"Set this up for <your county, state>"** (any US county). Claude researches your county's public sources, writes `counties/<st>_<county>.yaml`, test-runs it and tells you what's automatic and what needs a CSV export. (Want to see it work first? "Run today's leads for King County" or "...for Maricopa County".)
5. Optional keys: copy `.env.example` to `.env` and paste your keys, or tell Claude "help me add my DealMachine key". Claude will edit `.env` for you. Never paste keys into a public place.
6. Every morning say **"run today's leads"**, or set up Path A so it runs without you.

The skill lives in `.claude/skills/distressed-lead-engine/`, so Claude picks it up when you open this folder. To use it from any folder, copy that folder into `~/.claude/skills/`.

## Path A: GitHub Actions (runs every day by itself)
1. Make a free GitHub account. Click **+ > New repository**, name it, and choose **Private**.
2. Click "uploading an existing file" and drag in everything from this folder, including the `.github` folder. (On a Mac, press Cmd+Shift+. to show hidden folders.)
3. Add your county file (use Claude Code, or follow ADD_YOUR_COUNTY.md).
4. Go to **Settings > Secrets and variables > Actions > New repository secret** and add any you have: `YOUR_NAME`, `YOUR_COMPANY`, `YOUR_PHONE`, `GOVFILES_API_KEY`, `SKIPTRACE_PROVIDER`, `DEALMACHINE_API_KEY` or `BATCHDATA_API_KEY`, `OUTREACH_WEBHOOK_URL`, and if you use them `BRIGHTDATA_API_KEY`, `BRIGHTDATA_UNLOCKER_ZONE`, `BRIGHTDATA_BROWSER_WSS`, `SCRAPERAPI_KEY`.
5. Open the **Actions** tab, enable workflows, click **Daily distressed leads > Run workflow**.
6. When it turns green, open the run and download **Artifacts > leads-N**. Open `leads.csv` in Google Sheets.
7. It now runs every day at 14:00 UTC. To change the time, edit the `cron` line in `.github/workflows/daily-leads.yml`.

Want leads in a Google Sheet automatically? Make a Zapier or Make "Catch Hook" webhook that adds a row to your Sheet, and put its URL in `OUTREACH_WEBHOOK_URL`, and if you use them `BRIGHTDATA_API_KEY`, `BRIGHTDATA_UNLOCKER_ZONE`, `BRIGHTDATA_BROWSER_WSS`, `SCRAPERAPI_KEY`.

## Getting keys
- **GovFiles** (LLC owners): sign up at govfiles.dev and create an API key.
- **DealMachine**: dealmachine.com/settings/developer. Needs a DealMachine account with API access. Uses data credits.
- **BatchData**: batchdata.io, then the developer dashboard.
- **Bright Data** (optional, for court/recorder portals that block scripts): sign up at brightdata.com, add a **Web Unlocker API** zone; the zone's Overview tab shows the API key and zone name ([guide](https://docs.brightdata.com/scraping-automation/web-unlocker/send-your-first-request)). For JavaScript search forms add a **Browser API** zone, copy its `wss://...` connection string, and run `pip install playwright` ([guide](https://docs.brightdata.com/scraping-automation/scraping-browser/introduction)). Pay-per-use.
- **ScraperAPI** (optional backup): scraperapi.com dashboard > API key ([docs](https://docs.scraperapi.com)).
- Only point these at sites whose terms of use allow automated access, and keep the polite delay on.
- **Invelo**: no key needed. Import `invelo_import.csv`.

## Commands (if you like typing)
```
pip install -r requirements.txt
python -m dle.discover --county Maricopa --state AZ   # find open-data candidates for any county
python -m dle.run --county wa_king --check     # test sources only
python -m dle.run --county wa_king --dry-run   # full run, don't save history
python -m dle.run                              # all counties, normal daily run
python tests/test_core.py && python tests/test_search_page.py   # offline self-tests
```
