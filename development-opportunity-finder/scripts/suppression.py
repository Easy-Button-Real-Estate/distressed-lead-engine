"""Do-not-contact (suppression) list, kept across runs and applied to every list.

File format (CSV): phone, address, owner, date, channel, reason
  phone    a number that must not be called or texted (any format)
  address  a mailing or property address that must not get mail
  owner    an owner name that must not be contacted
  date     when it was added (YYYY-MM-DD)
  channel  all | mail | call | sms   (blank = all)
  reason   free text ("replied STOP", "asked not to be called", "deceased", ...)

Fill in phone, address or owner (one is enough). Phones are matched on their 10 digits, so
(919) 555-0134, 9195550134 and +19195550134 are the same number. Addresses are normalised
(123 Main Street = 123 MAIN ST; ZIP+4 cut to 5 digits).

Drop folder: every CSV in the project's suppress/ folder is read on every run, so you can just
save your latest do-not-contact export there. START_HERE warns when the newest file in it is
more than 7 days old.

Retention: keep this list (and the dates) for as long as you market, and at least 5 years
(the federal Telemarketing Sales Rule record-keeping period). The pipeline keeps a master copy in
<output>/state/suppression.csv: every --suppress file and every STOP reply you pass
(--stop-replies) is merged into it, and it is applied on every later run, even if you
forget the flag. Suppression is cumulative: every run adds to the master list and nothing is
ever taken off it by the kit (a run that would leave fewer rows than before stops with an error).
Never remove a suppression row. If someone later asks to hear from you again, keep the row and
handle it with your counsel.

Where requests come from: import the latest opt-outs and do-not-contact requests from every system
where your team communicates with these owners (CRM, dialer, texting tool, email, mail house). Log a manual
request (a call, letter, email or in-person "don't contact me" an employee received) with:
  PY scripts/suppression.py add --phone "(919) 555-0134" --owner "Pat Lee" --reason "asked on a call" --by "Sam"
It is appended to suppress/manual_requests.csv (append only; nothing is ever deleted).
"""
import datetime as dt, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import clean_phone, norm, norm_address, read_rows, write_rows  # noqa: E402
import glob, time

FIELDS = ["phone", "address", "owner", "date", "channel", "reason"]
OPT_OUT_SENTENCE = ("Import the latest opt-outs and do-not-contact requests from every system where your team communicates "
                    "with these owners.")
MANUAL_SENTENCE = ("Also log manual requests your employees receive (a call, letter, email or in person): add them to "
                   "suppress/manual_requests.csv or run scripts/suppression.py add.")
MANUAL_FILE = "manual_requests.csv"
MANUAL_FIELDS = FIELDS + ["logged_by", "logged_at"]
CHANNELS = ("all", "mail", "call", "sms")


def _low(r):
    return {str(k).strip().lower(): ("" if v is None else str(v).strip()) for k, v in r.items() if k}


def load(path, default_reason="", default_channel="all"):
    out = []
    if not path or not os.path.exists(path):
        return out
    for r in read_rows(path):
        low = _low(r)
        ch = (low.get("channel") or default_channel).lower()
        ch = ch if ch in CHANNELS else ("sms" if "text" in ch or "sms" in ch else "call" if "call" in ch or "phone" in ch
                                        else "mail" if "mail" in ch else "all")
        row = {"phone": clean_phone(low.get("phone") or low.get("phone_number") or low.get("number")),
               "address": low.get("address") or low.get("mail_address") or low.get("mailing_address") or "",
               "owner": low.get("owner") or low.get("name") or "",
               "date": low.get("date") or low.get("added") or dt.date.today().isoformat(),
               "channel": ch, "reason": low.get("reason") or default_reason}
        if row["phone"] or norm(row["address"]) or norm(row["owner"]):
            out.append(row)
    return out


DROP_STALE_DAYS = 7


def drop_folder(folder):
    """CSV files in the suppress/ drop folder (newest first) and the age in days of the newest file that has rows."""
    if not folder or not os.path.isdir(folder):
        return [], None
    files = sorted((p for p in glob.glob(os.path.join(folder, "*.csv")) if os.path.isfile(p)), key=os.path.getmtime, reverse=True)
    with_rows = [p for p in files if load(p)]
    age = (time.time() - os.path.getmtime(with_rows[0])) / 86400 if with_rows else None
    return with_rows, age


def merge(master, extra=(), stop_replies=None, persist=True):
    """Merge --suppress files and STOP replies into the master list; save it (unless persist=False)."""
    rows = load(master)
    for p in extra or ():
        if p and not os.path.exists(p):
            raise SystemExit(f"Suppression file not found: {p}")
        rows += load(p)
    if stop_replies:
        if not os.path.exists(stop_replies):
            raise SystemExit(f"STOP replies file not found: {stop_replies}")
        rows += load(stop_replies, default_reason="replied STOP", default_channel="all")
    seen, out = set(), []
    for r in rows:
        k = (r["phone"], norm_address(r["address"]), norm(r["owner"]), r["channel"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    if persist and master:
        before = len(load(master))
        if len(out) < before:  # cumulative: never write a shorter list than the one on disk
            raise SystemExit(f"Refusing to shrink the suppression list ({before} -> {len(out)} rows). Nothing was changed.")
        write_rows(master, out, FIELDS)
    return out


def add(folder, phone="", address="", owner="", channel="all", reason="", by=""):
    """Append one manual do-not-contact request to <folder>/manual_requests.csv (append only)."""
    import csv
    if not (clean_phone(phone) or norm(address) or norm(owner)):
        raise SystemExit("Give at least one of --phone, --address or --owner.")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, MANUAL_FILE)
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    now = dt.datetime.now().isoformat(timespec="seconds")
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANUAL_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"phone": clean_phone(phone) or "", "address": address, "owner": owner, "date": now[:10],
                    "channel": channel if channel in CHANNELS else "all", "reason": reason or "manual request", "logged_by": by,
                    "logged_at": now})
    return path


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Add a manual do-not-contact request (append only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("add")
    a_.add_argument("--phone", default=""); a_.add_argument("--address", default=""); a_.add_argument("--owner", default="")
    a_.add_argument("--channel", default="all", choices=CHANNELS); a_.add_argument("--reason", default="")
    a_.add_argument("--by", default="", help="who received the request")
    a_.add_argument("--folder", help="default: the kit's suppress/ folder")
    a = ap.parse_args(argv)
    folder = a.folder or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "suppress")
    path = add(folder, a.phone, a.address, a.owner, a.channel, a.reason, a.by)
    print(f"Added to {path}. It applies to every list on the next run. Rows are never removed.")
    return path


class Suppression:
    def __init__(self, rows):
        self.rows = rows or []
        self.phones = {}
        self.owners, self.addresses = [], []
        for r in self.rows:
            if r["phone"]:
                self.phones.setdefault(r["phone"], set()).add(r["channel"])
            if norm(r["owner"]):
                self.owners.append((norm(r["owner"]), r["channel"], r.get("reason", "")))
            if len(norm(r["address"])) >= 6:
                self.addresses.append((norm_address(r["address"]), r["channel"], r.get("reason", "")))

    def __len__(self):
        return len(self.rows)

    @staticmethod
    def _hit(ch, channel):
        return ch == "all" or ch == channel or channel == "any"

    def phone(self, p, channel):
        return any(self._hit(c, channel) for c in self.phones.get(clean_phone(p), ()))

    def owner(self, owner, addresses, channel):
        """Reason string if this owner (by name or any of its addresses) is suppressed for the channel."""
        no = norm(owner)
        for n, ch, why in self.owners:
            if n and n == no and self._hit(ch, channel):
                return why or "on your suppression list"
        for a in addresses:
            na = norm_address(a)
            if len(norm(a)) < 6:
                continue
            for n, ch, why in self.addresses:
                # whole-word prefix match: "123 main st" matches "123 main st raleigh nc 27606", not "1123 main st"
                if (na == n or na.startswith(n + " ") or n.startswith(na + " ")) and self._hit(ch, channel):
                    return why or "address on your suppression list"
        return ""


if __name__ == "__main__":
    main()
