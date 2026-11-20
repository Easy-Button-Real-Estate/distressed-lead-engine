# suppress/ (drop folder)

Import the latest opt-outs and do-not-contact requests from every system where your team communicates with these owners.
Bring each export in with (columns: phone, address, owner, date, channel, reason; see templates/suppress.csv):
`PY scripts/suppression.py import <file> --export-date YYYY-MM-DD --source "CRM" --by "<who exported it>"`
for your CRM, dialer, texting tool (STOP replies), email tool and mail house. --export-date is the day that
system GENERATED the export, not the day you downloaded or copied it. If the file itself carries the date (a
first line like "# exported: 2026-11-18", or an export_date / generated_at column) the kit reads it from the
file and you can leave --export-date out. A system with no opt-outs: import a header-only CSV with its date.

Manual requests count too: when an employee hears "don't contact me" on a call, in a letter, by email or in person,
add it to suppress/manual_requests.csv (template: templates/manual_requests.csv) or run
`PY scripts/suppression.py add --phone "..." --owner "..." --reason "asked on a call" --by "<who took it>"`.

Every run reads every CSV in this folder and adds it to the master list in out/state/suppression.csv.
Suppression is cumulative: rows are only ever added, never removed (the kit refuses to write a shorter list).
Never remove a suppression row. START_HERE.md shows "SUPPRESSION LIST MAY BE OUT OF DATE" unless at least one system
export here was generated in the last 7 days (judged by its generated date, never the file's date on disk; an
undated export doesn't count; manual_requests.csv is always applied but isn't an export), and while that banner shows the kit holds back
every phone and text output (no cold_call.csv, no sms.csv, phones blank in crm_import.csv).
Claude Code is not allowed to edit this folder directly (.claude/settings.json, a safeguard, not a guarantee);
files arrive through suppression.py import / add, or you save them here yourself.
