"""One function per opportunity type.

Each check looks at one property and the market config and either returns a
hit or returns nothing. To add a type, copy the commented example at the
bottom of this file, then list its id under `enabled:` in your YAML.

Confidence means how complete the spreadsheet was, not whether the city
will approve the project:
  high   — the gates you set were in the file and passed
  medium — one fact was missing or only implied (a garage type with no size)
  low    — zoning was blank, or you have not put zoning codes in the config
"""

import re

REGISTRY = []

_BASE_POINTS = {"high": 30, "medium": 20, "low": 12}

_NONRES = re.compile(
    r"\b(industrial|warehouse|manufacturing|retail|office|commercial|church|"
    r"school|utility|agricultural|farm|exempt)\b",
    re.I,
)
_RES_HINT = re.compile(r"\b(single|sfr|duplex|triplex|fourplex|townho|residential|family)\b", re.I)
_CONDO = re.compile(r"\b(condo|condominium|apartment|coop|co-op)\b", re.I)
_VACANT = re.compile(r"\bvacant\b", re.I)


def opportunity(*, id, title, needs_any=(), needs_all=(), weight=1.0):
    """Register a check. needs_any: at least one of these columns must exist."""

    def deco(fn):
        REGISTRY.append({
            "id": id,
            "title": title,
            "fn": fn,
            "needs_any": tuple(needs_any),
            "needs_all": tuple(needs_all),
            "weight": weight,
        })
        return fn

    return deco


def fmt_num(value):
    if value is None:
        return ""
    if abs(value - round(value)) < 1e-6:
        return f"{int(round(value)):,}"
    return f"{value:,.2f}"


def norm_code(value):
    if value is None:
        return ""
    return re.sub(r"[\s_\-]+", "", str(value).upper())


def codes_match(value, allowed):
    """True when the cell equals the code, or starts with it (NR matches NR3).

    A single trailing letter is treated as an overlay (R5z matches R5) and
    returned as the second value. A one-letter code never prefix-matches,
    so listing "R" does not flag every zone.
    """
    allowed_n = norm_code(allowed)
    if not allowed_n or value is None:
        return False, ""
    for part in re.split(r"[/,;|]+", str(value)):
        prop = norm_code(part)
        if not prop:
            continue
        if prop == allowed_n:
            return True, ""
        if len(allowed_n) >= 2 and prop.startswith(allowed_n):
            rest = prop[len(allowed_n):]
            if rest.isdigit():
                return True, ""
            if len(rest) == 1 and rest.isalpha():
                return True, rest
    return False, ""


def rules_for(cfg, use):
    return cfg["rules"].get(use) or {}


def _zone_entry(cfg, zoning_value):
    for entry in cfg.get("zones") or []:
        matched, overlay = codes_match(zoning_value, entry.get("code", ""))
        if matched:
            return entry, overlay
    return None, ""


def effective_rules(cfg, use, zoning_value):
    """Citywide rules, with the matched `zones:` row laid on top."""
    rules = dict(rules_for(cfg, use))
    entry, overlay = _zone_entry(cfg, zoning_value)
    if not entry:
        return rules, ""
    key_map = {
        "adu": {
            "min_lot_sqft": "adu_min_lot_sqft",
            "min_lot_width_ft": "adu_min_lot_width_ft",
            "max_units_on_lot": "max_units",
        },
        "middle_housing": {
            "min_lot_sqft": "middle_min_lot_sqft",
            "min_lot_sqft_per_unit": "middle_min_lot_sqft_per_unit",
            "max_units": "middle_max_units",
            "min_lot_width_ft": "middle_min_lot_width_ft",
        },
        "lot_split": {
            "min_lot_sqft": "split_min_lot_sqft",
            "min_parent_lot_sqft": "split_min_parent_lot_sqft",
            "min_lot_width_ft": "split_min_lot_width_ft",
            "min_parent_width_ft": "split_min_parent_width_ft",
        },
    }
    for dest, src in key_map.get(use, {}).items():
        if entry.get(src) is not None:
            rules[dest] = entry[src]
    return rules, overlay


def allowed_codes(cfg, use):
    codes = list((cfg.get("zoning") or {}).get(use) or [])
    if not codes and use in ("garage_conversion", "attic_or_second_story", "second_story"):
        codes = list((cfg.get("zoning") or {}).get("adu") or [])
    if not codes and use == "garage_conversion":
        codes = list((cfg.get("zoning") or {}).get("dadu") or [])
    for entry in cfg.get("zones") or []:
        if entry.get("code"):
            codes.append(entry["code"])
    # Preserve order, drop duplicates.
    seen = set()
    out = []
    for code in codes:
        key = norm_code(code)
        if key and key not in seen:
            seen.add(key)
            out.append(code)
    return out


def zoning_status(cfg, prop, use):
    """yes / no / blank / no_column / unconfigured, plus a short note."""
    codes = allowed_codes(cfg, use)
    if not codes:
        return "unconfigured", "no zoning codes in the config for this use"
    if "zoning" not in prop.get("_present", set()):
        return "no_column", "the file has no zoning column"
    value = prop.get("zoning")
    if not value:
        return "blank", "the zoning cell is blank"
    overlays = []
    for code in codes:
        matched, overlay = codes_match(value, code)
        if matched:
            if overlay:
                overlays.append(overlay)
            note = f"zoning {value} matches {code}"
            if overlays:
                note += f" (trailing overlay letter {overlays[0]} was ignored — confirm it does not block this)"
            return "yes", note
    return "no", f"zoning {value} is not on your list for this use"


def use_class(prop):
    blob = f"{prop.get('property_type') or ''} {prop.get('land_use') or ''}"
    if _NONRES.search(blob) and not _RES_HINT.search(blob):
        return "nonres"
    if _CONDO.search(blob):
        return "condo"
    if _VACANT.search(blob):
        return "vacant"
    if prop.get("building_sqft") == 0 and re.search(r"\b(land|lot)\b", blob, re.I):
        return "vacant"
    return "house"


def gate_min(value, minimum):
    """unset (no rule), missing (rule set, cell empty), pass, or fail."""
    if minimum is None:
        return "unset"
    if value is None:
        return "missing"
    return "pass" if value >= minimum else "fail"


def confidence_from(zoning, gates):
    """Turn a zoning status plus lot-size gates into high / medium / low / None."""
    checked = [g for g in gates if g != "unset"]
    if "fail" in checked or zoning == "no":
        return None
    if zoning == "yes" and "missing" not in checked:
        return "high"
    if zoning == "yes":
        return "medium"
    # Zoning unknown. Only flag when a number you set actually passed,
    # or when the zone matched nothing because the cell was empty AND a
    # lot-size rule passed. Never flag the whole file off an empty config.
    if "pass" in checked and zoning in ("blank", "no_column", "unconfigured"):
        return "low"
    # One blank zoning cell is a weak hit. A missing zoning column is not,
    # or every house in the file would light up.
    if zoning == "blank" and "fail" not in checked:
        return "low"
    return None


def make_hit(op_id, title, confidence, why, verify, weight):
    return {
        "id": op_id,
        "title": title,
        "confidence": confidence,
        "why": why,
        "verify": verify,
        "points": int(round(_BASE_POINTS[confidence] * weight)),
    }


def sentence(text):
    """Capitalize the first letter only, so zoning codes stay 'NR3'."""
    text = (text or "").strip()
    if not text:
        return ""
    return text[0].upper() + text[1:]


def unit_phrase(n):
    word = "unit" if abs(float(n) - 1) < 1e-6 else "units"
    return f"{fmt_num(n)} {word}"


def join_verify(base, rules):
    extra = (rules.get("verify") or "").strip()
    base = " ".join((base or "").split())
    return f"{base} {extra}" if extra else base


def _blocked(prop, *, allow_vacant=False, allow_condo=False):
    kind = use_class(prop)
    if kind == "nonres":
        return True
    if kind == "condo" and not allow_condo:
        return True
    if kind == "vacant" and not allow_vacant:
        return True
    return False


def _parent_lot_needed(rules):
    need = rules.get("min_parent_lot_sqft")
    each = rules.get("min_lot_sqft")
    if each:
        need = max(need or 0, 2 * each)
    return need


def _parent_width_needed(rules):
    if rules.get("min_parent_width_ft"):
        return rules["min_parent_width_ft"]
    if rules.get("min_lot_width_ft"):
        return 2 * rules["min_lot_width_ft"]
    return None


def split_is_configured(cfg):
    rules, _ = effective_rules(cfg, "lot_split", None)
    if _parent_lot_needed(rules):
        return True
    for entry in cfg.get("zones") or []:
        if entry.get("split_min_parent_lot_sqft") or entry.get("split_min_lot_sqft"):
            return True
    return False


def activation_note(cfg, op_id):
    """Plain-language reason a check can run and still find nothing useful."""
    if op_id == "lot_split" and not split_is_configured(cfg):
        return ("Lot split is off until you set rules.lot_split.min_parent_lot_sqft "
                "or min_lot_sqft (the size of each new lot). A zoning match alone is not a split.")
    if op_id in ("adu", "middle_housing"):
        rules = rules_for(cfg, op_id)
        has_number = any(rules.get(k) for k in ("min_lot_sqft", "min_lot_width_ft", "min_lot_sqft_per_unit"))
        if not allowed_codes(cfg, op_id) and not has_number and not cfg.get("zones"):
            return (f"{op_id}: no zoning codes and no minimum lot size yet, so nothing was flagged. "
                    f"Add them under zoning.{op_id} and rules.{op_id}, or say \"set this up for my city\".")
    return ""


# --- checks -----------------------------------------------------------------

@opportunity(id="adu", title="ADU / DADU", needs_any=("zoning", "lot_sqft", "lot_width_ft"), weight=1.0)
def adu(prop, cfg):
    rules, overlay = effective_rules(cfg, "adu", prop.get("zoning"))
    if _blocked(prop, allow_vacant=bool(rules.get("allow_on_vacant"))):
        return None
    status, znote = zoning_status(cfg, prop, "adu")
    gates = [gate_min(prop.get("lot_sqft"), rules.get("min_lot_sqft")),
             gate_min(prop.get("lot_width_ft"), rules.get("min_lot_width_ft"))]
    units = prop.get("units")
    unit_note = ""
    cap = "high"
    if units is not None:
        if rules.get("max_units_on_lot") is not None and units >= rules["max_units_on_lot"]:
            return None
        max_adus = rules.get("max_adus")
        if max_adus is not None and units > 1 + max_adus:
            return None
        if max_adus is not None and units >= 1 + max_adus:
            cap = "medium"
            unit_note = (f" Already {unit_phrase(units)} on the lot; your cap is "
                         f"{fmt_num(max_adus)} ADU(s), so this may already be full.")
        elif units >= 2:
            cap = "medium"
            unit_note = f" Already {unit_phrase(units)}; confirm one of them is not already an ADU."
    confidence = confidence_from(status, gates)
    if confidence is None:
        return None
    if _rank(cap) < _rank(confidence):
        confidence = cap
    bits = [sentence(znote) + "."]
    if rules.get("min_lot_sqft") and prop.get("lot_sqft") is not None:
        bits.append(f"Lot is {fmt_num(prop['lot_sqft'])} sqft (minimum {fmt_num(rules['min_lot_sqft'])}).")
    elif prop.get("lot_sqft") is not None:
        bits.append(f"Lot is {fmt_num(prop['lot_sqft'])} sqft.")
    if rules.get("min_lot_width_ft") and prop.get("lot_width_ft") is not None:
        bits.append(f"Width is {fmt_num(prop['lot_width_ft'])} ft (minimum {fmt_num(rules['min_lot_width_ft'])}).")
    if rules.get("max_adu_sqft"):
        bits.append(f"Your notes cap an ADU around {fmt_num(rules['max_adu_sqft'])} sqft.")
    why = " ".join(bits) + unit_note
    verify = "Confirm the zoning map, setbacks, coverage, and that a primary house is allowed an extra unit."
    if overlay:
        verify += f" The zoning text has an overlay letter ({overlay})."
    backs = rules.get("setbacks_ft") or {}
    back_bits = [f"{side} {fmt_num(backs.get(side))} ft" for side in ("front", "side", "rear") if backs.get(side)]
    if back_bits:
        verify += " Setbacks in your config: " + ", ".join(back_bits) + "."
    if rules.get("max_lot_coverage_pct"):
        verify += f" Lot coverage cap in your config: {rules['max_lot_coverage_pct']}%."
    verify = join_verify(verify, rules)
    return make_hit("adu", "ADU / DADU", confidence, why.strip(), verify.strip(), 1.0)


@opportunity(id="lot_split", title="Lot split", needs_any=("lot_sqft",), weight=1.15)
def lot_split(prop, cfg):
    if not split_is_configured(cfg):
        return None
    if _blocked(prop, allow_vacant=True):
        return None
    rules, overlay = effective_rules(cfg, "lot_split", prop.get("zoning"))
    if _overlay_blocked(prop.get("zoning"), rules.get("skip_if_zoning_contains")):
        return None
    need = _parent_lot_needed(rules)
    if not need:
        return None
    status, znote = zoning_status(cfg, prop, "lot_split")
    width_need = _parent_width_needed(rules)
    gates = [gate_min(prop.get("lot_sqft"), need), gate_min(prop.get("lot_width_ft"), width_need)]
    confidence = confidence_from(status, gates)
    if confidence is None:
        return None
    each = rules.get("min_lot_sqft")
    why = (f"{sentence(znote)}. Parent lot is {fmt_num(prop.get('lot_sqft'))} sqft; "
           f"a {fmt_num(rules.get('max_lots') or 2)}-lot split needs about {fmt_num(need)} sqft")
    if each:
        why += f" so each piece can be {fmt_num(each)} sqft"
    why += "."
    if width_need and prop.get("lot_width_ft") is not None:
        why += f" Width is {fmt_num(prop['lot_width_ft'])} ft (looking for {fmt_num(width_need)} ft)."
    verify = ("Confirm frontage, access, critical areas, and whether the city allows a short plat "
              "or only a middle-housing land division.")
    if overlay:
        verify += f" Overlay letter {overlay} was ignored."
    return make_hit("lot_split", "Lot split", confidence, why, join_verify(verify, rules), 1.15)


@opportunity(id="middle_housing", title="Middle housing (2–4 units)",
             needs_any=("zoning", "lot_sqft"), weight=1.1)
def middle_housing(prop, cfg):
    if _blocked(prop, allow_vacant=True):
        return None
    rules, overlay = effective_rules(cfg, "middle_housing", prop.get("zoning"))
    if _overlay_blocked(prop.get("zoning"), rules.get("skip_if_zoning_contains")):
        return None
    status, znote = zoning_status(cfg, prop, "middle_housing")
    per = rules.get("min_lot_sqft_per_unit")
    min_lot = rules.get("min_lot_sqft")
    if per:
        min_lot = max(min_lot or 0, 2 * per)
    gates = [gate_min(prop.get("lot_sqft"), min_lot),
             gate_min(prop.get("lot_width_ft"), rules.get("min_lot_width_ft"))]
    cap_units = rules.get("max_units") or 4
    units = prop.get("units")
    possible = None
    if per and prop.get("lot_sqft"):
        possible = min(cap_units, int(prop["lot_sqft"] // per))
        if possible < 2:
            return None
    if units is not None and units >= cap_units:
        return None
    if units is not None and possible is not None and units >= possible:
        return None
    confidence = confidence_from(status, gates)
    if confidence is None:
        return None
    why = f"{sentence(znote)}. Cap in your config is {fmt_num(cap_units)} units."
    if prop.get("lot_sqft") is not None and min_lot:
        why += f" Lot is {fmt_num(prop['lot_sqft'])} sqft (minimum {fmt_num(min_lot)})."
    if units is not None:
        why += f" {unit_phrase(units)} there now."
    elif use_class(prop) == "vacant":
        why += " The row looks like vacant land, so this is a new-construction screen, not a conversion."
    if possible:
        why += f" At {fmt_num(per)} sqft of lot per unit, the spreadsheet supports about {possible} units."
    verify = "Confirm the unit count the zone actually allows, parking, and any affordability or transit bonus."
    if overlay:
        verify += f" Overlay letter {overlay} was ignored."
    return make_hit("middle_housing", "Middle housing (2–4 units)", confidence, why, join_verify(verify, rules), 1.1)


@opportunity(
    id="basement",
    title="Unfinished basement",
    needs_any=("basement_sqft", "basement_finished_sqft", "basement_unfinished_sqft",
               "below_grade_sqft", "below_grade_finished_sqft", "basement_type"),
    weight=0.95,
)
def basement(prop, cfg):
    if _blocked(prop, allow_vacant=False, allow_condo=True):
        return None
    rules = rules_for(cfg, "basement")
    total = prop.get("basement_sqft")
    if total is None:
        total = prop.get("below_grade_sqft")
    finished = prop.get("basement_finished_sqft")
    if finished is None:
        finished = prop.get("below_grade_finished_sqft")
    unfinished = prop.get("basement_unfinished_sqft")
    if total is None and finished is not None and unfinished is not None:
        total = finished + unfinished
    kind = _basement_words(prop.get("basement_type"), rules)
    minimum = rules.get("min_basement_sqft") or 0
    share_cap = rules.get("max_finished_share")
    if share_cap is None:
        share_cap = 0.50

    if kind == "none":
        return None
    if total is not None and total < minimum and kind != "unfinished":
        return None
    if unfinished is not None and total is None and unfinished < minimum:
        return None

    why = ""
    confidence = None
    if total is not None and finished is not None and total > 0:
        share = min(1.0, finished / total)
        if share > share_cap:
            return None
        if total < minimum:
            return None
        label = "unfinished" if share == 0 else "partly finished"
        why = (f"Basement is {fmt_num(total)} sqft and {fmt_num(finished)} sqft is finished "
               f"({share:.0%} finished, your cutoff is {share_cap:.0%}). Reads as {label}.")
        confidence = "high"
    elif unfinished is not None and unfinished >= minimum:
        why = f"Unfinished basement area is {fmt_num(unfinished)} sqft (minimum {fmt_num(minimum)})."
        confidence = "high"
    elif kind == "unfinished":
        why = f"Basement type is \"{prop.get('basement_type')}\"."
        if total is not None:
            why += f" Listed area is {fmt_num(total)} sqft."
        else:
            why += " No basement square feet in the file, so confirm there is room to finish."
        confidence = "medium"
    elif total is not None and total >= minimum and finished is None and kind != "finished":
        why = (f"Basement is {fmt_num(total)} sqft but the file does not say how much is finished. "
               "It may already be done.")
        confidence = "low"
    if not confidence:
        return None
    verify = join_verify(
        "Confirm ceiling height, egress, moisture, and whether the space is already permitted living area.",
        rules)
    return make_hit("basement", "Unfinished basement", confidence, why, verify, 0.95)


@opportunity(id="garage_conversion", title="Garage conversion",
             needs_any=("garage_sqft", "garage_spaces", "garage_type"), weight=0.85)
def garage_conversion(prop, cfg):
    if _blocked(prop):
        return None
    rules = rules_for(cfg, "garage_conversion")
    status, znote = zoning_status(cfg, prop, "garage_conversion")
    signal, detail = _garage_signal(prop, rules)
    if not signal:
        return None
    # A real square-footage measurement is the numeric gate. Type-only is "missing".
    if prop.get("garage_sqft") is not None or prop.get("garage_spaces") is not None:
        gates = ["pass"]
    else:
        gates = ["missing"]
    confidence = confidence_from(status, gates)
    if confidence is None:
        return None
    if signal == "medium" and confidence == "high":
        confidence = "medium"
    why = f"{detail}. {sentence(znote)}."
    verify = join_verify(
        "Confirm the garage is real (not a carport or a deeded stall), the conversion meets light and egress, "
        "and you can spare the parking.",
        rules)
    return make_hit("garage_conversion", "Garage conversion", confidence, why, verify, 0.85)


@opportunity(id="underbuilt", title="Under-built lot", needs_all=("lot_sqft", "building_sqft"), weight=1.0)
def underbuilt(prop, cfg):
    if _blocked(prop):
        return None
    rules = rules_for(cfg, "underbuilt")
    lot, house = prop.get("lot_sqft"), prop.get("building_sqft")
    if not lot or not house or house <= 0:
        return None
    if rules.get("min_lot_sqft") and lot < rules["min_lot_sqft"]:
        return None
    if rules.get("max_house_sqft") and house > rules["max_house_sqft"]:
        return None
    far = house / lot
    max_far = rules.get("max_far")
    if max_far is None or far > max_far:
        return None
    why = (f"House is {fmt_num(house)} sqft on a {fmt_num(lot)} sqft lot "
           f"(building-to-lot ratio {far:.2f}, your cutoff is {max_far:.2f}).")
    verify = join_verify(
        "This cutoff is yours, not the city's FAR cap. Confirm the real floor-area limit, "
        "setbacks, and trees before you plan a bigger house.",
        rules)
    return make_hit("underbuilt", "Under-built lot", "high", why, verify, 1.0)


@opportunity(id="add_bed_bath", title="Add a bedroom or bathroom",
             needs_all=("bedrooms",), needs_any=("building_sqft", "bathrooms"), weight=0.7)
def add_bed_bath(prop, cfg):
    if _blocked(prop, allow_condo=True):
        return None
    rules = rules_for(cfg, "add_bed_bath")
    beds, baths, house = prop.get("bedrooms"), prop.get("bathrooms"), prop.get("building_sqft")
    if beds is None or beds <= 0:
        return None
    reasons = []
    per = rules.get("min_sqft_per_bedroom")
    if per and house:
        sqft_per = house / beds
        if sqft_per >= per:
            reasons.append(f"{fmt_num(house)} sqft / {fmt_num(beds)} bedrooms = {fmt_num(sqft_per)} sqft per bedroom "
                           f"(your cutoff is {fmt_num(per)}). Room to add a bedroom.")
    min_beds = rules.get("min_beds_for_bath_check")
    max_baths = rules.get("max_baths_for_mismatch")
    if min_beds is not None and max_baths is not None and baths is not None and beds >= min_beds and baths <= max_baths:
        bath_word = "bathroom" if abs(float(baths) - 1) < 1e-6 else "bathrooms"
        reasons.append(f"{fmt_num(beds)} bedrooms and {fmt_num(baths)} {bath_word}. A bath is the obvious add.")
    if not reasons:
        return None
    verify = join_verify(
        "Confirm the floor plan. A big sqft-per-bedroom number can just be a great room, "
        "and an extra bath needs a plumbing wall.",
        rules)
    return make_hit("add_bed_bath", "Add a bedroom or bathroom", "high", " ".join(reasons), verify, 0.7)


@opportunity(id="attic_or_second_story", title="Attic or second story",
             needs_all=("stories",), weight=0.8)
def attic_or_second_story(prop, cfg):
    if _blocked(prop):
        return None
    rules, overlay = effective_rules(cfg, "attic_or_second_story", prop.get("zoning"))
    stories = prop.get("stories")
    if stories is None:
        return None
    max_stories = rules.get("max_stories") if rules.get("max_stories") is not None else 1
    if stories > max_stories:
        return None
    status, znote = zoning_status(cfg, prop, "second_story")
    gates = [gate_min(prop.get("lot_sqft"), rules.get("min_lot_sqft")),
             gate_min(prop.get("building_sqft"), rules.get("min_house_sqft"))]
    confidence = confidence_from(status, gates)
    if confidence is None:
        return None
    why = (f"{fmt_num(stories)}-story house. {sentence(znote)}.")
    if prop.get("building_sqft"):
        why += f" House is {fmt_num(prop['building_sqft'])} sqft."
    if prop.get("lot_sqft"):
        why += f" Lot is {fmt_num(prop['lot_sqft'])} sqft."
    verify = join_verify(
        "Confirm height limits, the foundation, and whether an addition is cheaper than a dormer. "
        "A 1-story house is a clue, not a structural report.",
        rules)
    if overlay:
        verify += f" Overlay letter {overlay} was ignored."
    return make_hit("attic_or_second_story", "Attic or second story", confidence, why, verify.strip(), 0.8)


@opportunity(id="corner_or_alley", title="Corner lot or alley",
             needs_any=("corner_lot", "alley_access"), weight=0.45)
def corner_or_alley(prop, cfg):
    if use_class(prop) == "nonres":
        return None
    corner = _is_yes(prop.get("corner_lot"))
    alley = _is_yes(prop.get("alley_access"))
    if not corner and not alley:
        return None
    bits = []
    if corner:
        bits.append("the corner-lot column says yes")
    if alley:
        bits.append("the alley column says yes")
    why = sentence(" and ".join(bits)) + ". Corner and alley lots are easier to split or to park."
    verify = join_verify("Confirm on a map. Assessor corner and alley flags are often wrong.", rules_for(cfg, "corner_or_alley"))
    # Medium on purpose: the column is a hint, and you still have to look at the lot.
    return make_hit("corner_or_alley", "Corner lot or alley", "medium", why, verify.strip(), 0.45)


# --- helpers used by the checks --------------------------------------------

def _rank(level):
    return {"high": 3, "medium": 2, "low": 1}[level]


def _is_yes(value):
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"y", "yes", "true", "t", "1", "corner", "alley"}


def _overlay_blocked(zoning_value, tokens):
    if not tokens or not zoning_value:
        return False
    for part in re.split(r"[/,;|]+", str(zoning_value)):
        prop = norm_code(part)
        for token in tokens:
            tok = norm_code(token)
            if tok and prop.endswith(tok) and prop != tok:
                return True
    return False


def _basement_words(text, rules):
    if not text:
        return ""
    lowered = str(text).lower()
    for word in rules.get("not_basement_words") or []:
        if word and word.lower() in lowered:
            return "none"
    for word in rules.get("unfinished_type_words") or []:
        if word and word.lower() in lowered:
            return "unfinished"
    for word in rules.get("finished_type_words") or []:
        if word and word.lower() in lowered and "unfinished" not in lowered and "partial" not in lowered:
            return "finished"
    return "unknown"


def _garage_signal(prop, rules):
    sqft = prop.get("garage_sqft")
    spaces = prop.get("garage_spaces")
    raw_type = prop.get("garage_type") or ""
    text = raw_type.lower()
    min_sqft = rules.get("min_garage_sqft") if rules.get("min_garage_sqft") is not None else 240
    min_spaces = rules.get("min_garage_spaces") if rules.get("min_garage_spaces") is not None else 1
    if sqft is not None:
        if sqft >= min_sqft:
            return "high", f"Garage is {fmt_num(sqft)} sqft"
        return None, ""
    if spaces is not None:
        if spaces >= min_spaces:
            return "medium", f"{fmt_num(spaces)} garage space(s)"
        return None, ""
    if not text:
        return None, ""
    if any(bad in text for bad in ("none", "no garage", "carport")) and "garage" not in text:
        return None, ""
    if any(word in text for word in ("garage", "attached", "detached", "tuckunder", "tuck-under")):
        return "medium", f"Garage type is \"{raw_type}\" (no square feet in the file)"
    return None, ""


def skip_reason(op, present, cfg):
    """Why a check cannot run on this file at all. None means it can run."""
    if op["needs_all"]:
        missing = [name for name in op["needs_all"] if name not in present]
        if missing:
            return "missing column(s): " + ", ".join(missing)
    if op["needs_any"] and not any(name in present for name in op["needs_any"]):
        return "none of these columns were in the file: " + ", ".join(op["needs_any"])
    if op["id"] == "lot_split" and not split_is_configured(cfg):
        return activation_note(cfg, "lot_split")
    return None


# --- Adding an opportunity type --------------------------------------------
# 1. Copy the function below, remove the comment marks, and pick a new id.
# 2. Add that id under `enabled:` in config/my-market.yaml.
# 3. Add a rules: block with the numbers the function should read.
# 4. Re-run: python -m dof.run --csv samples/sample_properties.csv --config config/my-market.yaml
#
# @opportunity(id="big_yard", title="Big yard", needs_any=("lot_sqft",), weight=0.8)
# def big_yard(prop, cfg):
#     rules = rules_for(cfg, "big_yard")
#     minimum = rules.get("min_lot_sqft") or 10000
#     lot = prop.get("lot_sqft")
#     if lot is None or lot < minimum:
#         return None
#     return make_hit(
#         "big_yard", "Big yard", "high",
#         f"Lot is {fmt_num(lot)} sqft (your minimum is {fmt_num(minimum)}).",
#         "Walk it. A big yard is not the same as a buildable yard.",
#         0.8,
#     )
