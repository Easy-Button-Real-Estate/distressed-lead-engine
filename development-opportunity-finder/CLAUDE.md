# Development Opportunity Finder (project notes for Claude Code)

The skill lives at .claude/skills/development-opportunity-finder/SKILL.md (same file as ./SKILL.md).
Read it before doing anything; it has the full workflow.

- Always run Python through the kit's private environment, with forward slashes:
  Mac/Linux: .venv/bin/python scripts/<script>.py    Windows: .venv/Scripts/python.exe scripts/<script>.py
  (Windows without Git Bash: Claude Code uses PowerShell; .venv\Scripts\python.exe scripts\<script>.py also works.)
  Never the system python3. If .venv is missing, tell the user to double-click start-mac.command / start-windows.bat.
- Privacy: The kit's local scripts store and process owner data in your kit folder and do not send owner data to public map servers. However, when Claude Code reads file contents or includes them in prompts, that information may be transmitted to Anthropic for processing under your Claude plan or API account terms and settings. Only use this workflow with data you are authorized to share with that service. Keep API keys in the local .env file and never paste them into chat.
  So: never upload owner lists, phones or emails to any other service, never read .env, never ask for keys in
  chat. Work from counts, summaries and START_HERE.md; open owner-level files only when the task needs it.
- Bring skip-trace results back through the kit before dialing. Never load the vendor file straight into your dialer.
- These are research and marketing preparation lists, not approved contact lists. Before launching a
  campaign, verify the applicable consent, suppression, registration, calling-hour and jurisdictional requirements.
- Live, manually dialed calls only. This kit does not support ringless voicemail, voicemail drops, prerecorded or AI voice, or autodialers to any number; those need prior express written consent and separate legal review. Some states (e.g. FL, OK) have their own autodialer laws.
- Suppression is cumulative: never remove a suppression row; never edit suppress/, out/state/ or consent_log.csv.
  Log manual opt-out requests with scripts/suppression.py add (append-only). Bring opt-out exports in with
  scripts/suppression.py import <file> --export-date YYYY-MM-DD (the date the system generated it, not today).
- Never imply an heir can sell; check the probate case, letters, court approval and title.
- .claude/settings.json pre-approves only the kit's own scripts and tests. Ask before anything else. The rules
  are a safeguard, not a guarantee; never suggest the user widen them.
