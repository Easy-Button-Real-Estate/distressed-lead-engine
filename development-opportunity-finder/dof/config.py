"""Load a market YAML file and fill in any heuristic keys the user left out.

Null means "I don't know" and is kept. A missing key gets the default.
Zoning codes are never invented here — a blank list stays blank.
"""

import copy, os
import yaml

# Heuristics a first run can use before the user has researched zoning.
# ADU / split / middle-housing minimums stay empty on purpose.
DEFAULT_RULES = {
    "adu": {
        "min_lot_sqft": None,
        "min_lot_width_ft": None,
        "max_adu_sqft": None,
        "max_units_on_lot": None,
        "max_adus": None,
        "allow_on_vacant": False,
        "setbacks_ft": {"front": None, "side": None, "rear": None},
        "max_lot_coverage_pct": None,
    },
    "lot_split": {
        "min_lot_sqft": None,
        "min_parent_lot_sqft": None,
        "min_lot_width_ft": None,
        "min_parent_width_ft": None,
        "max_lots": 2,
    },
    "middle_housing": {
        "max_units": 4,
        "min_lot_sqft": None,
        "min_lot_sqft_per_unit": None,
        "min_lot_width_ft": None,
        "skip_if_zoning_contains": [],
    },
    "basement": {
        "min_basement_sqft": 400,
        "max_finished_share": 0.50,
        "unfinished_type_words": ["unfinished", "partial", "partially finished", "partly finished"],
        "finished_type_words": ["finished", "full finished", "fully finished"],
        "not_basement_words": ["crawl", "slab", "none", "no basement", "pier"],
    },
    "garage_conversion": {
        "min_garage_sqft": 240,
        "min_garage_spaces": 1,
    },
    "underbuilt": {
        "max_far": 0.30,
        "min_lot_sqft": 5000,
        "max_house_sqft": None,
    },
    "add_bed_bath": {
        "min_sqft_per_bedroom": 700,
        "min_beds_for_bath_check": 3,
        "max_baths_for_mismatch": 1,
    },
    "attic_or_second_story": {
        "max_stories": 1,
        "min_lot_sqft": 4000,
        "min_house_sqft": 800,
    },
    "corner_or_alley": {
        "only_with_another_opportunity": False,
    },
}

DEFAULT_ENABLED = [
    "adu", "lot_split", "middle_housing", "basement", "garage_conversion",
    "underbuilt", "add_bed_bath", "attic_or_second_story", "corner_or_alley",
]

ZONING_USES = ["adu", "dadu", "lot_split", "middle_housing", "garage_conversion", "second_story"]


def _merge(base, override):
    """Override wins, including an explicit null. Missing keys stay at the default."""
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for key, value in override.items():
            out[key] = _merge(out[key], value) if key in out else value
        return out
    return override


def load_config(path):
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise SystemExit(f"{path} is not a YAML mapping. Expected keys like market: and rules:.")
    cfg = {
        "path": os.path.abspath(path),
        "kind": raw.get("kind") or "yours",
        "checked": raw.get("checked") or "",
        "market": raw.get("market") or {},
        "sources": raw.get("sources") or [],
        "enabled": raw.get("enabled") or list(DEFAULT_ENABLED),
        "zoning": {use: [] for use in ZONING_USES},
        "zones": raw.get("zones") or [],
        "rules": copy.deepcopy(DEFAULT_RULES),
    }
    cfg["zoning"] = _merge(cfg["zoning"], raw.get("zoning") or {})
    cfg["rules"] = _merge(cfg["rules"], raw.get("rules") or {})
    for key in ("name", "city", "county", "state", "notes"):
        cfg["market"].setdefault(key, "")
    return cfg
