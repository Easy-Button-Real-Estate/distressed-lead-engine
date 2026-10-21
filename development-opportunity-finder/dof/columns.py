"""Turn a PropStream, assessor, or other property CSV into one shape.

Headers are matched by a nickname list, not by column order. A "Lot Size SqFt"
column and a "LOTSQFT" column both become lot_sqft. Anything we don't
recognize is reported back so you can see what the screen never looked at.
"""

import csv, re, statistics

# (canonical field, priority, aliases).
# Lower priority wins when two columns could fill the same field
# (a situs address beats a generic "Address" if both are present).
# Aliases are written the way a human would, then normalized.
_SPECS = [
    ("address", 1, ["situs address", "site address", "property address", "prop address",
                    "situs", "site addr", "property location", "location address"]),
    ("address", 2, ["address", "street address", "street", "property street"]),
    ("city", 1, ["city", "situs city", "property city", "site city"]),
    ("state", 1, ["state", "situs state", "property state", "site state"]),
    ("zip", 1, ["zip", "zip code", "zipcode", "postal code", "situs zip", "property zip"]),
    ("parcel_id", 1, ["apn", "pin", "parcel", "parcel id", "parcel number", "parcel no",
                      "parcelid", "tax id", "tax parcel", "taxlot", "tax lot",
                      "assessor parcel number", "pid"]),
    ("owner_name", 1, ["owner name", "owner", "owner 1 full name", "owner full name",
                       "primary owner", "taxpayer name", "taxpayer"]),
    ("owner_first", 1, ["owner 1 first name", "owner first name", "owner 1 first"]),
    ("owner_last", 1, ["owner 1 last name", "owner last name", "owner 1 last"]),
    ("property_type", 1, ["property type", "prop type", "property use", "use description",
                          "land use description", "residential type"]),
    ("land_use", 1, ["land use", "use code", "present use", "property class", "use class",
                     "land use code"]),
    ("zoning", 1, ["zoning", "zoning code", "zone", "zone code", "zone desc",
                   "zoning district", "zoning description", "zone description"]),
    ("lot_sqft", 1, ["lot size sqft", "lot size sq ft", "lot sqft", "lot sq ft",
                     "lot square feet", "lotsqft", "lot area", "land sqft", "land area",
                     "lotarea", "land sq ft", "lot size square feet", "total lot sqft"]),
    ("lot_size_raw", 2, ["lot size"]),  # PropStream sometimes exports this in acres
    ("lot_acres", 1, ["lot acres", "acres", "lot size acres", "land acres"]),
    ("lot_width_ft", 1, ["lot width", "width", "frontage", "lot frontage", "lot width ft",
                         "frontage ft", "street frontage"]),
    ("lot_depth_ft", 1, ["lot depth", "depth"]),
    ("building_sqft", 1, ["building sqft", "building sq ft", "bldg sqft", "bldg sq ft",
                          "square feet", "sq ft", "sqft", "living area", "living sqft",
                          "living sq ft", "finished living area", "total living area",
                          "building area", "bldgarea", "finished area", "total sqft",
                          "floor area", "living area sqft"]),
    ("year_built", 1, ["year built", "yr built", "yearbuilt", "effective year built"]),
    ("bedrooms", 1, ["bedrooms", "bedroom", "beds", "bed", "no beds", "bed rooms",
                     "total bedrooms", "br"]),
    ("bathrooms", 1, ["bathrooms", "bathroom", "baths", "total baths", "total bathrooms",
                      "bath rooms"]),
    ("full_baths", 1, ["full baths", "full bath", "full bathrooms", "baths full"]),
    ("half_baths", 1, ["half baths", "half bath", "half bathrooms", "baths half"]),
    ("stories", 1, ["stories", "story", "number of stories", "num stories", "floors",
                    "number of floors", "# of stories"]),
    ("basement_sqft", 1, ["basement sqft", "basement sq ft", "basement square feet",
                          "total basement sqft", "basement area", "bsmt sqft", "sqft bsmt",
                          "bsmt area", "basement size"]),
    ("basement_finished_sqft", 1, ["basement finished sqft", "finished basement sqft",
                                   "finished basement", "fin basement sqft", "fin bsmt",
                                   "bsmt finished", "finished bsmt sqft"]),
    ("basement_unfinished_sqft", 1, ["basement unfinished sqft", "unfinished basement sqft",
                                     "unfinished basement", "unfin basement", "unfin bsmt"]),
    ("below_grade_sqft", 1, ["below grade sqft", "below grade sq ft", "below grade area",
                             "below grade square feet", "lower level sqft"]),
    ("below_grade_finished_sqft", 1, ["below grade finished sqft", "below grade finished",
                                      "finished below grade", "below grade finished area"]),
    ("basement_type", 1, ["basement type", "basement", "bsmt", "bsmt type", "basement description",
                          "foundation", "foundation type"]),
    ("garage_sqft", 1, ["garage sqft", "garage sq ft", "garage square feet", "garage area",
                        "garagesqft"]),
    ("garage_spaces", 1, ["garage spaces", "parking spaces", "garage count", "# garage spaces",
                          "number of garage spaces"]),
    ("garage_type", 1, ["garage type", "garage", "garage description", "parking type"]),
    ("units", 1, ["units", "number of units", "unit count", "living units", "residential units",
                  "dwelling units", "num units", "# of units"]),
    ("corner_lot", 1, ["corner lot", "corner", "is corner", "corner property", "on corner"]),
    ("alley_access", 1, ["alley", "alley access", "on alley", "alley lot", "has alley"]),
]

_ALIAS = {}
for _field, _pri, _aliases in _SPECS:
    for _a in _aliases:
        _ALIAS.setdefault(_a, (_field, _pri))

_TEXT = {"address", "city", "state", "zip", "parcel_id", "owner_name", "owner_first",
         "owner_last", "property_type", "land_use", "zoning", "basement_type",
         "garage_type", "corner_lot", "alley_access"}

_EMPTY = {"", "n/a", "na", "none", "null", "-", "--", "unknown", "n.a."}


def norm_header(header):
    """Lowercase, drop punctuation, collapse spaces. 'Lot Size (SqFt)' -> 'lot size sqft'."""
    text = (header or "").replace("\ufeff", "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def parse_number(value):
    """Pull the first number out of '7,200', '0.18 acres', '$450'. Blank stays None."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _EMPTY:
        return None
    text = text.replace(",", "").replace("$", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group())


def map_headers(headers):
    """Return ({original header: field}, [headers we did not recognize])."""
    chosen = {}
    mapped = {}
    unmapped = []
    for header in headers or []:
        if header is None:
            continue
        spec = _ALIAS.get(norm_header(header))
        if not spec:
            unmapped.append(header)
            continue
        field, priority = spec
        previous = chosen.get(field)
        if previous is None or priority < previous[0]:
            if previous is not None:
                unmapped.append(previous[1])
                mapped.pop(previous[1], None)
            chosen[field] = (priority, header)
            mapped[header] = field
        else:
            unmapped.append(header)
    return mapped, unmapped


def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _EMPTY:
        return None
    return text


def build_prop(raw, mapping):
    prop = {}
    by_field = {field: header for header, field in mapping.items()}
    for field, header in by_field.items():
        raw_value = raw.get(header)
        if field in _TEXT:
            prop[field] = _clean_text(raw_value)
        else:
            prop[field] = parse_number(raw_value)
    if prop.get("state"):
        prop["state"] = prop["state"].upper()
    if prop.get("zip"):
        digits = re.sub(r"\D", "", prop["zip"])
        prop["zip"] = digits[:5] if len(digits) >= 5 else prop["zip"]
    return prop


def _derive_lot_sqft(props, present):
    """Fill lot_sqft from an acres column, or from a 'Lot Size' column that is really acres."""
    if "lot_sqft" not in present and "lot_size_raw" in present:
        values = [p.get("lot_size_raw") for p in props if p.get("lot_size_raw")]
        # A lot-size column whose typical value is under 20 is acres (0.18), not sqft (7800).
        as_acres = bool(values) and statistics.median(values) <= 20
        for prop in props:
            raw = prop.get("lot_size_raw")
            if raw is None:
                continue
            prop["lot_sqft"] = raw * 43560 if as_acres else raw
        present.add("lot_sqft")
    if "lot_acres" in present:
        for prop in props:
            if prop.get("lot_sqft") is None and prop.get("lot_acres"):
                prop["lot_sqft"] = prop["lot_acres"] * 43560
        present.add("lot_sqft")
    return present


def _derive_baths(props, present):
    if "bathrooms" in present:
        return
    if "full_baths" not in present and "half_baths" not in present:
        return
    for prop in props:
        full, half = prop.get("full_baths"), prop.get("half_baths")
        if full is None and half is None:
            continue
        prop["bathrooms"] = (full or 0) + 0.5 * (half or 0)
    present.add("bathrooms")


def _derive_owner(props):
    for prop in props:
        if prop.get("owner_name"):
            continue
        parts = [prop.get("owner_first") or "", prop.get("owner_last") or ""]
        name = " ".join(p for p in parts if p).strip()
        prop["owner_name"] = name or None


def load_csv(path):
    """Read a CSV. Returns (properties, column report)."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        raw_rows = list(reader)
    mapping, unmapped = map_headers(headers)
    present = set(mapping.values())
    props = []
    for raw in raw_rows:
        prop = build_prop(raw, mapping)
        if prop.get("address") or prop.get("parcel_id"):
            props.append(prop)
    present = _derive_lot_sqft(props, present)
    _derive_baths(props, present)
    _derive_owner(props)
    report = {"mapped": mapping, "unmapped": unmapped, "present": present, "read": len(raw_rows)}
    return props, report
