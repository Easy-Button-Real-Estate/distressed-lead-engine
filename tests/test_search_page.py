"""Offline tests for the provider chain and the generic search_page source (no network)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dle import providers
import importlib
sp = importlib.import_module("dle.sources.search_page")

PAGE = """<table id=r><thead><tr><th>Case</th><th>Filed</th><th>Address</th></tr></thead><tbody>
<tr><td><a href="/case/{n}1">PR-{n}1</a></td><td>10/18/2026</td><td>1 Main St</td></tr>
<tr><td><a href="/case/{n}2">PR-{n}2</a></td><td>10/19/2026</td><td>2 Oak Ave</td></tr></tbody></table>"""


def test_parse_header_and_links():
    rows = sp.parse_html(PAGE.format(n=1), {"rows": "#r tbody tr", "header": "#r thead th"}, "https://x.gov/s")
    assert rows[0]["Case"] == "PR-11" and rows[1]["Address"] == "2 Oak Ave"
    assert rows[0]["url"] == "https://x.gov/case/11"


def test_pagination_and_placeholders():
    calls = []

    def fake(url, method, data, headers, **kw):
        calls.append((url, data))
        page = int(url.split("page=")[1])
        return PAGE.format(n=page) if page <= 2 else "<table id=r><tbody></tbody></table>"

    src = {"url": "https://x.gov/s?type={ct}&from={from}&page={page}", "params": {"ct": "PR"},
           "parse": {"rows": "#r tbody tr", "header": "#r thead th"},
           "pagination": {"start": 1, "max_pages": 5}, "delay_seconds": 0}
    rows = sp.run(src, fetch=fake)
    assert len(rows) == 4 and len(calls) == 3 and "type=PR" in calls[0][0] and "{from}" not in calls[0][0]


def test_templates_load():
    for t in ("tyler_odyssey", "landmark_web", "html_table"):
        r = sp.resolve({"template": t, "url": "https://x"})
        assert r["url"] == "https://x" and "parse" in r and "notes" not in r


def test_provider_chain():
    for k in ("SCRAPER_PROVIDER", "BRIGHTDATA_API_KEY", "BRIGHTDATA_UNLOCKER_ZONE", "SCRAPERAPI_KEY"):
        os.environ.pop(k, None)
    assert providers.default_chain() == ["direct"]
    os.environ.update(BRIGHTDATA_API_KEY="x", BRIGHTDATA_UNLOCKER_ZONE="z", SCRAPERAPI_KEY="y")
    assert providers.default_chain() == ["brightdata", "scraperapi", "direct"]
    os.environ["SCRAPER_PROVIDER"] = "scraperapi,direct"
    assert providers.default_chain() == ["scraperapi", "direct"]
    for k in ("SCRAPER_PROVIDER", "BRIGHTDATA_API_KEY", "BRIGHTDATA_UNLOCKER_ZONE", "SCRAPERAPI_KEY"):
        os.environ.pop(k, None)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
    print("ok")
