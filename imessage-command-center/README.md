# iMessage Command Center

Free setup for real estate investors who want to run the day from a text thread. Your Mac stays on and signed into Messages. Your iPhone, on the same Apple ID, is how you send the orders. A Grok Bot on that Mac drafts the work, asks you in the thread, and does the step only after you reply.

It is not tied to a city or a county. It does not know your prices, your contracts, or your vendors until you connect them, and it is not allowed to invent them.

**Nothing is sent, booked, or written down until you approve that step in the command chat.** The approval is a reply you type: `YES` and the id, or `👍` and the id. The bot cannot approve itself.

Setup is about 10 minutes the first time. The guide below is the whole product. The bot's script is [bot-template/SYSTEM_PROMPT.md](bot-template/SYSTEM_PROMPT.md). Example texts are in [prompts/real-estate-texts.md](prompts/real-estate-texts.md).

MIT License. The iMessage program it installs, [imsg](https://github.com/openclaw/imsg), is someone else's MIT project (copyright Peter Steinberger). This folder is the guide, the approval gate, and the bot template. It is not affiliated with Apple or xAI.

## What you need

- A Mac on macOS 14 or newer that **stays awake**. A closed laptop sleeps, and then nothing runs. A desktop, or a laptop left open and plugged in, is the right machine. Messages on that Mac is already signed in and can send a normal text.
- The iPhone you already use, on **the same Apple ID**, so the texts you send show up on the Mac.
- A Grok Bot account. The bot template is a set of instructions you paste in. This download is not a pre-made link on x.ai.
- Python 3.9 or newer. On a Mac, the Xcode Command Line Tools provide it (`xcode-select --install` if Terminal says python3 is missing).
- Homebrew, only because that is how imsg is installed. https://brew.sh

You do not need a paid county data feed. You do not turn off any macOS security switch.

## The three phases

### 1. The bridge (about 10 minutes)

imsg is a small program that reads the Messages database already on your Mac and sends through the Messages app. Your iPhone and Mac stay in sync because they share an Apple ID. That is the bridge: phone, Mac, iMessage, and the bot.

You will:

1. Unzip this folder somewhere you can find, such as Documents.
2. Create a Grok Bot and paste in `bot-template/SYSTEM_PROMPT.md` as its instructions.
3. In Grok Bot, leave **Execution on Local Computer** on **Ask every time**. The first time it wants the Mac, the card says Allow once, Always allow, Never, or Deny once. Choose **Allow once** for each command. The settings path in the Grok Bot docs (checked 2026-10-23) is Settings → General → Bot → Execution on Local Computer, and later Settings → Computer → Computers.
4. Tell the bot: **"Start phase 1. Ask me before you change anything."**
5. It will show you a plan (`bash install.sh` changes nothing). After you say yes, `bash install.sh --apply` installs imsg **only if it is not already installed**, with this exact command:

   ```
   brew install steipete/tap/imsg
   ```

6. Click the two permission screens in the next section.
7. Make one group in Messages named **Command Center**. Apple will not deliver an iMessage to your own number, so "texting yourself" is not a setup this tool can do. The other member of the group should be an address you control. Anyone in the group can read the chat. Do not add a client, an agent, or a title company.
8. The bot lists chats, you point at the Command Center row, and it saves that id. It then ignores every other thread.

You can do the same steps yourself in Terminal if you would rather not hand the bot the keyboard yet. `cd` into the folder, run `bash install.sh`, read it, then `bash install.sh --apply`.

### 2. Plug in your tools

Tell the bot which tools the team actually uses. You connect them in Grok Bot's **Connect apps** screen (the catalog is also at grok.com/connectors) and you sign in on the secure page. Do not paste passwords into the chat.

The connector docs checked on 2026-10-23 name Box, Canva, Gamma, GitHub, Linear, Meltwater, Notion, S&P Global, and Vercel as examples, and tell you to browse the live catalog. A separate FAQ also mentions Gmail, Google Drive, Google Calendar, Slack, Salesforce, HubSpot, and GitHub. **The list that matters is the one on your account.** Zoom was not on the pages that were checked. If it is missing for you, the bot should say so and draft a message you can paste, not pretend Zoom is connected.

Before any of that is connected, two lists still work on the Mac, and only after a YES:

- a pipeline (address, status, next step)
- a to-do list, up to 20 lines in one approval

They live in a private folder in your home directory, `~/.imessage-command-center`. They are a starter list, not a CRM.

### 3. Run the day from the thread

Text the Command Center group. The bot reads that chat, tells you what it intends to do, and waits.

| You want | What happens |
|---|---|
| Comps | It uses a source you connected, or it says it cannot see one. It does not fill in a price. |
| An offer | The first YES returns a draft in the chat. A second YES, with the exact phone number or email and the exact words, is what sends it. |
| Buyers | It can read a list you connected. It does not text buyers unless a YES names them. |
| Pipeline and CRM | Local list first. Your real CRM only after it is connected and the YES names the update. |
| Schedule and travel | Read or draft first. It does not buy a flight or send an invite, and it does not invent a confirmation code. |
| The team | A Slack (or other) post is a draft until you YES that exact post. |
| 20 to-dos | Send the 20 lines in one text. The ask repeats them. One YES saves them. It does not do the tasks. |

More word-for-word texts: [prompts/real-estate-texts.md](prompts/real-estate-texts.md).

A text sits in a queue until the bot is awake to read it. Say **"check my texts"** when you open the bot. The optional login watcher (`bash install.sh --apply --launchd`) only copies new command-chat texts into that queue. It never sends. Grok Bot's cloud computer is a different machine from this Mac. This project did not verify a scheduled routine reaching the Mac while the Grok Bot app is closed, so do not count on an unattended overnight loop.

## Permission screens

These are clicks. The install script cannot turn them on, and it should not try.

**Full Disk Access** — so imsg can read `~/Library/Messages/chat.db`.

1. System Settings → Privacy & Security → Full Disk Access.
2. Click +, press Cmd-Shift-G, and add **Terminal** (`/System/Applications/Utilities/Terminal.app`).
3. Add the imsg program too. In Terminal, `which imsg` prints the path. On Apple silicon that is often `/opt/homebrew/bin/imsg`. On Intel Macs it is often `/usr/local/bin/imsg`.
4. Turn both switches on. Quit Terminal completely and open it again. macOS only notices this permission at launch.

**Automation → Messages** — so a send can ask Messages.app to deliver it.

The first real send pops a dialog: the app wants to control Messages. Click OK. If you missed it: System Settings → Privacy & Security → Automation → Messages, and turn the switch on for Terminal (or whichever app is running the command).

**Contacts** — optional. The commands this guide uses skip Contacts. You can ignore that prompt.

**Text Message Forwarding** — only if you also want SMS, not just iMessage. On the iPhone: Settings → Messages → Text Message Forwarding, and include this Mac. That label was not re-checked on a phone for this write-up. iMessage itself does not need it.

If you install the login watcher and it still cannot read Messages while Terminal can, macOS is granting Full Disk Access to a different parent app. Use `python3 -m icc doctor` from Terminal until that is sorted. Which icon a login item shows in Full Disk Access was not confirmed on a machine here.

## Approval rules

The command chat is the only place an approval counts.

- The bot's question starts with `[icc]` and includes an 8-character id.
- You reply with `YES a1b2c3d4` or `👍 a1b2c3d4` as the **entire** message. `NO a1b2c3d4` cancels.
- A thumbs-up inside a longer text does not count. A tapback (the bubble you press and hold) does not count: imsg does not include those rows in history, so this tool cannot see them.
- If two things are waiting, a bare `YES` does not pick one. Use the id.
- A later `NO`, before the step runs, beats an earlier `YES`.
- The ask expires after 12 hours.
- Messages marks your own texts as from you, because the iPhone and the Mac share an Apple ID. Someone else's text in the group cannot approve and cannot command.
- An iMessage to another person is sent once. If Messages is unsure whether it went out, the tool stops and tells you to look at the thread. It will not automatically send it again.
- Outgoing numbers are E.164 (`+15555550123`) or an email. A first name is refused, so "Mom" cannot match the wrong contact.

The only texts the tool sends without a YES are the approval question, and a short clarifying question, both in the Command Center chat.

Offers are drafts. They are not legal advice. A comp the bot could not look up is not a number. Zoning, title, and the contract still get checked the way you already check them.

## Try the gate without a Mac

The approval rules are plain Python. On any computer, from this folder:

```
python3 -m unittest discover -s tests -v
bash tests/test_install.sh
```

Those tests use a fake imsg. They do not read or send real messages. `bash install.sh --apply` on a computer that is not a Mac refuses and changes nothing. The dry run (`bash install.sh`) is always safe to read.

Checked 2026-10-23: the unit tests and the install-script test passed in this project. imsg itself was not installed here, because this environment is not a Mac.

## Commands, if you want them

```
bash install.sh                      # plan only
bash install.sh --apply              # install imsg if missing
python3 -m icc doctor                # permissions, no message bodies
python3 -m icc chats --limit 20      # pick the Command Center id
python3 -m icc use-chat --id 42      # 42 is an example; use your id
python3 -m icc sync                  # queue new texts; the first run only marks your place
python3 -m icc inbox
python3 -m icc pipeline              # read the local list
python3 -m icc todos
bash uninstall.sh                    # plan to remove the watcher
bash uninstall.sh --apply            # remove the watcher; imsg stays
bash uninstall.sh --apply --remove-state
```

Day to day you should not need these. The bot runs them. `propose`, `release`, `commit`, and `reply` are there so the YES check is a program, not a promise in a prompt.

To update imsg later, after you mean to: `brew upgrade imsg`. The installer does not upgrade a copy that is already there.

## Troubleshooting

| What you see | What to do |
|---|---|
| `unable to open database file` or `authorization denied` | Full Disk Access, then quit and reopen Terminal. If the switch is already on, turn it off and on again. imsg's docs call that a stale grant. |
| `Not authorized to send Apple events to Messages (-1743)` | Automation → Messages is off, or it was granted to a different app than the one running the command. |
| `imsg` not found | `bash install.sh --apply` has not been run, or Homebrew is missing. |
| Doctor works, but a text never shows up in the inbox | The Mac slept, Messages is signed out, or the text was not in the Command Center group. Run `python3 -m icc sync` after you send a new test. The first sync does not import old texts on purpose. |
| The bot says it is waiting | It is. Reply with the exact `YES` line in the group, then tell the bot to check again. |
| A send may have gone out | Look at Messages before you ask again. The tool will not send a second copy of an uncertain text. |

## What was checked, and what was not

Checked 2026-10-23 from the upstream pages, not by running them on a Mac:

- imsg exists, is MIT licensed, requires macOS 14 or newer, and installs with `brew install steipete/tap/imsg`. https://github.com/openclaw/imsg
- Reads need Full Disk Access for `~/Library/Messages/chat.db`. Sends need Automation permission for Messages.app. Basic send, history, and watch do **not** need SIP turned off. `imsg chat-create` and the private API features do. This project does not use those.
- `imsg history` is newest-first and hides tapback rows. `imsg history --chat-id --limit --no-contacts --json` and `imsg chats --limit --no-contacts --json` are documented commands.
- `imsg send --chat-id` and `imsg send --to --text` are the documented sends. A timeout or a `may_have_completed` result is treated as uncertain and is not retried.
- Grok Bot's cloud computer is separate from your Mac. Local commands are a separate switch, default Ask every time. https://docs.x.ai/grok-bot/computer-and-apps and https://docs.x.ai/grok-bot/approvals-security-and-privacy
- Custom MCP connectors need a public HTTPS URL. This project does not open one. https://docs.x.ai/grok/connectors

Not verified on hardware for this project:

- The Full Disk Access icon macOS shows for the optional login watcher.
- A Grok Bot routine reaching the Mac while the desktop app is closed.
- The iPhone menu label for Text Message Forwarding.
- That the connector names in a third-party FAQ match your Connect apps screen today. Look at the screen.

Other real projects were considered and not used as the default. [mac-messages-mcp](https://github.com/carterlasalle/mac_messages_mcp) is a real MIT server for local MCP clients; its changelog says a `confirm=true` flag is not human confirmation, and Grok Bot's cloud agent cannot call a server that only listens on your Mac. [grokbot-imessage-skill](https://github.com/jeffhuber/grokbot-imessage-skill) is a real MIT helper aimed at Grok, and its send check is a dialog on the Mac rather than a reply in iMessage. [chatwire](https://github.com/allenbina/chatwire) is a real MIT bridge and was still described as beta. A tunnel that exposes Messages to the internet was rejected on purpose.

## Example texts

```
Pull comps for 418 West Pine Street. Use only a source I have connected. If you cannot see one, say so. Do not email anyone.
```

```
Draft a cash offer for 418 West Pine Street. Leave it in this chat. Do not send it.
```

```
Add 418 West Pine Street to my pipeline. Status: offer. Next step: call the listing agent tomorrow.
```

The reply you send back is the whole message:

```
YES a1b2c3d4
```

The rest of the library, including a 20-line to-do list, is in [prompts/real-estate-texts.md](prompts/real-estate-texts.md).
