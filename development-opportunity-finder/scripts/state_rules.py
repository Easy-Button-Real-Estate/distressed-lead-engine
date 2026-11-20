"""State wholesaling / assignment notes for the state check. Not legal advice; laws change every year.

Each entry: law (which statute or rule), license (when a license is needed), disclosures (assignment /
marketing disclosures), source (where the note comes from) and checked (when the kit author last read it).
NC, VA and MD were read at the source on the date shown. The other entries are citations carried from
earlier rounds; their text was not re-read on that date (checked says so).
"""

CHECKED = "2026-11-19"
CARRIED = "2026-11-19 (citation only; source text not re-read this round)"

STATE_NOTES = {
    "NC": {
        "law": "No wholesaling-specific statute found (a 2025 bill, H797, is reported as not enacted; confirm). "
               "Real estate brokerage law: N.C. Gen. Stat. sec. 93A-1 and 93A-2(a).",
        "license": "Not needed for a bona fide buyer to assign their own purchase contract. NCREC says these can be unlicensed "
                   "brokerage (a Class 1 misdemeanor): soliciting sellers with no intent to buy, misrepresenting your ownership "
                   "interest, handling others' deposits, negotiating between seller and buyer, marketing to buyers generally.",
        "disclosures": "No wholesaler-specific disclosure statute found. Never present yourself as the owner; say you hold a contract.",
        "source": "NCREC Bulletin, Dec 2023, 'Brokers & Consumers Should Beware of Unlicensed Activity in North Carolina' "
                  "(bulletins.ncrec.gov); N.C. Gen. Stat. sec. 93A-2(a)",
        "checked": CHECKED,
    },
    "VA": {
        "law": "Va. Code sec. 54.1-2100: a person who deals in real estate contracts, including assignable contracts, on two "
               "or more occasions in any 12-month period is a real estate broker.",
        "license": "Needed from the second contract you sell, assign or market in any 12-month period.",
        "disclosures": "No wholesaler-specific disclosure statute found; ordinary contract and disclosure rules apply.",
        "source": "Va. Code sec. 54.1-2100 (law.lis.virginia.gov/vacode/title54.1/chapter21/section54.1-2100/)",
        "checked": CHECKED,
    },
    "MD": {
        "law": "Md. Code, Real Prop. sec. 10-715 (HB 124 of 2025, ch. 508, in effect Oct 1, 2025). It covers owner-occupied "
               "residential property with 4 or fewer units; vacant land is likely outside it, but confirm.",
        "license": "Sec. 10-715 adds no license. Marketing contracts as a business may still be brokerage: check with the "
                   "Maryland Real Estate Commission or counsel.",
        "disclosures": "Before contracting, tell the owner in writing that you may assign the contract; before assigning, tell "
                       "the assignee in writing that you hold an equitable interest and may not be able to convey title. Without "
                       "these the owner (or the assignee) may rescind before closing.",
        "source": "Md. Code, Real Prop. sec. 10-715 (mgaleg.maryland.gov/2026RS/Statute_Web/grp/10-715.pdf)",
        "checked": CHECKED,
    },
    "PA": {"law": "Act 52 of 2024 (in effect Jan 2025).",
           "license": "Marketing an equitable interest is brokerage that needs a license. Philadelphia has its own wholesaler license.",
           "disclosures": "Specific contract disclosures and a seller cancellation right.",
           "source": "Pennsylvania Act 52 of 2024", "checked": CARRIED},
    "IL": {"law": "Public Act 101-0357 (2019).", "license": "Wholesaling more than once in 12 months needs a real estate license.",
           "disclosures": "None noted by the kit; check.", "source": "Illinois Public Act 101-0357", "checked": CARRIED},
    "OH": {"law": "ORC 5301.95.", "license": "None noted by the kit; check.",
           "disclosures": "Separate, conspicuous written disclosure before contracting on residential property you intend to assign.",
           "source": "Ohio Rev. Code sec. 5301.95", "checked": CARRIED},
    "OK": {"law": "Predatory Real Estate Wholesaler Prohibition Act (and SB 1075).", "license": "License to publicly market an equitable interest.",
           "disclosures": "Disclosure of intent to assign, notice to seek legal advice, 2-business-day cancellation right.",
           "source": "Oklahoma Predatory Real Estate Wholesaler Prohibition Act; SB 1075", "checked": CARRIED},
    "TX": {"law": "SB 1577 (2023); TREC rules.", "license": "TREC rules apply; check.",
           "disclosures": "Tell buyers in writing that you hold only an equitable interest when you market a contract.",
           "source": "Texas SB 1577 (2023)", "checked": CARRIED},
}

RECORD_FIELDS = ["state", "why_in_scope", "law_that_applies", "licensing_needed", "disclosures_apply",
                 "kit_note_law", "kit_note_license", "kit_note_disclosures", "kit_source", "kit_last_checked",
                 "verified_by", "verified_on", "counsel_or_source_used"]


def one_line(st):
    n = STATE_NOTES.get(st)
    if not n:
        return "No state-specific note in this kit. That does not mean there is no rule: check."
    return f"{n['law']} License: {n['license']} Disclosures: {n['disclosures']} [Source: {n['source']}; last checked {n['checked']}]"


def record_rows(states_why):
    """Blank state-check record rows (the user fills law_that_applies ... counsel_or_source_used)."""
    out = []
    for st, why in states_why:
        n = STATE_NOTES.get(st, {})
        out.append({"state": st, "why_in_scope": why, "law_that_applies": "", "licensing_needed": "", "disclosures_apply": "",
                    "kit_note_law": n.get("law", "no kit note: research this state"), "kit_note_license": n.get("license", ""),
                    "kit_note_disclosures": n.get("disclosures", ""), "kit_source": n.get("source", ""),
                    "kit_last_checked": n.get("checked", ""), "verified_by": "", "verified_on": "", "counsel_or_source_used": ""})
    return out
