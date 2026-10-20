"""Offline tests: python -m pytest -q  (or python tests/test_core.py)"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dle.core import lead, merge, Store, norm_address, owner_type
from dle.integrations.llc import pierce
from dle.integrations.outreach import write_copy


def test_all():
    a = lead("King", "WA", "code_violation", "123 Main Street", "Seattle", "98101", event_date="2026-10-18")
    b = lead("King", "WA", "fire", "123 MAIN ST", "Seattle", "", event_date="2026-10-19")
    c = lead("King", "WA", "tax_foreclosure", "", parcel_id="0121059036", owner_name="ACME HOLDINGS LLC")
    rows = merge([a, b, c])
    assert len(rows) == 2
    stacked = [r for r in rows if r["list_count"] == 2][0]
    assert stacked["list_types"] == "code_violation;fire" and stacked["event_date"] == "2026-10-19"
    assert stacked["score"] > 35
    assert norm_address("12035 Aurora Avenue North") == "12035 aurora ave n"
    assert owner_type("ACME HOLDINGS LLC") == "entity" and owner_type("ESTATE OF JOHN DOE") == "estate"
    os.environ.pop("GOVFILES_API_KEY", None)
    pierce(rows, "WA")
    assert "ccfs.sos.wa.gov" in [r for r in rows if r["owner_type"] == "entity"][0]["llc_principals"]
    db = os.path.join(tempfile.mkdtemp(), "t.sqlite")
    s = Store(db); s.mark(rows)
    again = merge([a, b, c]); Store(db).mark(again)
    assert all(r["is_new"] == "" for r in again)
    write_copy(rows[0], {}); assert "STOP" in rows[0]["marketing_sms"]
    print("ok")


if __name__ == "__main__":
    test_all()
