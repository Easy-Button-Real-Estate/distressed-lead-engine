# Blank templates (copy, fill in, keep private)

- suppress.csv: your do-not-contact list. phone / address / owner (one is enough), date, channel
  (all, mail, call, sms), reason. Bring exports in with scripts/suppression.py import <file> --export-date
  YYYY-MM-DD (the date the system generated it): every run reads the suppress/ folder.
- dnc_scrub.csv: the result of YOUR DNC scrub. dnc = Y (on a list) or N (clean), scrub_date
  (YYYY-MM-DD), lists_checked must cover federal, state and internal, e.g. "federal; state:NC none; internal",
  scrubbed_by (the person or company who ran the scrub) and vendor (the DNC service used, or "self (own SAN)").
  A row missing lists_checked parts, scrubbed_by or vendor counts as an incomplete scrub.
- call_review.csv: your decision per number or owner_key: call_eligibility = blocked or
  reviewed_for_campaign, reviewed_by, review_date, hours_verified (Y when you checked the person's
  local time and the state's calling hours yourself; required for every reviewed_for_campaign row, because
  call_window is only an estimated window). Pass it with --call-review (the pipeline also
  reads out/state/call_review.csv).
- consent.csv: texting consent. Every column except review_status / revoked_* is required:
  consented_to = your business name exactly, purpose, method, consent_date, consent_source,
  consent_evidence (where the proof is kept), confirmed = Y. When someone withdraws consent,
  fill revoked_date and revoked_how: the kit drops the row and adds the number to your suppression list.
- manual_requests.csv: do-not-contact requests your employees receive by phone, letter, email or in person.
  Save it in suppress/ (or run scripts/suppression.py add). Rows are never removed.

Notes:
- A DNC scrub is not consent, and consent does not override other restrictions (calling hours, do-not-contact requests, state rules, call-frequency limits). 10DLC registration is a separate requirement: it is not consent, and consent does not replace it.
- Bring skip-trace results back through the kit before dialing. Never load the vendor file straight into your dialer.
