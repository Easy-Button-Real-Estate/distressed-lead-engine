# suppress/ (drop folder)

Import the latest opt-outs and do-not-contact requests from every system where your team communicates with these owners.
Save each export here as .csv (columns: phone, address, owner, date, channel, reason; see templates/suppress.csv):
your CRM, dialer, texting tool (STOP replies), email tool and mail house.

Manual requests count too: when an employee hears "don't contact me" on a call, in a letter, by email or in person,
add it to suppress/manual_requests.csv (template: templates/manual_requests.csv) or run
`PY scripts/suppression.py add --phone "..." --owner "..." --reason "asked on a call" --by "<who took it>"`.

Every run reads every CSV in this folder and adds it to the master list in out/state/suppression.csv.
Suppression is cumulative: rows are only ever added, never removed (the kit refuses to write a shorter list).
Never remove a suppression row. START_HERE.md shows "SUPPRESSION LIST MAY BE OUT OF DATE" when this folder has
no file with rows or the newest one is more than 7 days old, and while that banner shows the kit holds back
every phone and text output (no cold_call.csv, no sms.csv, phones blank in crm_import.csv).
Claude Code is not allowed to edit this folder (.claude/settings.json); you save the files here yourself.
