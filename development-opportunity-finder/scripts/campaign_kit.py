#!/usr/bin/env python3
"""Step 6: get the campaign ready to start. Writes copy and load-in steps. Sends nothing.

Writes (in --output-dir, default out/campaign):
  offer_letter.txt        a short letter to land owners, with {{merge_fields}}
  estate_letter.txt       a gentler letter for "Estate of" / heirs / deceased owners
  mail_merge.csv          mail.csv plus the right letter filled in per owner (letter_type column)
  cold_call_opener.txt    a 30-second opener, a voicemail, and answers to common pushback
  sms_opener.txt          first texts, ONLY for numbers in your consent file (marketing/sms.csv)
  LOAD_INTO_YOUR_TOOLS.md step by step: mailer, dialer, texting tool, CRM
  campaign_checklist.md   what to check before anything goes out

Usage:
  python scripts/campaign_kit.py --marketing-dir out/marketing --your-name "Pat Lee" \
      --company "Lee Land Co" --phone "555-555-0100" --buyer "home builders"

Anything you leave out stays as a [PLACEHOLDER] for you to fill in. Edit the copy
so it sounds like you. Do not promise a price before you have run the numbers.
"""
import argparse, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import read_rows, write_rows  # noqa: E402

LETTER_NOTE = """[Before you send: if you plan to assign this contract or double close, read the
"State wholesaling / assignment rules" section in marketing/COMPLIANCE.md. PA, IL, VA, MD,
OH, OK and TX have disclosure or license rules. Delete this note before printing.]

"""

ESTATE = """{{today}}

Personal Representative, Estate of {{decedent}}
{{mail_street}}
{{mail_city}}, {{mail_state}} {{mail_zip}}

Re: land at {{property_line}} ({{acres}} acres, {{county}})

Hello,

My name is {{your_name}} with {{company}}. County records show this land is held by an estate, and I'm sorry if this letter reaches you during a hard time.

There is no rush and nothing you need to do. If, now or later, the estate's personal representative decides that selling the land would help, I buy land in {{county}} and would be glad to make a simple, no-obligation offer. I can work around the estate's timeline and with the estate's attorney.

I understand that only the person the probate court has given authority over the estate (the personal representative or executor) can agree to a sale, and that some sales also need the court's approval. I'm happy to talk with that person or the estate's attorney.

If you'd like to talk, call or text me at {{your_phone}}. If you'd rather not hear from me, let me know at the same number and I won't contact you again.

With respect,
{{your_name}}
{{company}}
{{your_phone}}
"""

LETTER = """{{today}}

{{first_name_or_owner}}
{{mail_street}}
{{mail_city}}, {{mail_state}} {{mail_zip}}

Re: your land at {{property_line}} ({{acres}} acres, {{county}})

Hi {{first_name_or_there}},

My name is {{your_name}} with {{company}}. I buy land in {{county}}, and I work with {{buyer}} who are looking for property like yours.

I'd like to make you a fair, no-obligation offer for your {{acres}} acres. If you sell to me:
- you choose the closing date
- in most cases I can cover the normal closing costs
- there are no agent commissions
- you don't have to clean up or improve anything

If you've thought about selling, or you just want to know what it's worth to a buyer today, call or text me at {{your_phone}}. If the timing isn't right, no problem. Keep this letter for later.

Thank you,
{{your_name}}
{{company}}
{{your_phone}}

If you'd rather not hear from me, call or text {{your_phone}} and I'll take you off my list.
"""

CALL = """COLD CALL OPENER (about 30 seconds). Talk like a person, not a script.

"Hi, is this {{first_name}}? ... Hey {{first_name}}, this is {{your_name}} with {{company}}. I'll be quick. I'm calling about your land on {{property_line}} in {{county}}. I work with {{buyer}} who are buying land in that area right now, and I wanted to ask: would you ever consider an offer on it, or is that something you plan to hold onto?"

If yes or maybe:
"Great. Can I ask a couple of quick questions so I don't waste your time?"
  1. How long have you owned it? Anything going on with it now (farming, leased, for sale)?
  2. Do you know if it has water, sewer or power at the road?
  3. If the price was right, when would you want to close?
  4. Do you have a number in mind?
"Thanks. Let me run the numbers with my buyer and call you back by {{callback_day}}. What's the best number and time?"

If no:
"Totally understand. Would it be OK if I checked back in six months, or would you rather I take you off my list?" (If they say take me off: do it, and mark it in your CRM today.)

IF THE OWNER HAS PASSED AWAY (estate / heirs)
"I'm very sorry for your loss. I didn't know. I'll be brief: I buy land in {{county}}. There's no rush at all. Would it be all right if I sent a letter to the estate's personal representative or attorney, or would you prefer I not reach out again?"
Do not push for a price on this call, and never suggest that an heir can sell. Only the court-appointed personal representative
(with letters testamentary / of administration, and court approval where required) can. Note it in your CRM.

VOICEMAIL left live, by you, during a manually dialed call (under 20 seconds). This kit does not support ringless voicemail,
voicemail drops or prerecorded messages.
"Hi {{first_name}}, this is {{your_name}} with {{company}}. I'm calling about your land on {{property_line}} in {{county}}. I may have a buyer for it. Call or text me at {{your_phone}}. Again, {{your_phone}}. Thanks."

COMMON PUSHBACK
- "How did you get my number?" -> "Property ownership is public record, and I use a data service to find contact info. If you'd rather I not call, I'll take you off my list right now."
- "What's it worth?" -> "I don't want to throw out a number before I look at it with my buyer. Can I ask two quick questions about the land?"
- "It's not for sale." -> "Understood. Is that a never, or a not-right-now?"
- "Send me something in writing." -> "Happy to. What's the best mailing or email address?"

Before you dial: scrub against the National + state + internal DNC lists yourself (a provider flag is not a scrub), call only inside
the row's call_window, dial manually (a person dials or clicks one number at a time, with no power, predictive or multi-line dialer),
and read marketing/COMPLIANCE.md.
"""

SMS = """ONLY text numbers in marketing/sms.csv: they are built from YOUR consent file (--sms --consent-file).
Skip-trace numbers are not consent. See marketing/COMPLIANCE.md.

FIRST TEXT, option A
"Hi {{first_name}}, this is {{your_name}} with {{company}}. Are you the owner of the land on {{property_line}} in {{county}}? I may have a buyer for it. Reply STOP to opt out."

FIRST TEXT, option B
"Hi {{first_name}}, {{your_name}} here ({{company}}). I'm buying land near {{property_line}} for {{buyer}}. Would you consider an offer on yours? Reply STOP to opt out."

IF THEY REPLY YES / MAYBE
"Thanks {{first_name}}! What's a good time for a quick 5-minute call today or tomorrow?"

IF THEY REPLY STOP / NO
Remove them right away, mark it in your CRM and add the number to your suppression list (--stop-replies). Do not text again.

Rules: say who you are in the first text, keep "Reply STOP to opt out", no links in the first text,
no all-caps or "URGENT", and only text inside your state's allowed hours.
"""

LOAD = """# Load the lists into your tools (nothing has been sent)

The files are in your output folder:
- marketing/mail.csv and campaign/mail_merge.csv -> your mail house
- marketing/cold_call.csv -> your dialer
- marketing/sms.csv -> your texting tool (only exists if you ran with --sms and a consent file)
- marketing/crm_import.csv -> your CRM (a CRM import file: you import it; nothing connects to your CRM)

Every tool's screens look a little different. The steps below are the same idea everywhere.

## 1. CRM first (so every reply has a home)
1. In your CRM (REsimpli, Podio, InvestorFuse, GoHighLevel, HubSpot, a Google Sheet...) find Import or Upload CSV.
2. Upload marketing/crm_import.csv.
3. Map the columns: owner -> name, mail_* -> mailing address, property_address / apns -> property, phone1-3 -> phones,
   phone_status -> a custom field, email1 -> email, tags -> tags. phone1-3 only hold scrubbed numbers; a blank phone with
   phone_status "not scrubbed, do not dial" means exactly that. Keep best_rank, tier and motivation_signals as custom fields if your CRM allows it.
4. Put them in a "Development land" list or pipeline stage like "New lead - not contacted".

## 2. Mail (start here if you only pick one channel)
1. Open campaign/offer_letter.txt (and estate_letter.txt for estate owners) and edit them in your own voice. Fill in every [PLACEHOLDER].
   If you will assign the contract, read the state wholesaling section of marketing/COMPLIANCE.md first.
2. In your mail house (Ballpoint Marketing, Yellow Letter HQ, Open Letter Marketing, Click2Mail, Thanks.io, or your own printer),
   start a new campaign and upload marketing/mail.csv (or campaign/mail_merge.csv if you want the letter text per owner).
3. Map: owner or first_name/last_name -> recipient, mail_street / mail_city / mail_state / mail_zip -> address.
   Estate owners: confirm the probate case, the personal representative's letters, any court approval and title before an offer.
4. Approve the proof yourself before anything prints. Plan 2-3 touches about 3-4 weeks apart.

## 3. Cold calls
1. cold_call.csv only has numbers that passed YOUR OWN National + state DNC scrub in the last 31 days. Numbers that still
   need a scrub are in cold_call_NEEDS_SCRUB.csv (call_eligibility = blocked): scrub them, then re-run with --dnc-scrubbed.
   Every row starts as call_eligibility = needs_review. A clean scrub is not permission to call: check the time_zone and
   calling hours, your own do-not-call list, your state's rules and registration, then mark the rows reviewed_for_campaign.
2. Load cold_call.csv into a tool where a person dials or clicks one number at a time (manual or click-to-call mode only).
   Do not use power, predictive or multi-line dialing, ringless voicemail, voicemail drops, prerecorded or AI voice:
   this kit does not support them.
3. Map phone1, phone2, phone3 as phones and first_name / property_address / call_window so they show on screen.
4. Load campaign/cold_call_opener.txt as the script. Call only inside each row's call_window; rows whose call_window_check
   says VERIFY need you to check the hours and mark hours_verified = Y in your call review.
5. Log every outcome back in the CRM.

## 4. Texts (only to people who gave you consent)
1. sms.csv only exists when you ran with --sms, --sms-sender and a consent file that confirms consent for this sender, this
   purpose and this method (consented_to, purpose, method, confirmed = Y). No file = no texting. Rows start as needs_review.
2. Read marketing/COMPLIANCE.md first. Most texting platforms need 10DLC registration.
3. Import sms.csv, map sms_phone as the phone, first_name and property_address as merge fields.
4. Use a first text from campaign/sms_opener.txt. Turn on automatic STOP handling, and export STOP replies into the
   kit with --stop-replies so they are suppressed everywhere.

## 5. Re-run it
Run it weekly by saying "refresh my county" to Claude (automatic scheduling needs separate setup). County sales
and owner data change slowly, so weekly is plenty. Your suppression list is applied on every run.
marketing/new_owners.csv has only the owners who are new since the last run, so you only import the new ones.
"""

CHECK = """# Before anything goes out

Do campaign/STATE_AND_JURISDICTION_CHECK.md first. The items below are separate checks; one never covers another.

- [ ] Zoning on the top parcels checked with the city or county planning office
- [ ] Satellite review done (satellite/satellite_review.csv has a verdict on every top parcel)
- [ ] Ownership spot-checked on the county assessor site for the top 10
- [ ] Companies and trusts researched (skiptrace/entities_to_research.csv)
- [ ] Letter, call opener and texts edited in your voice, every [PLACEHOLDER] filled
- [ ] State wholesaling / jurisdiction check done (campaign/STATE_AND_JURISDICTION_CHECK.md)
- [ ] DNC scrub: your own federal + state + internal scrub, with scrubbed_by and vendor, within 31 days (provider flag is not enough)
- [ ] Calling hours: call_window on every row; VERIFY rows checked by you (hours_verified = Y)
- [ ] Consent: texting only numbers in your consent file (consent_evidence recorded)
- [ ] 10DLC: your texting brand and campaign registered through your texting provider
- [ ] Opt-outs: the latest opt-outs and do-not-contact requests imported from every system your team uses, plus manual requests
- [ ] Data license verified before redistribution or resale
- [ ] State wholesaling / assignment disclosures handled if you will assign (marketing/COMPLIANCE.md)
- [ ] Estate owners get estate_letter.txt, not the standard letter (living trusts get the standard letter: the trustee signs)
- [ ] For estates, you will only sign with the personal representative / executor (letters testamentary) or as your attorney advises
- [ ] Estate authority check before any offer: probate case number, a copy of the letters testamentary / letters of administration,
      and whether the court must approve or confirm the sale (some states and some estates require it). No court case yet = no contract.
- [ ] No price is printed in any letter (the kit never fills one in; you set an offer after you run the numbers)
- [ ] Suppression list up to date (everyone who asked you to stop, every STOP reply)
- [ ] Calls only to cold_call.csv rows you marked reviewed_for_campaign, inside calling hours (time_zone column)
- [ ] Telemarketer registration done in any state that requires it (marketing/COMPLIANCE.md)
- [ ] Your buyer agrees with the buy box (sizes, zoning, price per acre)
- [ ] You know your numbers: what your buyer pays, your offer, your margin
"""


ESTATE_RE = re.compile(r"\b(ESTATE OF|EST OF|HEIRS?|DECEASED|DECD|DEC'D)\b|\bESTATE\b", re.I)
NOT_ESTATE = re.compile(r"\b(TRUST|TRUSTEES?|TR|REVOCABLE|LIVING|REAL ESTATE|LIFE ESTATE|ESTATES? (LLC|INC|CO|CORP|LP))\b", re.I)


# State notes for the wholesaling / jurisdiction check. Not legal advice; laws change every year.
STATE_NOTES = {
    "PA": "Act 52 of 2024: marketing an equitable interest is brokerage that needs a license; disclosures and a seller cancellation right. Philadelphia has its own wholesaler license.",
    "IL": "Public Act 101-0357: wholesaling more than once in 12 months needs a real estate license.",
    "VA": "Repeatedly marketing contracts as a business can be brokerage that needs a license.",
    "MD": "Since Oct 1, 2025: written notice to the owner that you may assign, and to the assignee that you hold only an equitable interest.",
    "OH": "ORC 5301.95: separate, conspicuous written disclosure before contracting on residential property you intend to assign.",
    "OK": "Predatory Real Estate Wholesaler Prohibition Act (and SB 1075): disclosure, notice to seek legal advice, 2-business-day cancellation, license to market.",
    "TX": "SB 1577 (2023): tell buyers in writing that you hold only an equitable interest; TREC rules apply.",
}
STATE_CHECK = """# State wholesaling and jurisdiction check (do this BEFORE you prepare the campaign)

This is one item. It does not cover consent, 10DLC registration, DNC scrubbing or calling hours:
each of those is its own check in campaign_checklist.md and marketing/COMPLIANCE.md.

States in these lists (land and owner mailing addresses): {states}

For each state above, and the state where your business is:
1. Wholesaling / assignment: will you buy and close, assign the contract, or double close? If you
   assign or market a contract, check that state's wholesaling law and license rules.
{notes}
2. Jurisdiction: are you allowed to make offers and sign contracts there under your own entity?
   Some states need a local license, registration or a specific contract form.
3. Estates: never imply an heir can sell. Check the probate case, the personal representative's
   appointment and letters, whether the court must approve the sale, and title.
4. Data license: verify the data license before redistribution or resale.
5. Write down who checked it and when: ____________________ (name, date, counsel)

Search "[state] real estate wholesaling law [year]" and confirm with a local real estate attorney.
"""


def is_estate(owner):
    """Estate / heirs owners get the gentle letter. Living trusts, 'real estate' companies and life estates do not:
    a living trust's trustee is alive and signs, so the standard letter is right."""
    o = str(owner or "")
    if re.search(r"\b(ESTATE OF|EST OF)\b", o, re.I) and not re.search(r"\bREAL ESTATE\b", o, re.I):
        return True
    return bool(ESTATE_RE.search(o)) and not NOT_ESTATE.search(o)


def decedent_name(owner):
    """'SMITH, JOHN ESTATE' / 'ESTATE OF JOHN SMITH' / 'SMITH JOHN HEIRS' -> 'SMITH, JOHN' (for 'Estate of ...')."""
    n = re.sub(r"\b(ESTATE OF|EST OF|ESTATE|EST|HEIRS?( OF)?|DECEASED|DECD|DEC'D|ET AL|ETAL)\b", " ", str(owner or ""), flags=re.I)
    n = re.sub(r"\s+", " ", n).strip(" ,&")
    return n or str(owner or "").strip()


def fill(text, ctx):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(ctx.get(m.group(1), "{{" + m.group(1) + "}}")), text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--marketing-dir", required=True)
    ap.add_argument("--output-dir")
    ap.add_argument("--your-name", default="[YOUR NAME]")
    ap.add_argument("--company", default="[YOUR COMPANY]")
    ap.add_argument("--phone", default="[YOUR PHONE]")
    ap.add_argument("--buyer", default="home builders and developers", help='who you are buying for, e.g. "home builders"')
    ap.add_argument("--callback-day", default="[DAY]")
    ap.add_argument("--state", default="", help="extra state(s) to include in the wholesaling / jurisdiction check, e.g. NC,SC")
    a = ap.parse_args(argv)
    out = a.output_dir or os.path.join(os.path.dirname(os.path.abspath(a.marketing_dir)), "campaign")
    os.makedirs(out, exist_ok=True)
    me = {"your_name": a.your_name, "company": a.company, "your_phone": a.phone, "buyer": a.buyer, "callback_day": a.callback_day}
    for name, body in (("offer_letter.txt", LETTER_NOTE + LETTER), ("estate_letter.txt", LETTER_NOTE + ESTATE),
                       ("cold_call_opener.txt", CALL), ("sms_opener.txt", SMS)):
        with open(os.path.join(out, name), "w") as f:
            f.write(fill(body, me))
    with open(os.path.join(out, "LOAD_INTO_YOUR_TOOLS.md"), "w") as f:
        f.write(LOAD)
    with open(os.path.join(out, "campaign_checklist.md"), "w") as f:
        f.write(CHECK)
    states = set()
    crm_path = os.path.join(a.marketing_dir, "crm_import.csv")
    if os.path.exists(crm_path):
        for r in read_rows(crm_path):
            for k in ("state", "mail_state"):
                v = str(r.get(k) or "").strip().upper()
                if re.fullmatch(r"[A-Z]{2}", v):
                    states.add(v)
    states |= {s_.strip().upper() for s_ in (a.state or "").split(",") if s_.strip()}
    notes = "\n".join(f"   - {st}: {STATE_NOTES[st]}" for st in sorted(states) if st in STATE_NOTES) or \
        "   - No state-specific note in this kit for these states. That does not mean there is no rule: check."
    with open(os.path.join(out, "STATE_AND_JURISDICTION_CHECK.md"), "w") as f:
        f.write(STATE_CHECK.replace("{states}", ", ".join(sorted(states)) or "unknown (no state column)").replace("{notes}", notes))
    mail_path = os.path.join(a.marketing_dir, "mail.csv")
    merged = []
    if os.path.exists(mail_path):
        import datetime as dt
        today = dt.date.today().strftime("%B %d, %Y").replace(" 0", " ")
        for r in read_rows(mail_path):
            first = (r.get("first_name") or "").strip() if r.get("is_company") != "Y" else ""
            props = [p for p in str(r.get("property_address") or "").split(";") if p.strip()]
            ctx = dict(me, today=today, first_name_or_owner=(f"{first} {r.get('last_name', '')}".strip() if first else r.get("owner", "")),
                       first_name_or_there=first or "there", mail_street=r.get("mail_street", ""), mail_city=r.get("mail_city", ""),
                       mail_state=r.get("mail_state", ""), mail_zip=r.get("mail_zip", ""),
                       property_line=(props[0].strip() + (f" and {len(props) - 1} more" if len(props) > 1 else "")) if props else "your parcel",
                       acres=r.get("total_acres", ""), county=r.get("county") or "your county")
            ctx["owner"] = r.get("owner", "")
            ctx["decedent"] = decedent_name(r.get("owner", ""))
            est = is_estate(r.get("owner"))
            merged.append(dict(r, letter_type="estate" if est else "standard", letter_text=fill(ESTATE if est else LETTER, ctx)))
        write_rows(os.path.join(out, "mail_merge.csv"), merged)
    left = sorted(set(re.findall(r"\[[A-Z ]+\]", " ".join(me.values()))))
    print(f"Campaign kit written to {out}: offer + estate letters, {len(merged)} merged letters "
          f"({sum(1 for m in merged if m['letter_type'] == 'estate')} estate), call opener, SMS openers, load-in steps."
          + (f" Fill in: {', '.join(left)}." if left else "") + " Nothing was sent.")
    return out


if __name__ == "__main__":
    main()
