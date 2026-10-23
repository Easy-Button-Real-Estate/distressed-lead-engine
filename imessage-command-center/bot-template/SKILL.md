---
name: imessage-command-center
description: Set up a Mac iMessage command chat for a real estate investor and run comps, offer drafts, buyers, pipeline, schedule, travel, team, CRM, and to-dos from that chat. Use when they say "set up iMessage", "Grok Bot template", "command center", "text my Mac", or "run the business from texts". Nothing sends or changes a record until they reply YES in the command chat.
---

# iMessage Command Center

Read `bot-template/SYSTEM_PROMPT.md` in this folder and follow it. If you cannot read that file, stop. Do not invent install steps.

The short version, which still applies if the long file fails to load:

- The bridge is imsg, installed only after a yes, with `bash install.sh` (plan) and then `bash install.sh --apply`. The apply step runs `brew install steipete/tap/imsg` only when `imsg` is missing.
- Do not disable SIP. Do not run `imsg chat-create`, `imsg launch`, `csrutil`, `tccutil`, or `sudo`. Do not call `imsg send` yourself.
- Full Disk Access and Automation → Messages are clicks in System Settings. Describe them. Do not grant them with a command.
- One command group chat. Do not read the rest of Messages.
- `python3 -m icc propose` texts the ask. Work waits for `YES <id>` or `👍 <id>` in that chat. `NO <id>` cancels. Then `python3 -m icc commit`.
- Do not invent comps, prices, or booking confirmations. Offer text is a draft until a second YES names the exact recipient and the exact body.
