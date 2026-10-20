"""Custom marketing per property + export for mail / email / SMS.

Invelo: no public API (helpdesk.inveloapp.com/can-i-use-an-api-for-calling-or-texting), so we write
output/invelo_import.csv using Invelo's Property import fields (Address, City, State, Zip + owner/contact
columns). In Invelo: More -> Import Data -> Properties, map columns, then start a Workflow that sends
mail / SMS (via smrtPhone) / email (via SMTP).
Others (REsimpli, Podio, Zapier, Make, n8n, GoHighLevel): set OUTREACH_WEBHOOK_URL and each NEW lead is
POSTed as JSON. Nothing is ever sent to a homeowner directly by this tool.
"""
import csv, os, requests

ANGLE = {
    "probate": "settling a loved one's estate", "pre_probate": "handling a family property after a loss",
    "pre_foreclosure": "getting ahead of the lender", "tax_foreclosure": "the county tax foreclosure",
    "tax_delinquent": "back property taxes", "code_violation": "the city repair notices",
    "vacant_building": "a vacant property that's costing you money", "eviction": "a tough tenant situation",
    "water_shutoff": "a property with utility issues", "lien": "liens on the property",
    "fire": "repairs after the fire",
}
SENSITIVE = {"probate", "pre_probate", "fire"}


def write_copy(r, cfg):
    me, co, phone = cfg.get("your_name", "[Your Name]"), cfg.get("company", "[Company]"), cfg.get("phone", "[Phone]")
    types = r["list_types"].split(";")
    angle = ANGLE.get(types[0], "your property")
    first = (r["owner_name"].split(",")[-1].strip().split(" ")[0].title() if r["owner_type"] == "individual" and r["owner_name"] else "there")
    addr = r["property_address"].title()
    soft = any(t in SENSITIVE for t in types)
    opener = ("I'm sorry to reach out at a hard time. " if soft else "")
    r["marketing_sms"] = (f"Hi {first}, this is {me} with {co}. {opener}Would you consider a cash offer on {addr}? "
                          f"As-is, no repairs, you pick the closing date. Reply STOP to opt out.")
    r["marketing_email_subject"] = f"Question about {addr}"
    r["marketing_email_body"] = (f"Hi {first},\n\n{opener}I buy houses locally and came across {addr} while looking into "
                                 f"properties dealing with {angle}. If selling would make life easier, I can make a fair "
                                 f"cash offer, buy as-is, and close on your timeline. No agents, no fees.\n\n"
                                 f"If it's not a fit, no worries at all.\n\n{me}\n{co}\n{phone}")
    r["marketing_letter"] = (f"Dear {first if first != 'there' else 'Property Owner'},\n\n{opener}My name is {me} and I'm a local "
                             f"buyer. I'm interested in {addr} and can buy it as-is for cash, even if it needs work or "
                             f"you're dealing with {angle}. You choose the closing date and we cover closing costs.\n\n"
                             f"Call or text me at {phone}.\n\nSincerely,\n{me}, {co}")
    return r


def export(rows, outdir, state, cfg):
    path = os.path.join(outdir, "invelo_import.csv")
    cols = ["Address", "City", "State", "Zip", "Owner Name", "Owner Type", "Phone 1", "Email 1",
            "Lead Source", "Lists", "Score", "Parcel ID", "Event Date", "SMS Script", "Letter"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r["property_address"].title(), r["city"].title(), state, r["zip"], r["owner_name"], r["owner_type"],
                        (r["phones"].split(";")[0] if r["phones"] else ""), (r["emails"].split(";")[0] if r["emails"] else ""),
                        "Distressed Lead Engine", r["list_types"], r["score"], r["parcel_id"], r["event_date"],
                        r["marketing_sms"], r["marketing_letter"]])
    msg = f"wrote {path}"
    hook = os.getenv("OUTREACH_WEBHOOK_URL")
    if hook:
        sent = 0
        for r in rows:
            if r["is_new"]:
                try:
                    requests.post(hook, json=r, timeout=30).raise_for_status(); sent += 1
                except requests.RequestException:
                    pass
        msg += f"; posted {sent} new leads to webhook"
    return msg
