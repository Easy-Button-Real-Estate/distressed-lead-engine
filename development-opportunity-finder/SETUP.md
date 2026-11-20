# Setup (4 steps)

**What you need:** a Mac or Windows computer, Python 3.10 or newer (free), and **Claude Code, which needs a paid
Claude plan** (Pro, Max, Team or Enterprise, or Anthropic Console API billing; the free Claude plan does not
include Claude Code). Basic use needs nothing else: no API keys and no paid data services. Optional paid services
are listed separately at the end.

> **Screening tool only.** Public data has gaps. It won't predict profit or replace a survey, title search,
> appraisal or zoning letter. It never mails, calls or texts anyone.

> **Privacy.** The kit's local scripts store and process owner data in your kit folder and do not send owner data to public map servers. However, when Claude Code reads file contents or includes them in prompts, that information may be transmitted to Anthropic for processing under your Claude plan or API account terms and settings. Only use this workflow with data you are authorized to share with that service. Keep API keys in the local .env file and never paste them into chat.

**The one supported path:** Claude Code on your own Mac or Windows computer, started by the double-click starter
in this folder. (The claude.ai web chat can't pull county data or aerial images because its sandbox blocks
outside sites; use it there only to score a file you upload.) How long setup takes depends on your computer and
connection; the first start downloads the Python packages.

## 1. Export your land list from PropStream (or your county)
In PropStream: filter your county for **vacant land**, the acreage your buyer wants (for example 5-100 acres), and
export to CSV with owner name, mailing address, APN, acres, zoning / land use, last sale date and price, and lat/lon.
For the buy box, the best source is your **county recorder's grantor-grantee index** (deeds with the recorded
buyer and price) or a sales report from a **title company rep**. A PropStream export of vacant land sold in the
last 24-36 months also works, but it shows the current owner, not always the buyer.
Texas, Utah, Kansas, Missouri and other **non-disclosure states** don't publish sale prices: use sold-land comps
from your MLS / land broker instead; the buy box then shows land prices in general, not what developers paid.

## 2. Install Python and Claude Code
- Python 3.10 or newer from python.org/downloads.
  **Windows:** the python.org installer or the Python install manager both work; with the classic installer tick
  "Add python.exe to PATH" on the first screen. **Mac:** use the python.org installer.
- Claude Code from claude.com/claude-code (**needs a paid Claude plan**, see above).
- **Windows, recommended:** Git for Windows (git-scm.com), which gives Claude Code its Git Bash shell. Without it
  Claude Code uses PowerShell; the kit works with either, and the starter tells you which one it found.

## 3. Extract the zip and double-click the starter
Extract the whole zip first; don't run anything from inside the zip window.
- **Mac:** double-click the zip, then move the folder to your home folder and name it `EBRE-Land` (`~/EBRE-Land`).
  If you keep it in Desktop, Documents or Downloads instead, macOS will ask "Terminal would like to access files
  in your ... folder": click **Allow**.
- **Windows:** **Right-click the zip > Extract All**, and extract to `C:\EBRE-Land`. (If the starter says it is
  running from a temporary folder, you double-clicked it inside the zip preview: Extract All first.)
Folder names with spaces work. Put your CSVs in that folder.
- **Mac:** double-click `start-mac.command`. If macOS says it "can't be opened" or "Apple could not verify" it,
  click **Done** (not Move to Trash), open **System Settings > Privacy & Security**, scroll down to the Security
  section, click **Open Anyway** next to "start-mac.command was blocked", enter your Mac password if asked, then
  click **Open Anyway** once more in the box that appears. On recent macOS (Sequoia, 15 and later) the old
  shortcut, Control-click (or right-click) > Open, no longer gets you past this; use Open Anyway. *(Exact wording
  and steps to be confirmed by the home-machine run.)* If double-clicking does nothing, open Terminal, type
  `bash ` (with a space), drag the file into the window and press Enter.

  [Screenshot placeholder 1 (Mac): the first "can't be opened" / "could not verify" dialog - from the home-machine run]
  [Screenshot placeholder 2 (Mac): System Settings > Privacy & Security with the Open Anyway button - from the home-machine run]
  [Screenshot placeholder 3 (Mac): the starter's first screen with the privacy warning - from the home-machine run]
- **Windows:** double-click `start-windows.bat`. If a blue box says "Windows protected your PC" (Microsoft Defender
  SmartScreen), click **More info**, check that the app name is start-windows.bat, then click **Run anyway**. If
  there is no Run anyway button, your PC's settings or your organisation block it; ask whoever manages the PC.
  *(Exact wording and steps to be confirmed by the home-machine run.)*

  [Screenshot placeholder 4 (Windows): the "Windows protected your PC" box - from the home-machine run]
  [Screenshot placeholder 5 (Windows): the same box after More info, with Run anyway - from the home-machine run]
  [Screenshot placeholder 6 (Windows): the starter's first screen with the privacy warning - from the home-machine run]
The starter finds Python 3.10+ (Mac: python.org or Homebrew Python, never Apple's built-in `/usr/bin/python3`;
Python 3.10 to 3.15; Windows: `py -3` first, and the Microsoft Store "python" shortcut counts as not installed), creates a private `.venv` folder, installs the packages, runs a setup check, checks for Claude Code, and starts it
in the folder. The starter's first screen repeats the privacy warning above. **The setup check is saved as `setup_check.txt` in the kit folder itself**, next to the starter
(for example `C:\EBRE-Land\setup_check.txt` or `~/EBRE-Land/setup_check.txt`); the starter prints the full path.
If anything fails, that file says what to fix; send it to whoever supports you.

## 4. Run it
**Run the sample first:** say **"run the demo"** (everything in it is made up; it writes to `out_demo/` only and
needs no keys or accounts). Look through `out_demo/START_HERE.md` before using your own data. Then:
**"Set this up for <county, state>. My buyer builds <single-family lots / industrial / data center / solar>. My
parcels are parcels.csv and my sales are sales.csv."**
Open `out/START_HERE.md`. Then: "review the aerial images", upload `out/skiptrace/skiptrace_upload_<provider>.csv`
(generic format, check your provider's template) and give Claude the results file. Bring skip-trace results back through the kit before dialing. Never load the vendor file straight into your dialer. Then say then "build the marketing
lists" and "write the campaign". Nothing is sent; you import the files into your own tools.

**Run it once a week** by saying "refresh my county". (Automatic scheduling needs separate setup.)
START_HERE.md shows the last-run date, and `out/marketing/new_owners.csv` holds only owners new since the last run.

---

### Before you contact anyone
- Read `out/marketing/COMPLIANCE.md` and verify it with counsel.
- These are research and marketing preparation lists, not approved contact lists. Before launching a campaign,
  verify the applicable consent, suppression, registration, calling-hour and jurisdictional requirements.
- Keep a do-not-contact list. Import the latest opt-outs and do-not-contact requests from every system where your team communicates with these owners. Save the exports (phone, address, owner, date,
  channel) in the `suppress/` folder (blank template: `templates/suppress.csv`), plus every STOP reply
  (`--stop-replies`). Also log manual requests your employees receive (a call, letter, email or in person): add them to suppress/manual_requests.csv or run scripts/suppression.py add. Every run reads them and adds them to `out/state/suppression.csv`.
  Bring each export in with `scripts/suppression.py import <file> --export-date YYYY-MM-DD --source "<system>"`
  (or ask Claude to): the date is the day that system **generated** the export, not the day you copied it. If the
  file itself shows its export date the kit reads it from there. An undated file doesn't count as current.
  The list only grows: never remove a row. Unless at least one export was generated in the last 7 days,
  START_HERE.md shows a banner and **every phone and text output is held** until you import a current export.
- Calls: only numbers from a complete DNC scrub (federal + your state's list + your internal list) in the last 31
  days, with who ran it (`scrubbed_by`) and which service (`vendor`), reach `cold_call.csv`, and each starts as
  `needs_review`. A skip-trace provider's DNC flag is not a scrub. `crm_import.csv` shows a phone only when it is
  scrubbed; otherwise `phone_status` says "not scrubbed, do not dial".
- Live, manually dialed calls only. This kit does not support ringless voicemail, voicemail drops, prerecorded or AI voice, or autodialers to any number; those need prior express written consent and separate legal review. Some states (e.g. FL, OK) have their own autodialer laws.
  Manually dialed means a person dials or clicks one number at a time, with no power, predictive or multi-line dialer.
- Each call row has a `call_window` that is an **estimated window**, never a verified one: worked out from the
  mailing address and the phone's area code, taking the stricter; federal 8am-9pm local, tighter where the kit has
  coded the state's hours (TX, LA, MS, AL, NC, VA, MD, FL, OK; sources and dates in COMPLIANCE.md). Other states
  say "federal window; <state> hours not coded, VERIFY". `sunday_holiday_rule` flags Sunday and holiday limits.
  The kit never knows where the person is right now, so before any row is reviewed someone checks the person's
  local time and the state's rules and puts Y in `hours_verified` in `call_review.csv`.
- Before campaign prep, work through `out/campaign/STATE_AND_JURISDICTION_CHECK.md` (state wholesaling and local
  rules) and fill `out/campaign/state_check_record.csv` (which state's law applies, licence, disclosures, who
  verified it and when). Consent, 10DLC, DNC and calling hours are separate checks in `campaign_checklist.md`.
  A DNC scrub is not consent, and consent does not override other restrictions (calling hours, do-not-contact requests, state rules, call-frequency limits). 10DLC registration is a separate requirement: it is not consent, and consent does not replace it.
- Estates: Never imply that an heir can sell. Before any offer on an estate-owned parcel, check the probate case (court and case number), that a personal representative has been appointed and holds current letters (testamentary or of administration), whether the court must approve the sale, and title (a title company confirms who can convey).
- Verify the data license before redistribution or resale.
- Texts: only with a consent file that names you, the purpose, the method and where the proof is kept
  (`templates/consent.csv`), plus 10DLC registration through your texting provider.
- Privacy: see the warning at the top. Keep keys in `.env`; never paste them into chat. The permission rules in
  `.claude/settings.json` are a safeguard, not a guarantee. `scripts/cleanup_exports.py` lists old exports to
  delete (it never touches the suppression list or consent records). See SECURITY.md.

### Optional extras (free)
- **Use it from any folder:** copy `.claude/skills/development-opportunity-finder/` into `~/.claude/skills/`.
- **Your county's own aerials:** give Claude its ArcGIS ImageServer URL (`--satellite county --imagery-url URL`).
- Known limits: see KNOWN_LIMITS.md.

### Optional paid services (not needed for basic use)
Everything above works without these. They cost money on your own account.
- **Your skip-trace provider** (BatchSkipTracing, PropStream, DealMachine, REISift...): you upload the file the kit
  makes and give Claude the results. Billed by your provider.
- **BatchData skip-trace API (EXPERIMENTAL):** built from BatchData's public docs and not yet run against a live
  account; check the first results by hand. Set `BATCHDATA_API_KEY` in your terminal before you start Claude.
  Never paste a key into the chat. It needs your price per record, shows the cost first, and sends nothing
  without `--confirm`.
- **A DNC scrub service** if you don't scrub against the registry yourself.
