# Run your business from iMessage

A free setup for real estate investors. Your Mac stays on. Your iPhone, on the same Apple ID, is the remote. You text a private Command Center chat. A Grok Bot on that Mac does the step you approved, and nothing else.

This works in any city. It does not know your market until you tell it, and it does not invent prices.

## What you need

- A Mac that stays awake, signed into Messages (macOS 14 or newer)
- The iPhone you already use, on that same Apple ID
- A Grok Bot account
- About 10 minutes, and the permission screens below

A closed laptop sleeps. Use a desktop, or leave the laptop open and plugged in.

## The three phases

**1. The bridge.** You paste the bot template and tell it to start phase 1. It asks before it changes the Mac. It installs imsg, a free open-source program that reads and sends through the Messages app already on your Mac. You click Allow on Full Disk Access and on Automation for Messages. You make one group chat named Command Center. That is the only chat this tool watches.

**2. Your tools.** You connect the ones you really use: calendar, mail, Slack, a CRM, whatever Grok Bot's Connect apps screen actually offers you. Zoom may not be in that list. The bot is not allowed to pretend a tool is connected. Until a CRM is connected, a simple pipeline list and a to-do list live on the Mac.

**3. You text.** Comps, a draft offer, buyers, the pipeline, your calendar, travel options, a note to the team, the CRM, a 20-line to-do list. Each one comes back as a plan with an id. You reply `YES` and the id, or a thumbs-up and the id. `NO` and the id cancels it. Offers stay drafts until a second YES names the exact person and the exact words.

## Download

Unzip this on the Mac. The folder inside is `imessage-command-center`.

https://github.com/Easy-Button-Real-Estate/distressed-lead-engine/raw/cursor/imessage-command-center-37fb/imessage-command-center/imessage-command-center.zip

The whole branch, if you want every file in the repo as well:

https://github.com/Easy-Button-Real-Estate/distressed-lead-engine/archive/refs/heads/cursor/imessage-command-center-37fb.zip

Open `README.md` in that folder. It is the setup guide. Paste `bot-template/SYSTEM_PROMPT.md` into the bot's instructions, then say: "Start phase 1. Ask me before you change anything."

## The safety line

Nothing is sent, booked, or written to a CRM until you approve that exact step in the Command Center chat. The bot cannot approve itself. Someone else in the group cannot approve for you. A thumbs-up buried in a sentence does not count, and a tapback on the bubble is not read. Reply with the line it asked for.

This is a drafting and command tool. It is not a brokerage, not legal advice, and not a promise that a number is true. Check comps and contracts the way you already do.

## If you get stuck

`README.md` has a short troubleshooting list: Full Disk Access, the Messages automation prompt, and what to do if the Mac went to sleep. The permission screens are clicks. No one needs to turn off macOS security features to use this.
