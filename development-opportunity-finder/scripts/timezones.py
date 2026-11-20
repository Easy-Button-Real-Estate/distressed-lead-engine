"""Estimated time zone for calling hours, from the mailing ZIP (first 3 digits) and state.

This is an ESTIMATE. A mailing address is not where a phone is: a cell number can be anywhere.
States split between two zones are resolved by ZIP3 where one zone clearly dominates that ZIP3;
ZIP3s that straddle the line are returned as "X or Y (check)". When in doubt, call inside the
hours that are legal in BOTH zones (for example 9am-8pm Eastern = 8am-7pm Central).
"""
import re

STATE_TZ = {
    "CT": "Eastern", "DE": "Eastern", "DC": "Eastern", "GA": "Eastern", "ME": "Eastern", "MD": "Eastern", "MA": "Eastern",
    "NH": "Eastern", "NJ": "Eastern", "NY": "Eastern", "NC": "Eastern", "OH": "Eastern", "PA": "Eastern", "RI": "Eastern",
    "SC": "Eastern", "VT": "Eastern", "VA": "Eastern", "WV": "Eastern",
    "AL": "Central", "AR": "Central", "IL": "Central", "IA": "Central", "LA": "Central", "MN": "Central", "MS": "Central",
    "MO": "Central", "OK": "Central", "WI": "Central",
    "AZ": "Mountain (no daylight saving)", "CO": "Mountain", "MT": "Mountain", "NM": "Mountain", "UT": "Mountain", "WY": "Mountain",
    "CA": "Pacific", "NV": "Pacific", "WA": "Pacific", "AK": "Alaska", "HI": "Hawaii", "PR": "Atlantic", "VI": "Atlantic", "GU": "Chamorro",
}

# Split states: (ZIP3 ranges -> zone). Anything not listed falls back to the state's main zone.
SPLIT = {
    "FL": ("Eastern", {("324", "325"): "Central"}),                       # panhandle west of the Apalachicola
    "IN": ("Eastern", {("463", "464"): "Central", ("476", "477"): "Central"}),  # Gary area, Evansville area
    "KY": ("Eastern", {("420", "424"): "Central", ("427", "427"): "Central"}),  # western KY
    "TN": ("Central", {("373", "379"): "Eastern"}),                       # Chattanooga / Knoxville / Tri-Cities
    "MI": ("Eastern", {("498", "499"): "Eastern or Central (check)"}),     # western Upper Peninsula
    "TX": ("Central", {("798", "799"): "Mountain", ("885", "885"): "Mountain"}),  # El Paso area
    "KS": ("Central", {("677", "677"): "Central or Mountain (check)"}),
    "NE": ("Central", {("693", "693"): "Mountain", ("690", "692"): "Central or Mountain (check)"}),
    "ND": ("Central", {("586", "586"): "Mountain", ("588", "588"): "Central or Mountain (check)"}),
    "SD": ("Central", {("577", "577"): "Mountain", ("575", "575"): "Central or Mountain (check)"}),
    "ID": ("Mountain", {("835", "835"): "Pacific", ("838", "838"): "Pacific"}),
    "OR": ("Pacific", {("979", "979"): "Mountain"}),
}


def estimate(state, zip_code=""):
    """(zone, basis). basis says how it was estimated."""
    st = str(state or "").strip().upper()
    z = re.sub(r"\D", "", str(zip_code or ""))[:5]
    if st in SPLIT:
        main, ranges = SPLIT[st]
        if len(z) >= 3:
            z3 = z[:3]
            for (lo, hi), zone in ranges.items():
                if lo <= z3 <= hi:
                    return zone, f"estimate from mailing ZIP {z} ({st} has two time zones)"
            return main, f"estimate from mailing ZIP {z} ({st} has two time zones)"
        return f"{main} or other zone (check)", f"{st} has two time zones and there is no mailing ZIP"
    if st in STATE_TZ:
        return STATE_TZ[st], f"estimate from mailing state {st}"
    return "unknown - check the area code", "no mailing state"


# ---- calling window: ZIP estimate + area code, stricter of the two -------------------------------------------
import area_codes  # noqa: E402

# hours relative to Eastern as (winter, summer): Hawaii, Arizona and Atlantic (PR / USVI) keep no daylight saving
OFFSETS = {"Eastern": (0, 0), "Central": (-1, -1), "Mountain": (-2, -2), "Pacific": (-3, -3), "Alaska": (-4, -4),
           "Hawaii": (-5, -6), "Arizona": (-2, -3), "Atlantic": (1, 0)}
FED_START, FED_END = 8, 21  # federal: 8am-9pm in the called person's local time (47 C.F.R. 64.1200(c)(1); 16 C.F.R. 310.4(c))
FED_SOURCE = "47 C.F.R. sec. 64.1200(c)(1) and 16 C.F.R. sec. 310.4(c): 8am-9pm called party's local time"
HOURS_CHECKED = "2026-11-19"
# State calling-hour rules this kit has coded, each with its source and the date it was last checked.
# start / end are local hours (end = calls must end by). sunday: None = no Sunday calls, (a, b) = Sunday window,
# "same" = no separate Sunday rule. holidays: True = no calls on the state's legal holidays.
# Only these states can get an "ok" call_window_check; every other state gets the federal window and VERIFY.
# Rules change: re-check each source before relying on it. Not legal advice.
STATE_HOURS = {
    "TX": {"start": 9, "end": 21, "sunday": (12, 21), "holidays": False, "checked": HOURS_CHECKED,
           "source": "Tex. Bus. & Com. Code sec. 301.051(b)(2) (statutes.capitol.texas.gov/Docs/BC/htm/BC.301.htm)",
           "note": "weekday / Saturday 9am-9pm, Sunday noon-9pm; covers 'consumer telephone calls' by a telephone solicitor"},
    "LA": {"start": 8, "end": 20, "sunday": None, "holidays": True, "checked": HOURS_CHECKED,
           "source": "LPSC Do Not Call General Order, Sec. V(A)(2) (lpsc.louisiana.gov/docs/DNC/DNCGeneralOrder.pdf); La. R.S. 45:811",
           "note": "8am-8pm Monday-Saturday; no calls on Sunday or Louisiana legal holidays; none during a declared state of emergency"},
    "MS": {"start": 8, "start_summer": 9, "end": 20, "sunday": None, "holidays": False, "checked": HOURS_CHECKED,
           "source": "Miss. Code Ann. sec. 77-3-723(1) (law.justia.com/codes/mississippi/title-77/chapter-3/article-15/section-77-3-723/)",
           "note": "8am-8pm 'Central Standard Time' (read conservatively: 9am-8pm local while daylight time is on); no calls on Sunday"},
    "AL": {"start": 8, "end": 20, "sunday": None, "holidays": True, "checked": HOURS_CHECKED,
           "source": "Ala. Admin. Code r. 770-X-5-.17(2)(b) (admincode.legislature.state.al.us/administrative-code/770-X-5-.17)",
           "note": "PSC rule for live solicitation calls: 8am-8pm; no calls on Sundays or holidays (state holidays: Ala. Code sec. 1-3-8)"},
    "NC": {"start": 8, "end": 21, "sunday": "same", "holidays": False, "checked": HOURS_CHECKED,
           "source": "N.C. Gen. Stat. sec. 75-102(f) (ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_75/GS_75-102.html)",
           "note": "no telephone solicitation before 8am or after 9pm"},
    "VA": {"start": 8, "end": 21, "sunday": "same", "holidays": False, "checked": HOURS_CHECKED,
           "source": "Va. Code sec. 59.1-511 (law.lis.virginia.gov/vacode/title59.1/chapter44/section59.1-511/)",
           "note": "8am-9pm local time at the contacted person's location unless they gave prior consent"},
    "MD": {"start": 8, "end": 20, "sunday": "same", "holidays": False, "checked": HOURS_CHECKED,
           "source": "Md. Code, Com. Law sec. 14-4502(c) (mgaleg.maryland.gov, Stop the Spam Calls Act of 2023)",
           "note": "no calls 8pm-8am in the called party's time zone; no more than 3 calls in 24 hours on the same subject"},
    "FL": {"start": 8, "end": 20, "sunday": "same", "holidays": False, "checked": HOURS_CHECKED,
           "source": "Fla. Stat. sec. 501.616(6) (leg.state.fl.us)",
           "note": "8am-8pm in the called person's time zone; no more than 3 calls in 24 hours on the same subject"},
    "OK": {"start": 8, "end": 20, "sunday": "same", "holidays": False, "checked": HOURS_CHECKED,
           "source": "Okla. Stat. tit. 15, sec. 775C.4 (law.justia.com/codes/oklahoma/title-15/section-15-775c-4/)",
           "note": "8am-8pm in the called person's time zone; no more than 3 calls in 24 hours on the same subject"},
}
STATE_END = {k: v["end"] for k, v in STATE_HOURS.items() if v["end"] < FED_END}  # kept for older callers
ESTIMATED = "estimated window: "
LOCATION_NOT_ESTABLISHED = ("current location not established (a mailing address and an area code are not where the phone is): "
                            "a person must verify the owner's local time and mark hours_verified = Y")
MANUALLY_DIALED = ("Manually dialed means a person dials or clicks one number at a time, with no power, predictive "
                   "or multi-line dialer.")


def zones_in(text):
    """Zone names mentioned in an estimate string ('Eastern or Central (check)' -> ['Eastern', 'Central'])."""
    t = str(text or "")
    if "no daylight saving" in t:
        t = t.replace("Mountain", "Arizona")
    found = [z for z in ("Eastern", "Central", "Mountain", "Pacific", "Alaska", "Hawaii", "Arizona", "Atlantic") if z in t]
    return found


def _fmt(h):
    h = int(h)
    return "noon" if h == 12 else (f"{h}am" if h < 12 else f"{h - 12}pm")


def _states(state, phones):
    st = str(state or "").strip().upper()
    states = [st] if st else []
    for p in phones or ():
        digits = "".join(ch for ch in str(p) if ch.isdigit())[-10:]
        hit = area_codes.AREA_CODES.get(digits[:3]) if len(digits) == 10 else None
        if hit and hit[0] not in states:
            states.append(hit[0])
    return states


def uncoded(states):
    return [s for s in states if s not in STATE_HOURS]


def sunday_holiday(state, phones=()):
    """One line for the Sunday / holiday rules of every state this owner may be in (mailing state + area codes)."""
    states = _states(state, phones)
    if not states:
        return "Sunday / holiday rules: VERIFY (no state known)"
    parts = []
    for s in states:
        h = STATE_HOURS.get(s)
        if not h:
            parts.append(f"{s}: Sunday / holiday rules not coded, VERIFY")
            continue
        if h["sunday"] is None:
            day = "no calls on Sunday"
        elif h["sunday"] == "same":
            day = "no separate Sunday rule coded"
        else:
            day = f"Sunday {_fmt(h['sunday'][0])}-{_fmt(h['sunday'][1])} only"
        parts.append(f"{s}: {day}" + ("; no calls on state legal holidays (check the state's holiday list)" if h["holidays"] else
                                       "; no state holiday rule coded"))
    return "; ".join(parts)


def call_window(state, zip_zone, phones=()):
    """(call_window, call_window_basis, call_window_check) for one owner.
    Takes the time zone estimated from the mailing ZIP plus the zone of each phone's area code, keeps every
    possible zone, and returns the window that is legal in ALL of them (the stricter window). It is always an
    ESTIMATED window: the kit never knows where the phone actually is. call_window_check starts with "ok" only when
    the signals agree AND every state involved has its hours coded and sourced (STATE_HOURS); otherwise VERIFY.
    Monday-Saturday window; Sunday / holiday rules are in sunday_holiday()."""
    st = str(state or "").strip().upper()
    zz = zones_in(zip_zone)
    if "other zone" in str(zip_zone) and st in SPLIT:  # split state, no ZIP: every zone the state has
        zz = list(dict.fromkeys(zz + [z for v in SPLIT[st][1].values() for z in zones_in(v)]))
    reasons, basis = [], [f"mailing ZIP/state: {zip_zone or 'unknown'}"]
    if not zz or "check" in str(zip_zone) or "unknown" in str(zip_zone).lower():
        reasons.append("mailing location gives no single time zone")
    ac_zones = []
    for p in phones or ():
        digits = "".join(ch for ch in str(p) if ch.isdigit())[-10:]
        if len(digits) != 10:
            continue
        hit = area_codes.AREA_CODES.get(digits[:3])
        if not hit:
            basis.append(f"area code {digits[:3]}: not a US geographic area code")
            reasons.append(f"area code {digits[:3]} has no known US time zone")
            continue
        ac_st, ac_zone = hit
        z = zones_in(ac_zone)
        basis.append(f"area code {digits[:3]}: {ac_zone} ({ac_st})")
        if not z:
            reasons.append(f"area code {digits[:3]} zone {ac_zone} is outside the zones this kit handles")
        ac_zones += z
        if len(z) > 1:
            reasons.append(f"area code {digits[:3]} covers two time zones")
    if ac_zones and zz and set(ac_zones) != set(zz):
        reasons.append("area code and mailing ZIP point to different time zones")
    if not ac_zones and phones:
        reasons.append("no usable area code")
    states = _states(st, phones)
    missing = uncoded(states)
    if missing or not states:
        reasons.append("federal window; " + (", ".join(missing) if missing else "state") + " hours not coded, VERIFY")
    allz = list(dict.fromkeys(zz + ac_zones))
    if not allz:
        return "unknown: verify calling hours", "; ".join(basis), "VERIFY calling hours: no time zone could be estimated"
    coded = [STATE_HOURS[s] for s in states if s in STATE_HOURS]
    end = min([h["end"] for h in coded] + [FED_END])

    def start(season):
        return max([h.get("start_summer", h["start"]) if season else h["start"] for h in coded] + [FED_START])

    def local(zone):
        """window in this zone's local hours that is legal in every possible zone, in winter AND in summer"""
        a, b = -99, 99
        for season in (0, 1):
            lo = max(start(season) - OFFSETS[z][season] for z in allz)
            hi = min(end - OFFSETS[z][season] for z in allz)
            a, b = max(a, lo + OFFSETS[zone][season]), min(b, hi + OFFSETS[zone][season])
        return a, b
    ref = allz[0]
    a, b = local(ref)
    if a >= b:
        return "none: no hour is legal in every possible zone", "; ".join(basis), "VERIFY calling hours: zones too far apart"
    txt = f"{ESTIMATED}{_fmt(a)}-{_fmt(b)} {ref}"
    if len(allz) > 1:
        txt += " (= " + ", ".join(f"{_fmt(local(z)[0])}-{_fmt(local(z)[1])} {z}" for z in allz[1:]) + ")"
    txt += " Mon-Sat (Sundays / holidays: see sunday_holiday_rule)"
    for s in states:
        h = STATE_HOURS.get(s)
        basis.append(f"{s}: " + (f"{h['note']} [{h['source']}; last checked {h['checked']}]" if h else "hours not coded in this kit"))
    basis.append("federal: " + FED_SOURCE)
    basis.append("stricter window of all signals; " + sunday_holiday(st, phones))
    if reasons:
        check = "VERIFY calling hours: " + "; ".join(dict.fromkeys(reasons))
    elif ac_zones:
        check = "ok (estimate): mailing ZIP and area code agree; hours coded for " + ", ".join(states)
    else:
        check = ("ok so far (estimate): mailing ZIP/state only (no phone yet; re-checked against the area code once phones come back); "
                 "hours coded for " + ", ".join(states))
    return txt, "; ".join(basis), check + ". " + LOCATION_NOT_ESTABLISHED
