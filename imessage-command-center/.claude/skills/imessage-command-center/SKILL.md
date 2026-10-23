---
name: imessage-command-center
description: Set up a Mac iMessage command chat for a real estate investor and run comps, offer drafts, buyers, pipeline, schedule, travel, team, CRM, and to-dos from that chat. Use when they say "set up iMessage", "Grok Bot template", "command center", "text my Mac", or "run the business from texts". Nothing sends or changes a record until they reply YES in the command chat.
---

# iMessage Command Center

The project folder is the one that contains `icc/` and `install.sh`.

Read `bot-template/SYSTEM_PROMPT.md` and follow it. The bridge is the open-source `imsg` CLI. Ask before every Mac change. `bash install.sh` prints a plan and changes nothing. `bash install.sh --apply` is the step that installs.

Do not disable SIP. Do not run `imsg chat-create`, `imsg launch`, `csrutil`, or `sudo`. Do not call `imsg send` yourself. The `icc` commands are the only way to text, and they wait for `YES <id>` or `👍 <id>` in the one command chat.

Do not invent a comp, a price, or a booking confirmation. A draft offer stays in the command chat until a second YES names the exact recipient and the exact body.
