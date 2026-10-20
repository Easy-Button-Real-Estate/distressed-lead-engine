"""Scraper providers. Pick one with SCRAPER_PROVIDER (or per source: `provider:` in the county YAML).

  direct            plain requests (default, free)
  brightdata        Bright Data Web Unlocker API  POST https://api.brightdata.com/request
                    env BRIGHTDATA_API_KEY, BRIGHTDATA_UNLOCKER_ZONE
                    docs https://docs.brightdata.com/scraping-automation/web-unlocker/send-your-first-request
  brightdata_browser Bright Data Browser API (Scraping Browser) for JavaScript-heavy search portals
                    env BRIGHTDATA_BROWSER_WSS = wss://brd-customer-<id>-zone-<zone>:<password>@brd.superproxy.io:9222
                    needs `pip install playwright` (no local browser download needed)
                    docs https://docs.brightdata.com/scraping-automation/scraping-browser/introduction
  scraperapi        GET https://api.scraperapi.com/?api_key=...&url=...   env SCRAPERAPI_KEY   docs https://docs.scraperapi.com
  scrapingbee       GET https://app.scrapingbee.com/api/v1/?api_key=...&url=...  env SCRAPINGBEE_API_KEY  docs https://www.scrapingbee.com/documentation/
  zenrows           GET https://api.zenrows.com/v1/?apikey=...&url=...   env ZENROWS_API_KEY   docs https://docs.zenrows.com

Default chain when SCRAPER_PROVIDER is unset: brightdata (if keyed) -> scraperapi (if keyed) -> direct.
Every provider returns the page body as text. Keys come only from the environment (.env or GitHub secrets).
"""
import os, time
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; distressed-lead-engine/0.2; public records research)"}


def default_chain():
    """Order to try when no provider is forced: Bright Data (if keyed) -> ScraperAPI (if keyed) -> direct."""
    forced = os.getenv("SCRAPER_PROVIDER")
    if forced:
        return [p.strip().lower() for p in forced.split(",") if p.strip()]
    chain = []
    if os.getenv("BRIGHTDATA_API_KEY") and os.getenv("BRIGHTDATA_UNLOCKER_ZONE"):
        chain.append("brightdata")
    if os.getenv("SCRAPERAPI_KEY"):
        chain.append("scraperapi")
    return chain + ["direct"]


def fetch_any(url, method="GET", data=None, headers=None, provider=None, render_js=False, delay=None):
    """Try each provider in the chain until one works. `provider` (from the county YAML) may be a name
    or a list. `delay` = polite seconds to wait before the request (default env FETCH_DELAY_SECONDS or 2)."""
    chain = provider if isinstance(provider, list) else ([provider] if provider else default_chain())
    time.sleep(float(delay if delay is not None else os.getenv("FETCH_DELAY_SECONDS", 2)))
    errs = []
    for p in chain:
        try:
            return Fetcher(p, render_js).fetch(url, method, data, headers)
        except Exception as e:   # noqa: BLE001 - fall through to next provider
            errs.append(f"{p}: {str(e)[:120]}")
    raise RuntimeError("all providers failed -> " + " | ".join(errs))


class Fetcher:
    def __init__(self, provider=None, render_js=False):
        self.provider = (provider or os.getenv("SCRAPER_PROVIDER") or "direct").lower()
        self.render_js = render_js
        self.session = requests.Session()        # keeps cookies (disclaimers) for direct mode
        self.session.headers.update(UA)

    # --- one call: fetch(url, method, data) -> text ---------------------------------
    def fetch(self, url, method="GET", data=None, headers=None):
        fn = getattr(self, "_" + self.provider, None)
        if fn is None:
            raise ValueError(f"unknown SCRAPER_PROVIDER '{self.provider}'")
        last = None
        for attempt in range(3):
            try:
                return fn(url, method.upper(), data, headers or {})
            except requests.RequestException as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise last

    def _direct(self, url, method, data, headers):
        r = self.session.request(method, url, data=data, headers=headers, timeout=60)
        r.raise_for_status()
        return r.text

    def _brightdata(self, url, method, data, headers):
        body = {"zone": _need("BRIGHTDATA_UNLOCKER_ZONE"), "url": url, "format": "raw"}
        if method == "POST":
            body["method"] = "POST"
            if data is not None:
                body["body"] = data if isinstance(data, str) else requests.models.RequestEncodingMixin._encode_params(data)
        r = requests.post("https://api.brightdata.com/request", json=body, timeout=120,
                          headers={"Authorization": f"Bearer {_need('BRIGHTDATA_API_KEY')}"})
        r.raise_for_status()
        return r.text

    def _brightdata_browser(self, url, method, data, headers):
        """Hosted Chrome via Bright Data Browser API (Playwright over CDP). For POST search forms,
        `data` keys are input names: each is filled, then the form is submitted (Enter)."""
        from playwright.sync_api import sync_playwright   # pip install playwright
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(_need("BRIGHTDATA_BROWSER_WSS"))
            try:
                page = b.new_page()
                page.goto(url, timeout=120000)
                if method == "POST" and isinstance(data, dict) and data:
                    last = None
                    for k, v in data.items():
                        last = f"[name='{k}'], #{k}"
                        page.fill(last, str(v))
                    page.press(last, "Enter")
                    page.wait_for_load_state("networkidle", timeout=120000)
                return page.content()
            finally:
                b.close()

    def _scraperapi(self, url, method, data, headers):
        params = {"api_key": _need("SCRAPERAPI_KEY"), "url": url}
        if self.render_js:
            params["render"] = "true"
        r = requests.request(method, "https://api.scraperapi.com/", params=params, data=data, timeout=120)
        r.raise_for_status()
        return r.text

    def _scrapingbee(self, url, method, data, headers):
        params = {"api_key": _need("SCRAPINGBEE_API_KEY"), "url": url,
                  "render_js": "true" if self.render_js else "false"}
        r = requests.request(method, "https://app.scrapingbee.com/api/v1/", params=params, data=data, timeout=120)
        r.raise_for_status()
        return r.text

    def _zenrows(self, url, method, data, headers):
        params = {"apikey": _need("ZENROWS_API_KEY"), "url": url}
        if self.render_js:
            params["js_render"] = "true"
        r = requests.request(method, "https://api.zenrows.com/v1/", params=params, data=data, timeout=120)
        r.raise_for_status()
        return r.text


def _need(name):
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"{name} is not set (add it to .env or GitHub secrets)")
    return v


def brightdata_serp(query, zone=None):
    """Bright Data SERP API: Google results as JSON (handy for finding obituaries / legal notices).
    Same /request endpoint with a SERP zone (env BRIGHTDATA_SERP_ZONE). brd_json=1 asks for parsed JSON.
    docs https://docs.brightdata.com/scraping-automation/serp-api/introduction"""
    url = "https://www.google.com/search?" + requests.compat.urlencode({"q": query, "brd_json": 1})
    r = requests.post("https://api.brightdata.com/request", timeout=120,
                      headers={"Authorization": f"Bearer {_need('BRIGHTDATA_API_KEY')}"},
                      json={"zone": zone or _need("BRIGHTDATA_SERP_ZONE"), "url": url, "format": "raw"})
    r.raise_for_status()
    return r.json()
