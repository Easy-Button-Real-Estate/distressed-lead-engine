"""Generic "public records search page" source - works for any county portal that returns an HTML
results table (court case search, recorder/clerk document search, sheriff sale lists...).

YAML (all keys optional except url):
  type: search_page
  template: tyler_odyssey | landmark_web | html_table   # pulls defaults from counties/templates/<name>.yaml
  url: "https://portal.example.gov/search?type={case_type}&from={from}&to={to}&page={page}"
  method: GET | POST
  form: {StartDate: "{from}", EndDate: "{to}", DocType: "{doc_type}"}     # POST body, same placeholders
  params: {case_type: "PR", doc_type: "NOD"}                               # your own placeholders
  date_range: {lookback_days: 7, format: "%m/%d/%Y"}                       # fills {from} {to}
  parse:
    rows: "table#results tbody tr"      # CSS selector for one result row
    header: "table#results thead th"    # optional: column names from header cells
    columns: {CaseNumber: "td:nth-of-type(1)", Filed: "td:nth-of-type(3)"}  # or explicit CSS per field
    link: "a"                           # optional: first link in row -> source_url
    skip_if_contains: "No records"      # optional
  pagination: {start: 1, max_pages: 5, step: 1}   # {page} placeholder; stops on an empty page
     # or {next: "a.next"}  to follow a Next link
  provider: brightdata | brightdata_browser | scraperapi | direct | [list]   # default chain
  render_js: false
  delay_seconds: 3                     # be polite: wait between pages
Placeholders: {from} {to} {page} {offset} {county} {state} plus anything in params.
"""
import os
from datetime import date, timedelta
from urllib.parse import urljoin
import yaml
from bs4 import BeautifulSoup
from ..providers import fetch_any

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "counties", "templates")


def _deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def resolve(src):
    if src.get("template"):
        path = os.path.join(TEMPLATE_DIR, src["template"] + ".yaml")
        tpl = yaml.safe_load(open(path)) or {}
        tpl.pop("notes", None)
        src = _deep_merge(tpl, src)
    return src


class _SafeDict(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def _fill(s, vals):
    return s.format_map(_SafeDict(vals)) if isinstance(s, str) else s


def parse_html(html, spec, base_url=""):
    soup = BeautifulSoup(html, "html.parser")
    if spec.get("skip_if_contains") and spec["skip_if_contains"] in soup.get_text(" "):
        return []
    headers = [h.get_text(" ", strip=True) for h in soup.select(spec["header"])] if spec.get("header") else []
    out = []
    for tr in soup.select(spec.get("rows", "table tr")):
        if spec.get("columns"):
            row = {}
            for k, sel in spec["columns"].items():
                el = tr.select_one(sel)
                row[k] = el.get_text(" ", strip=True) if el else ""
        else:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td"])]
            if not cells:
                continue        # header row
            names = headers if len(headers) == len(cells) else [f"col{i+1}" for i in range(len(cells))]
            row = dict(zip(names, cells))
        if not any(row.values()):
            continue
        a = tr.select_one(spec.get("link", "a[href]"))
        if a and a.get("href"):
            row["url"] = urljoin(base_url, a["href"])
        out.append(row)
    return out


def run(src, fetch=fetch_any):
    src = resolve(src)
    dr = src.get("date_range", {})
    fmt = dr.get("format", "%m/%d/%Y")
    to = date.today()
    frm = to - timedelta(days=int(dr.get("lookback_days", src.get("lookback_days", 7))))
    vals = {"from": frm.strftime(fmt), "to": to.strftime(fmt), "county": src.get("county", ""),
            "state": src.get("state", "")}
    vals.update(src.get("params", {}))
    pg = src.get("pagination", {}) or {}
    page, step, max_pages = int(pg.get("start", 1)), int(pg.get("step", 1)), int(pg.get("max_pages", 1))
    per = int(pg.get("page_size", 0) or 0)
    url = _fill(src["url"], {**vals, "page": page, "offset": 0})
    rows, seen = [], 0
    delay = float(src.get("delay_seconds", os.getenv("FETCH_DELAY_SECONDS", 2)))
    while url and seen < max_pages:
        form = {k: _fill(v, {**vals, "page": page, "offset": seen * per}) for k, v in (src.get("form") or {}).items()} or None
        html = fetch(url, src.get("method", "GET"), form, None, provider=src.get("provider"),
                     render_js=src.get("render_js", False), delay=delay)
        got = parse_html(html, src.get("parse", {}), url)
        rows += got
        seen += 1
        if not got:
            break
        if pg.get("next"):
            nxt = BeautifulSoup(html, "html.parser").select_one(pg["next"])
            url = urljoin(url, nxt["href"]) if nxt and nxt.get("href") else None
        elif "{page}" in src["url"] or "{offset}" in src["url"] or any("{page}" in str(v) or "{offset}" in str(v) for v in (src.get("form") or {}).values()):
            page += step
            url = _fill(src["url"], {**vals, "page": page, "offset": seen * per})
        else:
            break
    return rows
