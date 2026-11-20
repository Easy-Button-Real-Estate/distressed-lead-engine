# Development Opportunity Finder (project notes for Claude Code)

The skill lives at .claude/skills/development-opportunity-finder/SKILL.md (same file as ./SKILL.md).
Read it before doing anything; it has the full workflow.

- Always run Python through the kit's private environment, with forward slashes:
  Mac/Linux: .venv/bin/python scripts/<script>.py    Windows: .venv/Scripts/python.exe scripts/<script>.py
  (Windows without Git Bash: Claude Code uses PowerShell; .venv\Scripts\python.exe scripts\<script>.py also works.)
  Never the system python3. If .venv is missing, tell the user to double-click start-mac.command / start-windows.bat.
- Data stays on this computer. Never upload owner lists, phones or emails to any other service, never paste
  API keys into chat, never read .env. The user types any API keys into .env themselves.
- These are research and marketing preparation lists, not approved contact lists. Before launching a
  campaign, verify the applicable consent, suppression, registration, calling-hour and jurisdictional requirements.
- Live, manually dialed calls only. This kit does not support ringless voicemail, voicemail drops, prerecorded or AI voice, or autodialers to any number; those need prior express written consent and separate legal review. Some states (e.g. FL, OK) have their own autodialer laws.
- Suppression is cumulative: never remove a suppression row; never edit suppress/, out/state/ or consent_log.csv.
  Log manual opt-out requests with scripts/suppression.py add (append-only).
- Never imply an heir can sell; check the probate case, letters, court approval and title.
- .claude/settings.json pre-approves only the kit's own scripts and tests. Ask before anything else.
