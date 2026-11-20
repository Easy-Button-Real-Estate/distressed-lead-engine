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
FED_START, FED_END = 8, 21  # federal: 8am-9pm in the called person's local time
# states with a stricter end time for telephone solicitation (check your state; rules change)
STATE_END = {"FL": 20, "OK": 20, "MD": 20}
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


def call_window(state, zip_zone, phones=()):
    """(call_window, call_window_basis, call_window_check) for one owner.
    Takes the time zone estimated from the mailing ZIP plus the zone of each phone's area code, keeps every
    possible zone, and returns the window that is legal in ALL of them (the stricter window). When the signals
    disagree or a zone is unknown, call_window_check starts with VERIFY: the user must check calling hours."""
    st = str(state or "").strip().upper()
    zz = zones_in(zip_zone)
    if "other zone" in str(zip_zone) and st in SPLIT:  # split state, no ZIP: every zone the state has
        zz = list(dict.fromkeys(zz + [z for v in SPLIT[st][1].values() for z in zones_in(v)]))
    reasons, basis = [], [f"mailing ZIP/state: {zip_zone or 'unknown'}"]
    if not zz or "check" in str(zip_zone) or "unknown" in str(zip_zone).lower():
        reasons.append("mailing location gives no single time zone")
    states = {st} if st else set()
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
        states.add(ac_st)
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
    allz = list(dict.fromkeys(zz + ac_zones))
    if not allz:
        return "unknown: verify calling hours", "; ".join(basis), "VERIFY calling hours: no time zone could be estimated"
    end = min([STATE_END.get(s, FED_END) for s in states] or [FED_END])
    def local(zone):
        """window in this zone's local hours that is legal in every possible zone, in winter AND in summer"""
        a, b = -99, 99
        for season in (0, 1):
            lo = max(FED_START - OFFSETS[z][season] for z in allz)
            hi = min(end - OFFSETS[z][season] for z in allz)
            a, b = max(a, lo + OFFSETS[zone][season]), min(b, hi + OFFSETS[zone][season])
        return a, b
    ref = allz[0]
    a, b = local(ref)
    if a >= b:
        return "none: no hour is legal in every possible zone", "; ".join(basis), "VERIFY calling hours: zones too far apart"
    txt = f"{_fmt(a)}-{_fmt(b)} {ref}"
    if len(allz) > 1:
        txt += " (= " + ", ".join(f"{_fmt(local(z)[0])}-{_fmt(local(z)[1])} {z}" for z in allz[1:]) + ")"
    if end < FED_END:
        basis.append("state rule: calls end by " + _fmt(end) + " (" + ", ".join(sorted(s for s in states if s in STATE_END)) + ")")
    basis.append("stricter window of all signals; Sundays / holidays: check your state")
    check = (("VERIFY calling hours: " + "; ".join(dict.fromkeys(reasons))) if reasons else
             "ok: mailing ZIP and area code agree" if ac_zones else
             "ok so far: mailing ZIP/state only (no phone yet; re-checked against the area code once phones come back)")
    return txt, "; ".join(basis), check
