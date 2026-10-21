"""Offline tests. From this folder: python tests/test_finder.py"""

import csv, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dof.columns import load_csv, norm_header
from dof.config import load_config
from dof.opportunities import codes_match
from dof.run import screen, render_summary

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "samples", "sample_properties.csv")
SEATTLE = os.path.join(ROOT, "config", "examples", "seattle-wa.yaml")


def _ids(result):
    out = {}
    for item in result["flagged"]:
        out[item["prop"]["address"]] = {h["id"] for h in item["hits"]}
    return out


def _hit(result, address, op_id):
    for item in result["flagged"]:
        if item["prop"]["address"] == address:
            for hit in item["hits"]:
                if hit["id"] == op_id:
                    return hit
    return None


def _screen(csv_path, config_path):
    cfg = load_config(config_path)
    props, columns = load_csv(csv_path)
    return cfg, screen(props, cfg, columns)


def test_codes():
    assert codes_match("NR3", "NR") == (True, "")
    assert codes_match("nr-3", "NR") == (True, "")
    assert codes_match("RSL", "NR") == (False, "")
    assert codes_match("R5z", "R5") == (True, "Z")
    assert codes_match("R2.5", "R2") == (False, "")
    assert codes_match("R2.5", "R2.5") == (True, "")
    assert codes_match("SF-3", "SF-1") == (False, "")
    assert codes_match("SF-3", "SF")[0] is True
    assert codes_match("R5", "R") == (False, "")
    assert norm_header("Lot Size (SqFt)") == "lot size sqft"
    print("codes ok")


def test_sample_seattle():
    cfg, result = _screen(SAMPLE, SEATTLE)
    found = _ids(result)
    assert result["screened"] == 15
    assert len(result["flagged"]) == 11
    assert result["flagged"][0]["prop"]["address"] == "101 Big Lot Ave"
    assert found["101 Big Lot Ave"] == {
        "adu", "lot_split", "middle_housing", "basement", "garage_conversion",
        "underbuilt", "add_bed_bath", "attic_or_second_story", "corner_or_alley",
    }
    assert found["202 Finished St"] == {"adu", "middle_housing"}
    assert found["505 Vacant Ln"] == {"lot_split", "middle_housing"}
    assert found["606 Partial Pl"] == {"adu", "middle_housing", "basement", "attic_or_second_story", "add_bed_bath"}
    assert found["707 Tiny Ct"] == {"adu"}
    assert found["808 Blank Zone Ave"] == {"adu", "lot_split", "middle_housing", "underbuilt", "attic_or_second_story"}
    assert found["111 Corner Blvd"] == {"adu", "middle_housing", "add_bed_bath", "corner_or_alley"}
    assert found["222 Alley Garage"] == {
        "adu", "middle_housing", "garage_conversion", "underbuilt",
        "attic_or_second_story", "corner_or_alley",
    }
    assert "basement" not in found["333 Crawl St"]
    assert found["333 Crawl St"] == {"adu", "middle_housing", "underbuilt", "attic_or_second_story"}
    assert found["444 Duplex Dr"] == {"adu", "middle_housing", "underbuilt"}
    assert found["666 Room To Grow"] == {"adu", "middle_housing", "basement", "add_bed_bath", "attic_or_second_story"}
    for gone in ("303 Full House Rd", "404 Industrial Way", "909 Condo Way", "555 Retail Rd"):
        assert gone not in found
    assert _hit(result, "101 Big Lot Ave", "adu")["confidence"] == "high"
    assert "NR3" in _hit(result, "101 Big Lot Ave", "adu")["why"]
    assert _hit(result, "808 Blank Zone Ave", "adu")["confidence"] == "low"
    assert _hit(result, "444 Duplex Dr", "adu")["confidence"] == "medium"
    assert _hit(result, "666 Room To Grow", "basement")["confidence"] == "medium"
    assert _hit(result, "222 Alley Garage", "garage_conversion")["confidence"] == "medium"
    assert "Ada Owner" == next(i["prop"]["owner_name"] for i in result["flagged"] if i["prop"]["address"].startswith("101"))
    text = render_summary(result, cfg, SAMPLE, SEATTLE)
    assert "Screened 15 properties. 11 flagged." in text
    assert "Year Built" in text
    assert "DISCLAIMER" in text
    assert "not a zoning determination" in text.lower()
    assert "Lot Size SqFt -> lot_sqft" in text
    assert result["skipped"] == []
    print("seattle sample ok")


def test_blank_config_does_not_invent_zoning():
    cfg, result = _screen(SAMPLE, os.path.join(ROOT, "config", "my-market.yaml"))
    found = _ids(result)
    assert "adu" not in found.get("101 Big Lot Ave", set())
    assert "middle_housing" not in found.get("101 Big Lot Ave", set())
    assert "lot_split" not in found.get("101 Big Lot Ave", set())
    assert "basement" in found["101 Big Lot Ave"]
    reasons = " ".join(s["reason"] for s in result["skipped"])
    assert "min_parent_lot_sqft" in reasons
    text = render_summary(result, cfg, SAMPLE, "config/my-market.yaml")
    assert "no zoning codes" in text
    print("blank config ok")


def test_skipped_columns():
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "thin.csv")
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Address", "City", "State"])
        writer.writerow(["1 Main St", "Boise", "ID"])
    cfg, result = _screen(path, SEATTLE)
    skipped = {s["id"] for s in result["skipped"]}
    for op_id in ("basement", "garage_conversion", "underbuilt", "add_bed_bath",
                  "attic_or_second_story", "corner_or_alley", "lot_split", "adu", "middle_housing"):
        assert op_id in skipped, op_id
    assert result["flagged"] == []
    text = render_summary(result, cfg, path, SEATTLE)
    assert "Checks skipped" in text
    assert "basement" in text.lower()
    print("skipped columns ok")


def test_assessor_and_below_grade_headers():
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "assessor.csv")
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Situs Address", "PIN", "ZONE_CODE", "LOTSQFT", "BLDG_SQFT",
                         "BEDROOMS", "BATHROOMS", "SQFT_BSMT", "FIN_BSMT", "STORIES", "UNITS"])
        writer.writerow(["9 Parcel Rd", "999", "NR2", "8000", "1500", "3", "1", "1000", "200", "1", "1"])
    cfg, result = _screen(path, SEATTLE)
    assert len(result["flagged"]) == 1
    ids = _ids(result)["9 Parcel Rd"]
    assert "basement" in ids and "adu" in ids and "add_bed_bath" in ids
    assert _hit(result, "9 Parcel Rd", "basement")["confidence"] == "high"

    path2 = os.path.join(folder, "below.csv")
    with open(path2, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Address", "Property Type", "Zoning", "Lot Size SqFt", "Square Feet",
                         "Below Grade SqFt", "Below Grade Finished SqFt", "Stories", "Bedrooms", "Bathrooms", "Units"])
        writer.writerow(["4 Lower Ln", "Single Family", "NR3", "6000", "1800", "900", "900", "2", "3", "2", "1"])
    _, result2 = _screen(path2, SEATTLE)
    # Fully finished below-grade area is not a basement opportunity.
    assert "basement" not in _ids(result2).get("4 Lower Ln", set())
    print("assessor headers ok")


def test_acres_column_and_other_markets():
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "acres.csv")
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Property Address", "Mailing Address", "City", "Lot Size", "Zoning", "Property Type", "Units"])
        writer.writerow(["9 Real St", "1 Mail St", "Austin", "0.25", "SF-3", "Single Family", "1"])
    props, columns = load_csv(path)
    assert props[0]["address"] == "9 Real St"
    assert abs(props[0]["lot_sqft"] - 0.25 * 43560) < 1
    assert "Mailing Address" in columns["unmapped"]

    # Austin: 0.25 acres is about 10,890 sqft, so ADU, middle housing, and a split all hit.
    cfg = load_config(os.path.join(ROOT, "config", "examples", "austin-tx.yaml"))
    result = screen(props, cfg, columns)
    ids = _ids(result)["9 Real St"]
    assert ids == {"adu", "lot_split", "middle_housing"}

    # 4,000 sqft is big enough for two 1,800 sqft lots, but 20 ft of width
    # fails the 30 ft parent-width screen, and 4,000 is under the 5,750 unit minimum.
    narrow = dict(props[0])
    narrow["lot_sqft"] = 4000
    narrow["lot_width_ft"] = 20
    columns2 = dict(columns)
    columns2["present"] = set(columns["present"]) | {"lot_width_ft"}
    result = screen([narrow], cfg, columns2)
    assert result["flagged"] == []

    # Portland zone table: R5 at 2,700 sqft clears the ADU minimum (2,500)
    # and misses the fourplex minimum (3,000) and the split (6,000).
    pdx = load_config(os.path.join(ROOT, "config", "examples", "portland-or.yaml"))
    row = {"address": "5 Division", "property_type": "Single Family", "zoning": "R5",
           "lot_sqft": 2700, "units": 1, "building_sqft": 1200, "stories": 2, "bedrooms": 3, "bathrooms": 2}
    present = {"zoning", "lot_sqft", "building_sqft", "stories", "bedrooms", "bathrooms", "address"}
    result = screen([row], pdx, {"mapped": {}, "unmapped": [], "present": present})
    assert _ids(result)["5 Division"] == {"adu"}
    row["zoning"] = "R5z"
    result = screen([row], pdx, {"mapped": {}, "unmapped": [], "present": present})
    assert "middle_housing" not in _ids(result).get("5 Division", set())
    assert "adu" in _ids(result)["5 Division"]

    # Minneapolis: one ADU on a 1-family UN2 house; a 3-unit building is not an ADU candidate.
    mpls = load_config(os.path.join(ROOT, "config", "examples", "minneapolis-mn.yaml"))
    house = {"address": "8 Nicollet", "property_type": "Single Family", "zoning": "UN2",
             "lot_sqft": 5000, "units": 1, "building_sqft": 1400, "stories": 2, "bedrooms": 3, "bathrooms": 2}
    result = screen([house], mpls, {"mapped": {}, "unmapped": [], "present": present})
    assert "adu" in _ids(result)["8 Nicollet"]
    assert "side 3 ft" in _hit(result, "8 Nicollet", "adu")["verify"]
    assert "lot_split" in result["turned_off"]
    house["units"] = 3
    result = screen([house], mpls, {"mapped": {}, "unmapped": [], "present": present})
    assert "adu" not in _ids(result).get("8 Nicollet", set())
    print("markets ok")


def test_examples_load():
    folder = os.path.join(ROOT, "config", "examples")
    for name in os.listdir(folder):
        if name.endswith(".yaml"):
            cfg = load_config(os.path.join(folder, name))
            assert cfg["kind"] == "example"
            assert cfg["market"]["state"]
            assert cfg["sources"]
    print("examples load ok")


if __name__ == "__main__":
    test_codes()
    test_sample_seattle()
    test_blank_config_does_not_invent_zoning()
    test_skipped_columns()
    test_assessor_and_below_grade_headers()
    test_acres_column_and_other_markets()
    test_examples_load()
    print("ok")
