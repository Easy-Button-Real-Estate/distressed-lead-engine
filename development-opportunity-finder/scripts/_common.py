"""Small helpers shared by the pipeline scripts (standard library only)."""
import csv, datetime as dt, os, re


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# Canonical privacy paragraph: used word for word in SECURITY.md, SKILL.md, SETUP.md, CLAUDE.md, the starters,
# COMPLIANCE.md and START_HERE.md (a test checks every one).
PRIVACY_PARAGRAPH = ("The kit's local scripts store and process owner data in your kit folder and do not send owner data to "
                     "public map servers. However, when Claude Code reads file contents or includes them in prompts, that "
                     "information may be transmitted to Anthropic for processing under your Claude plan or API account terms "
                     "and settings. Only use this workflow with data you are authorized to share with that service. Keep API "
                     "keys in the local .env file and never paste them into chat.")
SKIPTRACE_LINE = ("Bring skip-trace results back through the kit before dialing. Never load the vendor file straight into your dialer.")
DNC_NOT_CONSENT = ("A DNC scrub is not consent, and consent does not override other restrictions (calling hours, do-not-contact "
                   "requests, state rules, call-frequency limits). 10DLC registration is a separate requirement: it is not "
                   "consent, and consent does not replace it.")


def read_rows(path):
    """Read a CSV into a list of dicts. Tries UTF-8 then Latin-1."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(path, newline="", encoding=enc) as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise SystemExit("Could not read " + path)


def write_rows(path, rows, fields=None):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    if fields is None:
        fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    return path


def pick(headers, aliases):
    """Return the first header whose normalized name is in aliases (in alias order)."""
    m = {norm(h): h for h in headers}
    for a in aliases:
        if norm(a) in m:
            return m[norm(a)]
    return None


def num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("$", "").replace("%", "")
    if s == "" or s.lower() in ("nan", "none", "null", "n/a", "na", "-", "unknown"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(v):
    s = str(v or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{12,13}", s):  # ArcGIS epoch ms
        return dt.datetime.fromtimestamp(int(s) / 1000, dt.timezone.utc).date()
    s = s.split("T")[0].split(" ")[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m-%d-%Y", "%Y%m%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def quantile(vals, q):
    v = sorted(vals)
    if not v:
        return None
    pos = (len(v) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def yes(v):
    s = str(v or "").strip().lower()
    if s in ("y", "yes", "true", "t", "1", "x"):
        return True
    if s in ("n", "no", "false", "f", "0"):
        return False
    return None


def clean_phone(v):
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else ""


ENTITY = re.compile(r"\b(llc|l l c|inc|corp|corporation|co|company|ltd|lp|llp|pllc|partners|partnership|holdings|"
                    r"trust|trustee|bank|church|association|assn|properties|investments|group|enterprises|estate)\b", re.I)


def split_owner(name):
    """Best-effort split of an assessor owner string into first / last.

    Entities (LLC, trust, estate...) are returned as-is in `entity` with no first/last.
    "SMITH JOHN A" (assessor order) and "John A Smith" are both handled; we guess
    assessor order when the whole string is upper case.
    """
    n = re.sub(r"\s+", " ", str(name or "").replace(",", " ")).strip()
    if not n:
        return {"first": "", "last": "", "entity": ""}
    if ENTITY.search(n):
        return {"first": "", "last": "", "entity": n}
    n = re.split(r"\s(?:&|and)\s", n, maxsplit=1, flags=re.I)[0].strip()
    parts = n.split(" ")
    if len(parts) == 1:
        return {"first": "", "last": parts[0].title(), "entity": ""}
    if str(name).isupper():
        return {"first": parts[1].title(), "last": parts[0].title(), "entity": ""}
    return {"first": parts[0].title(), "last": parts[-1].title(), "entity": ""}


# ---- network helpers -------------------------------------------------------
# Fresh Macs (python.org installs) often have no root certificates for Python, which
# makes every HTTPS call fail with CERTIFICATE_VERIFY_FAILED. certifi ships them.
SOURCE_UNAVAILABLE = "source unavailable; scoring continued without this factor"
_SSL = None


def ssl_context():
    global _SSL
    if _SSL is None:
        import ssl
        try:
            import certifi
            _SSL = ssl.create_default_context(cafile=certifi.where())
        except Exception:  # certifi missing: fall back to the system store
            _SSL = ssl.create_default_context()
    return _SSL


def urlopen(req, timeout=60):
    """urllib.request.urlopen with certifi's certificates (looked up at call time so tests can fake it)."""
    import urllib.request
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())


def friendly_error(e):
    """One short line instead of a traceback."""
    s = str(e).strip().splitlines()[0] if str(e).strip() else e.__class__.__name__
    if "CERTIFICATE_VERIFY_FAILED" in s:
        return "certificate check failed (run start-mac.command again, or: .venv/bin/python -m pip install certifi)"
    if "timed out" in s.lower():
        return "timed out"
    return s[:120]


# --- address normalisation (suppression matching) ---
_SUFFIX = {"street": "st", "str": "st", "avenue": "ave", "av": "ave", "road": "rd", "drive": "dr", "lane": "ln",
           "court": "ct", "circle": "cir", "boulevard": "blvd", "place": "pl", "terrace": "ter", "highway": "hwy",
           "parkway": "pkwy", "trail": "trl", "way": "way", "square": "sq", "point": "pt", "crossing": "xing",
           "north": "n", "south": "s", "east": "e", "west": "w", "northeast": "ne", "northwest": "nw",
           "southeast": "se", "southwest": "sw", "apartment": "apt", "suite": "ste", "unit": "unit",
           "post office box": "po box", "p o box": "po box", "pobox": "po box"}


def norm_address(s):
    """'123 Main Street, Apt. 4' and '123 MAIN ST APT 4' -> '123 main st apt 4'. ZIP+4 is cut to 5 digits."""
    t = re.sub(r"[.,#]", " ", str(s or "").lower())
    t = re.sub(r"\b(\d{5})-\d{4}\b", r"\1", t)
    t = re.sub(r"\bp\s*o\s*box\b", "po box", t)
    words = [w for w in re.split(r"\s+", t) if w]
    words = [_SUFFIX.get(w, w) for w in words]
    return " ".join(words)
