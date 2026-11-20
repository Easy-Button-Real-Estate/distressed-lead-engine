#!/usr/bin/env python3
"""Step 5: turn the ranked parcels into marketing-ready lists, one per channel. Outreach is blocked by default.

Inputs
  --ranked     out/parcels_ranked.csv (score_parcels.py, plus split/ADU signals if you ran them)
  --traced     out/skiptrace/owners_traced.csv (skip_trace.py import), optional
  --satellite  out/satellite/satellite_review.csv (filled in), optional

Safe-by-default rules
  * SUPPRESSION: --suppress suppress.csv (phone, address, owner, date, channel) and --stop-replies
    (numbers that texted STOP) are merged into a master list kept in the state folder and applied
    to EVERY list on EVERY run. Owners suppressed for "all" are left out of every file.
  * HOLD: when the suppression list may be out of date (--hold-phone-sms, set by run_pipeline when the
    START_HERE banner shows), no phone or text output is written at all: no cold_call.csv,
    cold_call_NEEDS_SCRUB.csv or sms.csv, and the phone columns of crm_import.csv are blank.
  * CALLS: cold_call.csv only has numbers that passed YOUR OWN complete DNC scrub within the last
    31 days: federal + state + internal (lists_checked), with scrubbed_by and vendor recorded
    (--dnc-scrubbed with scrub_date, or --dnc-scrub-date). Every other number goes to
    cold_call_NEEDS_SCRUB.csv with call_eligibility = blocked. A provider's DNC flag is not a scrub.
  * CRM import: phone1-3 carry only scrubbed numbers. Otherwise they are blank and phone_status says
    "not scrubbed, do not dial".
  * call_eligibility: needs_review (default) / blocked / reviewed_for_campaign. Only YOU set
    reviewed_for_campaign (--call-review file). A clean scrub alone never means a number is legal to call.
  * time_zone, call_window (stricter of mailing-ZIP zone and area-code zone) and call_window_check on
    every call row. A row whose check says VERIFY can only become reviewed_for_campaign when your
    call-review file also has hours_verified = Y.
  * TEXTS: sms.csv only with --sms, --sms-sender and a consent file whose rows confirm consent for
    this sender (consented_to), this purpose and this method, with confirmed = Y. Each row gets
    sms_review_status (needs_review by default). Skip-trace data is never consent.
  * litigator numbers and DNC-flagged numbers are removed.
  * one row per OWNER; trace_status is "not traced", "no hit" or "hit".

Outputs (in --output-dir, default out/marketing)
  mail.csv, cold_call.csv, cold_call_NEEDS_SCRUB.csv, sms.csv (only as above), crm_import.csv
  (a CRM import file you import yourself), new_owners.csv, suppressed_this_run.csv,
  COMPLIANCE.md, marketing_summary.txt

Nothing is sent. These are files for you to load into your own tools.
"""
import argparse, datetime as dt, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import clean_phone, norm, num, parse_date, read_rows, split_owner, write_rows  # noqa: E402
import suppression  # noqa: E402
import timezones  # noqa: E402

VOICE_LINE = ("Live, manually dialed calls only. This kit does not support ringless voicemail, voicemail drops, prerecorded or AI "
              "voice, or autodialers to any number; those need prior express written consent and separate legal review. Some states "
              "(e.g. FL, OK) have their own autodialer laws.")
MANUALLY_DIALED = timezones.MANUALLY_DIALED
OPT_OUT_SENTENCE = suppression.OPT_OUT_SENTENCE
MANUAL_SENTENCE = suppression.MANUAL_SENTENCE
DATA_LICENSE_LINE = "Verify the data license before redistribution or resale."
NOT_SCRUBBED = "not scrubbed, do not dial"
HOLD_STATUS = "held: suppression list may be out of date, do not dial"
ESTATE_RULE = ("Never imply that an heir can sell. Before any offer on an estate-owned parcel, check the probate case (court and case "
               "number), that a personal representative has been appointed and holds current letters (testamentary or of "
               "administration), whether the court must approve the sale, and title (a title company confirms who can convey).")
RVM_PARAGRAPH = ("Never create, recommend, or launch a ringless voicemail campaign as part of this workflow. Ringless voicemail and "
                 "prerecorded/artificial voice outreach require separate legal review and applicable consent verification. Do not "
                 "assume a number eligible for ordinary calling is eligible for these methods.")
PREPARED_NOT_APPROVED = ("These are research and marketing preparation lists, not approved contact lists. Before launching a campaign, "
                         "verify the applicable consent, suppression, registration, calling-hour and jurisdictional requirements.")
# States that keep their own do-not-call list (in addition to the National Registry). Check your state's
# attorney general / consumer-protection site: lists and fees change.
STATE_DNC_LISTS = ("Colorado, Florida, Indiana, Louisiana, Massachusetts, Mississippi, Missouri, Oklahoma, Pennsylvania, "
                   "Tennessee, Texas and Wyoming")
SCRUB_PARTS = ("federal", "state", "internal")
from skip_trace import owner_key  # noqa: E402

COMPLIANCE = """# Before you mail, call or text (read this)

**This is a screening tool and a reminder list, not legal advice.** Verify every point with counsel
(a lawyer who handles TCPA / telemarketing and real estate contracts where you and the owner are)
before you contact anyone.

- Jurisdiction this run was built for: {jurisdiction}
- These notes were last verified by the kit author: {last_verified} (public sources; laws change)
- Verified for your business by counsel: ____________________ (name, date)

**{prepared}**

## Outreach is blocked by default
- Suppression: your do-not-contact list (state/suppression.csv) is applied to every list on every run.
  {opt_out}
  {manual}
  Save each export in the suppress/ folder (read on every run) or pass --suppress; STOP replies go in with
  --stop-replies. Suppression is cumulative: rows are only added. Never remove a suppression row.
- While the suppression list may be out of date (START_HERE banner), every phone and text output is held:
  no cold_call.csv, no sms.csv, phones blank in crm_import.csv.
- crm_import.csv carries only scrubbed phones. Any other phone is left blank with phone_status
  "not scrubbed, do not dial".
- cold_call.csv has only numbers that passed YOUR OWN complete DNC scrub (federal + state + internal, below) in the last 31 days
  (the federal rule: scrub at least every 31 days). Everything else is in cold_call_NEEDS_SCRUB.csv.
- Every call row starts as call_eligibility = needs_review. A clean scrub alone does not make a call
  legal: you still need the right calling hours, your internal do-not-call list, your state's rules,
  any registration your state requires, and the number must belong to the owner.

## What a complete DNC scrub is
A number counts as scrubbed only when, within the last 31 days, you checked it against ALL of:
1. the National Do Not Call Registry (through your own registry account / Subscription Account
   Number, or a dialer / data vendor that uses yours),
2. your state's own do-not-call list, if it has one. States with their own list include
   {state_lists} (check your state attorney general's site; lists and fees change), and the
   list of every state you call into,
3. your internal do-not-call list (everyone who asked you to stop; the kit's suppression list is
   part of it).
Record it in the scrub file: phone, dnc (Y/N), scrub_date, lists_checked (for example
"federal; state:NC none; internal"), scrubbed_by (who ran it) and vendor (the DNC service, or
"self (own SAN)"). Rows without all three parts, scrubbed_by or vendor go to cold_call_NEEDS_SCRUB.csv.
A skip-trace provider's "DNC" flag is NOT a scrub.

## DNC scrub and consent are two different things
- Passing a DNC scrub does not give you consent to text or to use an autodialer or prerecorded voice.
- Texting consent must be given by the owner to YOU (this sender), for this purpose (offers to buy
  their land), by a method you can prove (signed form, web form with a consent box). Record
  consented_to, purpose, method, consent_date, consent_source, consent_evidence (where the proof is
  kept: form ID, signed PDF, screenshot with date / IP) and confirmed = Y.
- Revocation: consent can be withdrawn any reasonable way (STOP, "don't text me", a letter, a call).
  Put revoked_date (and how) on the consent row; the kit then rejects the row and adds the number to
  your suppression list. consent_log.csv in this folder is the audit trail of every consent row and
  what the kit did with it. Keep consent proof and revocations at least 5 years.
- Skip-trace data is never consent.

## Mail
- Direct mail to the owner's mailing address is the lowest-risk channel.
- Do not imply you are a government office, the county, or the owner's lender. Never print a price
  you have not worked out yourself; the kit never fills one in.

## Cold calls
**{voice}**

- {manually_dialed}
- Call only rows in cold_call.csv, after you mark them reviewed_for_campaign.
- line_type (mobile / landline / voip / unknown) comes from your skip-trace provider and can be wrong.
  Treat unknown and voip as possible cell phones.
- Calling hours: federal 8am-9pm in the called person's local time. The time_zone column is an
  ESTIMATE from the mailing ZIP / state; a cell phone can be anywhere. Some states are stricter
  (for example FL, OK and MD: 8am-8pm) or limit Sundays / holidays.
- call_window uses two signals, the mailing-ZIP time zone and each phone's area-code time zone, and
  gives the stricter window (legal in every possible zone). When they disagree or a zone is unknown,
  call_window_check says VERIFY: check the calling hours yourself and put hours_verified = Y in your
  call-review file before the row can be reviewed_for_campaign.
- Telemarketer registration: several states (for example FL, TX, UT, WA, AL and LA) require
  telephone solicitors to register, get a license or post a bond before calling into the state.
  Exemptions for real estate vary. Check every state you call into.
- Ringless voicemail counts as a call: the FCC treats it as a call under the TCPA. This kit does not support it.
- {rvm}
- Numbers marked litigator were removed.

## Text messages
- sms.csv is only built with --sms, --sms-sender and a confirmed consent file, and only for those numbers.
- Cold texts to people who never gave you consent carry the most legal risk of any channel.
- 10DLC: US carriers require business texting from regular 10-digit numbers to be registered
  (your brand and each campaign, through your texting platform with The Campaign Registry).
  Unregistered traffic is filtered or blocked, and the registration describes how you got consent:
  keep it consistent with your consent records.
- Every text says who you are and "Reply STOP to opt out". Honor STOP at once and add the number
  to your suppression list (--stop-replies).

## Email
- Include your physical address and an unsubscribe link (CAN-SPAM).

## Estate and heir owners
- {estate_rule}
- An heir is not a seller. Only a court-appointed personal representative with authority (or whoever
  the probate court and title company confirm) can sign. If no probate case is open, do not make an
  offer or sign a contract; suggest the family talk to a probate attorney.
- Living trusts are NOT estates: the trustee signs, and the kit sends them the standard letter.

## Before campaign prep: separate checks (each one is its own item)
1. State wholesaling / jurisdiction check for {jurisdiction}: see campaign/STATE_AND_JURISDICTION_CHECK.md and the
   section below. Check the state where the land is AND the state where you do business.
2. DNC scrub (federal + state + internal, scrubbed_by, vendor, within 31 days).
3. Calling hours (call_window; VERIFY rows need hours_verified = Y).
4. Consent for texts (consent file, consent_evidence).
5. 10DLC registration for any business texting.
6. Telemarketer registration in each state you call into.
7. Data license: {data_license}

## State wholesaling / assignment rules (read before you sign or assign a contract)
If you plan to assign the contract or double close instead of buying, several states now regulate
that. Do not assume vacant land is exempt; check with a local real estate attorney.
- Pennsylvania: Act 52 of 2024 (in effect Jan 2025) treats marketing an equitable interest
  in a property as brokerage that needs a license; contracts need specific disclosures and
  give the seller a cancellation right. Philadelphia also has its own wholesaler license.
- Illinois: since 2019 (Public Act 101-0357), wholesaling more than once in 12 months
  needs a real estate license.
- Virginia: repeatedly marketing contracts as a business can be treated as brokerage that
  needs a license. Check with the Virginia Real Estate Board or an attorney.
- Maryland: since Oct 1, 2025 you must tell the owner in writing that you may assign the
  contract, and tell the assignee you hold only an equitable interest; without the
  disclosure the seller can cancel any time before closing.
- Ohio: ORC 5301.95 requires a separate, conspicuous (bold, 12 pt) written disclosure
  before contracting on residential property you intend to assign; without it the seller
  can cancel.
- Oklahoma: the Predatory Real Estate Wholesaler Prohibition Act (plus SB 1075, Nov 2025)
  requires written disclosure of intent to assign, a notice to seek legal advice, a
  2-business-day cancellation right, and a license to publicly market an equitable interest.
- Texas: SB 1577 (2023) requires telling buyers in writing that you hold only an equitable
  interest when you market a contract; TREC rules apply.
Other states are adding rules every year. Search "[your state] real estate wholesaling law".

Optional assignment disclosure (have your attorney adapt it to your state's required wording):
"Buyer may assign this contract to another buyer before closing. Until closing, Buyer holds only
an equitable interest in the property, not ownership."

## Data licensing (what you may do with the data)
- {data_license}
- PropStream and other list providers: licensed for your own business use under their terms.
  Do not resell, share or publish the exports.
- Skip-trace results: use them only as your provider's terms allow. They are not consumer reports:
  never use them for credit, employment, insurance or tenant decisions (FCRA).
- County parcel layers: each county sets its own terms. The kit saves the layer's licence / use
  text to sources/county_layer_license.txt when it pulls a layer. Read it before you share data.
- USDA NAIP imagery: public domain (credit "USDA NAIP imagery via USGS").
- OpenStreetMap: ODbL. Credit "(c) OpenStreetMap contributors"; a database you publish from it
  must stay under ODbL.
- US Census TIGER and re-hosted HIFLD snapshot layers (used when OpenStreetMap is down): public data; credit the source.
- Esri and Google imagery: view links only; their terms don't allow saving it.
- Do not upload these lists anywhere public.

## Personal data (owner names, addresses, phones, emails)
- Everything stays on your computer in this folder. The kit sends nothing anywhere except the
  public map / county lookups (no owner data is sent in those) and, only if you run it with
  --confirm, the owners you choose to your own BatchData account.
- Never paste API keys into the chat. Set them as environment variables (see SETUP.md).
- Do not upload these files to services that are not part of your campaign (no public drives,
  AI chats, file-sharing links or forums). Upload only to your own skip-trace provider, mail
  house, dialer or CRM, under their terms.
- Protect the folder (your computer's login password and disk encryption: FileVault / BitLocker).
- Delete old exports you no longer need: `PY scripts/cleanup_exports.py` lists output files older
  than 90 days and deletes them only with --delete. It never deletes the suppression list, the
  consent log or the call-review file.
- Keep the suppression list, consent proof and call records at least 5 years.
"""



STATE_TZ = {
    "CT": "Eastern", "DE": "Eastern", "DC": "Eastern", "GA": "Eastern", "ME": "Eastern", "MD": "Eastern", "MA": "Eastern",
    "NH": "Eastern", "NJ": "Eastern", "NY": "Eastern", "NC": "Eastern", "OH": "Eastern", "PA": "Eastern", "RI": "Eastern",
    "SC": "Eastern", "VT": "Eastern", "VA": "Eastern", "WV": "Eastern",
    "AL": "Central", "AR": "Central", "IL": "Central", "IA": "Central", "LA": "Central", "MN": "Central", "MS": "Central",
    "MO": "Central", "OK": "Central", "WI": "Central",
    "AZ": "Mountain (Arizona: no daylight saving)", "CO": "Mountain", "MT": "Mountain", "NM": "Mountain", "UT": "Mountain", "WY": "Mountain",
    "CA": "Pacific", "NV": "Pacific", "WA": "Pacific", "AK": "Alaska", "HI": "Hawaii",
    "FL": "Eastern or Central (FL panhandle)", "IN": "Eastern or Central (IN)", "KY": "Eastern or Central (KY)",
    "MI": "Eastern or Central (MI)", "TN": "Eastern or Central (TN)", "TX": "Central or Mountain (TX)",
    "KS": "Central or Mountain (KS)", "NE": "Central or Mountain (NE)", "ND": "Central or Mountain (ND)",
    "SD": "Central or Mountain (SD)", "ID": "Mountain or Pacific (ID)", "OR": "Pacific or Mountain (OR)",
}
CALL_HOURS = ("Federal rule: 8am-9pm in the called person's local time. Some states are stricter (for example FL, OK and MD "
              "allow 8am-8pm) and some limit Sundays and holidays. time_zone is an estimate from the mailing ZIP / state; a cell number can be anywhere.")
LAST_VERIFIED = "2026-11-19"
CALL_ELIGIBILITY = ("needs_review", "blocked", "reviewed_for_campaign")
SCRUB_MAX_DAYS = 31


def load_phones(path, need=()):
    """phone -> row, for a consent or DNC-scrub file."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    for r in read_rows(path):
        low = {str(k).strip().lower(): v for k, v in r.items()}
        ph = clean_phone(low.get("phone") or low.get("phone_number") or low.get("number"))
        if ph and all(str(low.get(n) or "").strip() for n in need):
            out[ph] = low
    return out


CONSENT_LOG_FIELDS = ["phone", "consented_to", "purpose", "method", "consent_date", "consent_source", "consent_evidence",
                      "confirmed", "revoked_date", "revoked_how", "kit_decision", "checked_on"]


def load_consent(path, sender, log=None, revoked=None):
    """Only rows that confirm consent for THIS sender, a stated purpose and method, with proof (consent_evidence),
    marked confirmed = Y and not revoked. Revoked numbers are collected in `revoked` (they go to the suppression list)."""
    ok, rejected = {}, []
    for ph, low in load_phones(path).items():
        missing = [c for c in ("consent_date", "consent_source", "consented_to", "purpose", "method", "consent_evidence")
                   if not str(low.get(c) or "").strip()]
        to = norm(low.get("consented_to"))
        rv = str(low.get("revoked_date") or low.get("revoked") or "").strip()
        if rv and rv.upper() not in ("N", "NO"):
            rejected.append(f"{ph}: consent revoked ({rv}); added to your suppression list")
            if revoked is not None:
                revoked.append({"phone": ph, "address": "", "owner": "", "date": rv if parse_date(rv) else dt.date.today().isoformat(),
                                "channel": "all", "reason": "consent revoked " + str(low.get("revoked_how") or "").strip()})
        elif missing:
            rejected.append(f"{ph}: missing {', '.join(missing)}")
        elif not sender or not (to and (to in norm(sender) or norm(sender) in to)):
            rejected.append(f"{ph}: consent was given to '{low.get('consented_to')}', not to the sender '{sender or '(no --sms-sender)'}'")
        elif str(low.get("confirmed") or "").strip().upper()[:1] != "Y":
            rejected.append(f"{ph}: confirmed is not Y (you confirm the consent covers this sender, this purpose and this method)")
        else:
            ok[ph] = low
        if log is not None:
            log.append({**{k: str(low.get(k) or "").strip() for k in CONSENT_LOG_FIELDS}, "phone": ph,
                        "kit_decision": "used for sms.csv" if ph in ok else ("revoked: suppressed" if rv and rv.upper() not in ("N", "NO") else "rejected: " + (rejected[-1].split(": ", 1)[1] if rejected else "")),
                        "checked_on": dt.date.today().isoformat()})
    return ok, rejected


def scrub_missing(lists_checked):
    """Which of federal / state / internal a lists_checked value does not cover."""
    t = str(lists_checked or "").lower()
    have = {"federal": bool(re.search(r"federal|national|ftc", t)), "state": "state" in t, "internal": bool(re.search(r"internal|company|own", t))}
    return [k for k in SCRUB_PARTS if not have[k]]


def load_scrub(path, default_date, as_of, default_lists="", default_by="", default_vendor=""):
    """phone -> (dnc Y/N, scrub date or None, fresh?, missing parts of a complete scrub, (lists, scrubbed_by, vendor))
    A complete scrub covers federal + state + internal AND records who scrubbed it (scrubbed_by) and with what (vendor)."""
    out = {}
    for ph, low in load_phones(path).items():
        d = parse_date(low.get("scrub_date") or low.get("scrubbed_on") or low.get("date")) or default_date
        fresh = bool(d and 0 <= (as_of - d).days <= SCRUB_MAX_DAYS)
        lists = str(low.get("lists_checked") or default_lists or "").strip()
        by = str(low.get("scrubbed_by") or default_by or "").strip()
        vendor = str(low.get("vendor") or default_vendor or "").strip()
        missing = scrub_missing(lists) + (["scrubbed_by"] if not by else []) + (["vendor"] if not vendor else [])
        out[ph] = (str(low.get("dnc") or "").strip().upper()[:1], d, fresh, missing, (lists, by, vendor))
    return out


def load_review(path):
    """phone or owner_key -> call_eligibility set by you (blocked / reviewed_for_campaign)."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    for r in read_rows(path):
        low = {str(k).strip().lower(): str(v or "").strip() for k, v in r.items() if k}
        v = low.get("call_eligibility", "").lower()
        if v not in CALL_ELIGIBILITY:
            continue
        key = clean_phone(low.get("phone")) or low.get("owner_key", "")
        if key:
            out[key] = (v, low.get("reviewed_by", ""), low.get("review_date", ""), low.get("hours_verified", "").upper()[:1] == "Y")
    return out


def split_multi(v):
    return [x.strip() for x in str(v or "").split(";") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ranked", required=True)
    ap.add_argument("--traced")
    ap.add_argument("--satellite")
    ap.add_argument("--tiers", default="A,B")
    ap.add_argument("--output-dir")
    ap.add_argument("--state-file", help="JSON file remembering owners already exported (for weekly re-runs)")
    ap.add_argument("--suppress", action="append", default=[], help="suppression CSV: phone, address, owner, date, channel (repeatable)")
    ap.add_argument("--stop-replies", help="CSV of numbers that replied STOP (phone, date): added to the suppression list for every channel")
    ap.add_argument("--suppression-master", help="master suppression list kept across runs (default: <state-file folder>/suppression.csv)")
    ap.add_argument("--sms", action="store_true", help="build sms.csv (needs --consent-file and --sms-sender)")
    ap.add_argument("--sms-sender", default="", help="the business sending the texts; consent must name it (consented_to column)")
    ap.add_argument("--consent-file", help="CSV: phone, consent_date, consent_source, consented_to, purpose, method, confirmed (Y)")
    ap.add_argument("--dnc-scrubbed", help="CSV from YOUR National + state DNC scrub: phone, dnc (Y = on a list, N = clean), scrub_date")
    ap.add_argument("--dnc-scrub-date", help="YYYY-MM-DD of your scrub, for rows of --dnc-scrubbed that have no scrub_date")
    ap.add_argument("--dnc-lists", default="", help='lists your scrub covered, for rows without lists_checked, e.g. "federal; state; internal"')
    ap.add_argument("--dnc-scrubbed-by", default="", help="who ran the scrub, for rows without scrubbed_by")
    ap.add_argument("--dnc-vendor", default="", help='DNC service used, for rows without vendor (e.g. "self (own SAN)")')
    ap.add_argument("--hold-phone-sms", default="", help="reason to hold every phone and text output (run_pipeline sets it while the "
                                                         "suppression list may be out of date)")
    ap.add_argument("--call-review", help="CSV you keep: phone or owner_key, call_eligibility (blocked / reviewed_for_campaign), reviewed_by, review_date")
    ap.add_argument("--as-of", help="YYYY-MM-DD to measure the 31-day scrub window from (default today)")
    ap.add_argument("--jurisdiction", default="", help='market this run is for, e.g. "Wake County, NC" (printed in COMPLIANCE.md)')
    a = ap.parse_args(argv)
    out = a.output_dir or os.path.join(os.path.dirname(a.ranked) or ".", "marketing")
    os.makedirs(out, exist_ok=True)
    as_of = parse_date(a.as_of) if a.as_of else dt.date.today()

    want = [t.strip().upper() for t in a.tiers.split(",") if t.strip()]
    rows = [r for r in read_rows(a.ranked) if str(r.get("rank") or "").strip() and str(r.get("tier") or "")[:1].upper() in want]
    rows.sort(key=lambda r: num(r["rank"]) or 1e9)

    verdict = {}
    if a.satellite and os.path.exists(a.satellite):
        for s in read_rows(a.satellite):
            v = str(s.get("verdict") or "").strip().lower()
            if v:
                verdict[str(s.get("apn") or "").strip()] = (v, str(s.get("notes") or "").strip())
    traced = {}
    if a.traced and os.path.exists(a.traced):
        for t in read_rows(a.traced):
            traced[t["owner_key"]] = t

    master = a.suppression_master or (os.path.join(os.path.dirname(a.state_file) or ".", "suppression.csv") if a.state_file else None)
    sup = suppression.Suppression(suppression.merge(master, a.suppress, a.stop_replies, persist=bool(master)))
    consent_log, revoked = [], []
    consent, consent_rejected = load_consent(a.consent_file, a.sms_sender, consent_log, revoked) if a.consent_file else ({}, [])
    if revoked:  # a revoked consent is a do-not-contact request: keep it
        rows_ = suppression.merge(master, a.suppress, a.stop_replies, persist=False) + revoked
        if master:
            suppression.write_rows(master, rows_, suppression.FIELDS)
        sup = suppression.Suppression(rows_)
    scrub = load_scrub(a.dnc_scrubbed, parse_date(a.dnc_scrub_date) if a.dnc_scrub_date else None, as_of, a.dnc_lists,
                       a.dnc_scrubbed_by, a.dnc_vendor)
    hold = (a.hold_phone_sms or "").strip()
    review = load_review(a.call_review)
    owners, dropped = {}, []
    for r in rows:
        v = verdict.get(str(r.get("apn") or "").strip())
        if v and v[0].startswith("drop"):
            dropped.append(f"{r.get('apn')}: {v[1] or 'dropped in satellite review'}")
            continue
        k = owner_key(r.get("owner"), r.get("mail_street") or r.get("mail_address"), r.get("mail_zip"))
        o = owners.get(k)
        if o is None:
            sp = split_owner(r.get("owner"))
            o = owners[k] = {
                "owner_key": k, "owner": (r.get("owner") or "").strip(), "first_name": sp["first"], "last_name": sp["last"],
                "is_company": "Y" if sp["entity"] else "", "mail_street": r.get("mail_street", ""), "mail_city": r.get("mail_city", ""),
                "mail_state": r.get("mail_state", ""), "mail_zip": r.get("mail_zip", ""), "best_rank": int(num(r["rank"])),
                "tier": r.get("tier", ""), "priority": r.get("priority", ""), "parcels": 0, "total_acres": 0.0, "apns": [],
                "property_addresses": [], "county": r.get("county", ""), "state": r.get("state", ""), "zoning": [],
                "motivation_signals": set(), "split_adu_signals": set(), "yield_gross": 0, "yield_net": 0, "why": r.get("why", ""),
                "satellite": [], "ev_low": 0, "ev_high": 0, "map_link": r.get("map_link", ""), "research_next": r.get("research_next", "")}
        o["parcels"] += 1
        o["total_acres"] += num(r.get("acres")) or 0
        o["apns"].append(r.get("apn", ""))
        if r.get("address"):
            o["property_addresses"].append(r["address"])
        if r.get("zoning_use"):
            o["zoning"].append(r["zoning_use"])
        o["motivation_signals"].update(split_multi(r.get("motivation_signals")))
        o["split_adu_signals"].update(split_multi(r.get("split_adu_signals")))
        o["yield_gross"] += int(num(r.get("est_lot_yield_gross")) or 0)
        o["yield_net"] += int(num(r.get("est_lot_yield_net")) or 0)
        o["ev_low"] += num(r.get("ev_low")) or 0
        o["ev_high"] += num(r.get("ev_high")) or 0
        if v:
            o["satellite"].append(f"{r.get('apn')}: {v[0]}" + (f" ({v[1]})" if v[1] else ""))

    seen, today = {}, as_of.isoformat()
    if a.state_file and os.path.exists(a.state_file):
        seen = json.load(open(a.state_file))
    recs, suppressed_log, needs_scrub = [], [], []
    for o in sorted(owners.values(), key=lambda o: o["best_rank"]):
        t = traced.get(o["owner_key"], {})
        lit = str(t.get("litigator") or "").upper() == "Y"
        addrs = [" ".join(x for x in (o["mail_street"], o["mail_city"], o["mail_state"], o["mail_zip"]) if x), o["mail_street"]] + o["property_addresses"]
        sup_all = sup.owner(o["owner"], addrs, "all")
        if sup_all:
            suppressed_log.append({"owner": o["owner"], "apns": "; ".join(o["apns"]), "removed_from": "every list (incl. CRM import file)", "reason": sup_all})
            continue
        sup_mail = sup.owner(o["owner"], addrs, "mail")
        sup_call = sup.owner(o["owner"], addrs, "call")
        sup_sms = sup.owner(o["owner"], addrs, "sms")
        ready, ready_meta, ready_types, unscrubbed, unscrubbed_meta, unscrubbed_types, texts, ready_by = [], [], [], [], [], [], [], []
        for i in range(1, 6):
            p = clean_phone(t.get(f"phone{i}"))
            if not p or lit:
                continue
            prov = str(t.get(f"phone{i}_dnc") or "").strip().upper()
            mine, sdate, fresh, parts_missing, scrub_meta = scrub.get(p, ("", None, False, list(SCRUB_PARTS), ("", "", "")))
            if prov == "Y" or mine == "Y":
                continue
            if p in consent and not sup.phone(p, "sms") and not sup_sms:
                texts.append(p)
            if sup.phone(p, "call") or sup_call:
                suppressed_log.append({"owner": o["owner"], "apns": "; ".join(o["apns"]), "removed_from": f"call list ({p})",
                                       "reason": sup_call or "number on your suppression list"})
                continue
            if mine == "N" and fresh and not parts_missing:
                ready.append(p); ready_meta.append(sdate.isoformat()); ready_types.append(str(t.get(f"phone{i}_type") or "unknown"))
                ready_by.append(scrub_meta)
            else:
                lst = [x for x in parts_missing if x in SCRUB_PARTS]
                who = [x for x in parts_missing if x not in SCRUB_PARTS]
                why = ("incomplete scrub: " + "; ".join(([", ".join(lst) + " list not checked (lists_checked)"] if lst else []) +
                                                       ([" and ".join(who) + " not recorded"] if who else [])) if (mine == "N" and fresh and parts_missing) else
                       "your scrub is older than 31 days (" + sdate.isoformat() + ")" if (mine == "N" and sdate) else
                       "in your scrub file but no scrub date (add scrub_date or --dnc-scrub-date)" if mine == "N" else
                       "provider flag only - still scrub National + state DNC" if prov == "N" else "unknown - scrub first")
                unscrubbed.append(p); unscrubbed_meta.append(why); unscrubbed_types.append(str(t.get(f"phone{i}_type") or "unknown"))
        tstatus = "not traced" if not t else (t.get("trace_status") or ("hit" if (t.get("phone1") or t.get("email1")) else "no hit"))
        rec = {k: o[k] for k in ("owner_key", "owner", "first_name", "last_name", "is_company", "mail_street", "mail_city",
                                 "mail_state", "mail_zip", "best_rank", "tier", "priority", "parcels", "county", "state", "why", "map_link",
                                 "research_next")}
        rv = review.get(ready[0]) if ready else None
        rv = rv or review.get(o["owner_key"])
        elig = rv[0] if rv else "needs_review"
        tz_state = (o["mail_state"] or o["state"] or "").strip().upper()
        tz_zone, tz_basis = timezones.estimate(tz_state, o["mail_zip"] if o["mail_state"] else "")
        cw, cw_basis, cw_check = timezones.call_window(tz_state, tz_zone, ready or unscrubbed)
        if elig == "reviewed_for_campaign" and cw_check.startswith("VERIFY") and not (rv and rv[3]):
            elig = "needs_review"  # uncertain location: the user must verify calling hours (hours_verified = Y)
            cw_check += " (reviewed_for_campaign not applied: add hours_verified = Y to your call review)"
        rec.update({
            "first_name": t.get("first_name") or o["first_name"], "last_name": t.get("last_name") or o["last_name"],
            "total_acres": round(o["total_acres"], 2), "apns": "; ".join(o["apns"]),
            "property_address": "; ".join(o["property_addresses"]) or ("APN " + "; ".join(o["apns"])),
            "zoning": "; ".join(dict.fromkeys(o["zoning"])), "motivation_signals": "; ".join(sorted(o["motivation_signals"])),
            "split_adu_signals": "; ".join(sorted(o["split_adu_signals"])),
            "est_lot_yield_gross": o["yield_gross"] or "", "est_lot_yield_net": o["yield_net"] or "",
            "value_range": (f"${o['ev_low']:,.0f}-${o['ev_high']:,.0f}" if o["ev_high"] else ""),
            "satellite_review": "; ".join(o["satellite"]),
            "phone1": ready[0] if len(ready) > 0 else "", "phone2": ready[1] if len(ready) > 1 else "",
            "phone3": ready[2] if len(ready) > 2 else "",
            "dnc_status": ("clean (your scrub " + ready_meta[0] + ")") if ready else (unscrubbed_meta[0] if unscrubbed else ""),
            "dnc_scrub_date": ready_meta[0] if ready else "",
            "unscrubbed_phones": "; ".join(unscrubbed), "unscrubbed_reason": unscrubbed_meta[0] if unscrubbed else "",
            "call_eligibility": elig if ready else ("blocked" if unscrubbed else ""),
            "call_review_by": (rv[1] + " " + rv[2]).strip() if (rv and ready) else "",
            "line_type": "; ".join(ready_types), "time_zone": tz_zone, "time_zone_basis": tz_basis,
            "calling_hours_note": CALL_HOURS, "call_rules": VOICE_LINE, "call_window": cw, "call_window_basis": cw_basis,
            "call_window_check": cw_check, "dialing": MANUALLY_DIALED,
            "phone_status": (HOLD_STATUS if hold else ("scrubbed " + ready_meta[0] + " (" + "; ".join(x for x in ready_by[0] if x) +
                                                       "), still needs your review before dialing") if ready else (NOT_SCRUBBED if unscrubbed else
                                                       ("no phone (not traced yet)" if not t else "no phone found"))),
            "sms_phone": texts[0] if texts else "",
            "sms_consent": ("Y: " + " / ".join(str(consent[texts[0]].get(c) or "") for c in ("consent_date", "consented_to", "purpose", "method", "consent_source"))) if texts else "",
            "sms_review_status": (str(consent[texts[0]].get("review_status") or "").strip().lower() if texts and str(consent[texts[0]].get("review_status") or "").strip().lower() in ("reviewed_for_campaign", "blocked") else "needs_review") if texts else "",
            "email1": t.get("email1", ""), "litigator_removed": "Y" if lit else "", "trace_status": tstatus,
            "mail_ok": "" if sup_mail else "Y", "suppressed": "; ".join(x for x in (("mail: " + sup_mail) if sup_mail else "", ("call: " + sup_call) if sup_call else "", ("sms: " + sup_sms) if sup_sms else "") if x),
            "is_new": "Y" if o["owner_key"] not in seen else "", "first_seen": seen.get(o["owner_key"], today),
            "tags": "dev-land; tier-" + str(o["tier"])[:1] + ("; company" if o["is_company"] else "") + ("; new" if o["owner_key"] not in seen else ""),
        })
        if sup_mail:
            suppressed_log.append({"owner": o["owner"], "apns": rec["apns"], "removed_from": "mail list", "reason": sup_mail})
        if hold:  # suppression list may be out of date: no phone or text leaves the kit
            rec.update(phone1="", phone2="", phone3="", line_type="", sms_phone="", sms_consent="", sms_review_status="",
                       call_eligibility="", dnc_status="held", dnc_scrub_date="")
        elif unscrubbed:
            needs_scrub.append(dict(rec, phone1=unscrubbed[0], phone2=unscrubbed[1] if len(unscrubbed) > 1 else "",
                                    phone3=unscrubbed[2] if len(unscrubbed) > 2 else "", dnc_status=unscrubbed_meta[0],
                                    line_type="; ".join(unscrubbed_types), call_eligibility="blocked", call_review_by=""))
        recs.append(rec)

    base = ["owner", "first_name", "last_name", "is_company", "mail_street", "mail_city", "mail_state", "mail_zip"]
    prop = ["property_address", "apns", "county", "state", "total_acres", "parcels", "zoning"]
    mail = [r for r in recs if r["mail_street"] and r["mail_zip"] and r["mail_ok"]]
    call = [r for r in recs if r["phone1"]]
    sms = [r for r in recs if r["sms_phone"]] if (a.sms and consent and not hold) else []
    call_cols = ["owner", "first_name", "last_name", "phone1", "phone2", "phone3", "line_type", "dnc_status", "dnc_scrub_date", "call_eligibility",
                 "call_review_by", "time_zone", "time_zone_basis", "call_window", "call_window_check", "call_window_basis", "calling_hours_note",
                 "call_rules", "dialing"] + prop + ["best_rank", "tier", "motivation_signals", "split_adu_signals",
                                                                               "why", "research_next", "is_new", "owner_key"]
    write_rows(os.path.join(out, "mail.csv"), mail, base + prop + ["best_rank", "tier", "is_new"])
    held_note = os.path.join(out, "PHONE_AND_SMS_HELD.txt")
    if hold:
        for fn in ("cold_call.csv", "cold_call_NEEDS_SCRUB.csv", "sms.csv"):
            if os.path.exists(os.path.join(out, fn)):
                os.remove(os.path.join(out, fn))  # never leave an old phone or text list behind
        with open(held_note, "w") as f:
            f.write("PHONE AND TEXT OUTPUTS ARE HELD.\n\nReason: " + hold + "\n\n" + OPT_OUT_SENTENCE + "\n" + MANUAL_SENTENCE +
                    "\nSave them in the suppress/ folder and re-run. Until then this kit writes no cold_call.csv, no "
                    "cold_call_NEEDS_SCRUB.csv and no sms.csv, and the phone columns in crm_import.csv are blank.\n")
    else:
        if os.path.exists(held_note):
            os.remove(held_note)
        write_rows(os.path.join(out, "cold_call.csv"), call, call_cols)
        write_rows(os.path.join(out, "cold_call_NEEDS_SCRUB.csv"), needs_scrub, call_cols)
    sms_path = os.path.join(out, "sms.csv")
    if a.sms and consent and not hold:
        write_rows(sms_path, sms, ["first_name", "last_name", "owner", "sms_phone", "sms_consent", "sms_review_status", "time_zone",
                                   "property_address", "county", "state", "total_acres", "best_rank", "tier", "is_new"])
    elif os.path.exists(sms_path):
        os.remove(sms_path)  # never leave an old text list behind
    crm_fields = base + prop + ["phone1", "phone2", "phone3", "phone_status", "line_type", "dnc_status", "dnc_scrub_date", "call_eligibility",
                                "time_zone", "time_zone_basis", "call_window", "call_window_check", "sms_phone", "sms_consent", "sms_review_status", "email1", "litigator_removed", "suppressed",
                                "trace_status", "best_rank", "tier", "priority", "motivation_signals", "split_adu_signals",
                                "est_lot_yield_gross", "est_lot_yield_net", "value_range", "satellite_review", "why", "research_next",
                                "map_link", "tags", "is_new", "first_seen", "owner_key"]
    write_rows(os.path.join(out, "crm_import.csv"), recs, crm_fields)
    if a.consent_file:
        write_rows(os.path.join(out, "consent_log.csv"), consent_log, CONSENT_LOG_FIELDS)
    write_rows(os.path.join(out, "suppressed_this_run.csv"), suppressed_log, ["owner", "apns", "removed_from", "reason"])
    new = [r for r in recs if r["is_new"]]
    if a.state_file:
        for r in recs:
            seen.setdefault(r["owner_key"], r["first_seen"])
        os.makedirs(os.path.dirname(a.state_file) or ".", exist_ok=True)
        json.dump(seen, open(a.state_file, "w"), indent=1)
        write_rows(os.path.join(out, "new_owners.csv"), new, crm_fields)
    with open(os.path.join(out, "COMPLIANCE.md"), "w") as f:
        f.write(COMPLIANCE.replace("{prepared}", PREPARED_NOT_APPROVED).replace("{voice}", VOICE_LINE).replace("{rvm}", RVM_PARAGRAPH)
                .replace("{opt_out}", OPT_OUT_SENTENCE).replace("{manual}", MANUAL_SENTENCE).replace("{manually_dialed}", MANUALLY_DIALED)
                .replace("{estate_rule}", ESTATE_RULE).replace("{data_license}", DATA_LICENSE_LINE)
                .replace("{state_lists}", STATE_DNC_LISTS).replace("{jurisdiction}", a.jurisdiction or (rows[0].get("county", "") + ", " + rows[0].get("state", "") if rows else "") or "not set")
                .replace("{last_verified}", LAST_VERIFIED))
    summary = [PREPARED_NOT_APPROVED, VOICE_LINE] + (["PHONE AND TEXT OUTPUTS HELD: " + hold] if hold else []) + [
               f"Marketing lists ({today})", f"Tiers kept: {', '.join(want)}",
               f"Parcels: {len(rows)} -> owners: {len(recs)} (dropped in satellite review: {len(dropped)})",
               f"mail.csv: {len(mail)} | cold_call.csv (your DNC scrub within 31 days): {len(call)} | cold_call_NEEDS_SCRUB.csv: {len(needs_scrub)} | sms.csv: " +
               (str(len(sms)) if (a.sms and consent) else "not built (needs --sms, --sms-sender and a confirmed consent file)") +
               f" | crm_import.csv (CRM import file): {len(recs)}",
               f"Suppression list: {len(sup)} entries" + (f" (kept in {master})" if master else " (not saved: demo or no state folder)") +
               f"; removed this run: {len(suppressed_log)} (suppressed_this_run.csv)",
               f"Trace status: hit {sum(1 for r in recs if r['trace_status'] == 'hit')}, no hit {sum(1 for r in recs if r['trace_status'] == 'no hit')}, "
               f"not traced {sum(1 for r in recs if r['trace_status'] == 'not traced')} | litigators removed: {sum(1 for r in recs if r['litigator_removed'])}",
               "Every row in cold_call.csv starts as call_eligibility = needs_review. A clean DNC scrub is not permission to call: "
               "check calling hours, your own do-not-call list, state rules and that the number is the owner's, then mark it in --call-review.",
               f"Companies / trusts (research the person behind them): {sum(1 for r in recs if r['is_company'])}"]
    if a.state_file:
        summary.append(f"New since last run: {len(new)} (new_owners.csv)")
    if a.sms and not consent:
        summary.append("--sms was given but no consent row passed the check (phone, consent_date, consent_source, consented_to = the sender, "
                       "purpose, method, confirmed = Y), so no sms.csv.")
    if consent_rejected:
        summary.append(f"Consent rows not used ({len(consent_rejected)}): " + " | ".join(consent_rejected[:5]))
    if not traced:
        summary.append("No skip-trace results imported yet, so the call list is empty. Run skip_trace.py export, upload, then import.")
    summary += [""] + ["Dropped: " + d for d in dropped] + ["", "Read COMPLIANCE.md before you call or text. Nothing has been sent."]
    with open(os.path.join(out, "marketing_summary.txt"), "w") as f:
        f.write("\n".join(summary) + "\n")
    print("\n".join(summary[:8]))
    return {"mail": mail, "call": [] if hold else call, "needs_scrub": [] if hold else needs_scrub, "sms": sms, "crm": recs, "new": new,
            "dropped": dropped, "held": hold,
            "suppressed": suppressed_log, "suppression_size": len(sup), "consent_rejected": consent_rejected}


if __name__ == "__main__":
    main()
