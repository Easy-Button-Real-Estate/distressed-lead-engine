# Security and privacy

## What the starter runs
`start-mac.command` / `start-windows.bat` are plain text; open them in a text editor to read them. In order they:
1. look for Python 3.10+ already on your computer (they never install Python or anything system-wide);
2. create a private `.venv` folder inside this kit folder and `pip install` the packages in `requirements.txt`
   (PyYAML, pandas, numpy, openpyxl, Pillow, certifi) from the Python Package Index;
3. run `scripts/doctor.py`, which checks the setup and saves `setup_check.txt` (with `--online` it opens one
   public USGS map page to test the internet);
4. start Claude Code (`claude`) in this folder if it is installed.
Nothing runs in the background, nothing is scheduled, and nothing needs admin rights. The first screen of the
starter repeats the privacy warning below. `--check` (Mac) or `/check`
(Windows) does steps 1-3 only and never prompts. To remove the kit, delete the folder.

## What the kit's scripts contact
Only public map and data servers: your county's ArcGIS parcel layer, OpenStreetMap Overpass, US Census TIGERweb,
the re-hosted HIFLD layers, FEMA, USFWS, USGS / USDA imagery. It sends them map coordinates or a bounding box,
never owner names, phones or emails. The only exception is the optional BatchData skip-trace API, which sends
owner names and addresses to BatchData with your own key, and only after it shows a cost preview and you add
`--confirm`. Claude Code itself talks to Anthropic; see the next section.

## Where owner data goes
The kit's local scripts store and process owner data in your kit folder and do not send owner data to public map servers. However, when Claude Code reads file contents or includes them in prompts, that information may be transmitted to Anthropic for processing under your Claude plan or API account terms and settings. Only use this workflow with data you are authorized to share with that service. Keep API keys in the local .env file and never paste them into chat.

What the kit's scripts keep in your kit folder: your parcel and sales files, every output in `out/`, the
suppression list (`out/state/suppression.csv` and the `suppress/` folder), consent logs and call reviews. The
scripts don't upload them anywhere. Claude Code is different: when it opens one of these files, or you paste
from one, that content goes to Anthropic as part of your conversation. Ask Claude to work from counts and
summaries rather than opening owner files when you don't need it to. Don't upload the files to services that
have nothing to do with your skip-trace provider or CRM, and don't paste API keys into chat (type them into
`.env` or your terminal yourself).

## Permission rules are safeguards, not guarantees
`.claude/settings.json` pre-approves only `.venv` Python running the kit's own `scripts/` and `tests/` (Bash and
PowerShell forms, since Claude Code on Windows uses PowerShell when Git Bash is missing). It denies reading `.env`
through Read, Bash or PowerShell, and denies Claude editing or deleting `suppress/`, `out/state/` and
`consent_log.csv`. These rules lower the risk of a mistake; they do not guarantee it can't happen. Claude Code's
permission system can change between versions, a command you approve by hand can do things the rules don't
cover, and anything you approve with "always allow" widens them. Read each permission prompt before you approve
it. Manual opt-outs go in with `scripts/suppression.py add`, which only appends, and opt-out exports go in with
`scripts/suppression.py import`, which records the date each export was generated.

## Old exports
Owner lists are personal data. Protect the folder (your computer's login password / disk encryption), and delete
old exports: `scripts/cleanup_exports.py` lists files over 90 days old and deletes them only with `--delete`.
It never deletes the suppression list, consent log or call reviews; keep those at least 5 years.

## Checking the download
`SHA256SUMS.txt` in this folder lists the SHA-256 of every file in the kit. The same list, plus the hash of the
zip itself, is published in the lesson text. To check:
- Mac: `cd ~/EBRE-Land && shasum -a 256 -c SHA256SUMS.txt`
- Windows (PowerShell): `Get-FileHash .\start-windows.bat -Algorithm SHA256` and compare with the list.
If a hash doesn't match, don't run the starter; download the kit again from the lesson.
