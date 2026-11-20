# Blank templates (copy, fill in, keep private)

- suppress.csv: your do-not-contact list. phone / address / owner (one is enough), date, channel
  (all, mail, call, sms), reason. Save filled copies in the suppress/ folder: every run reads it.
- dnc_scrub.csv: the result of YOUR DNC scrub. dnc = Y (on a list) or N (clean), scrub_date
  (YYYY-MM-DD), lists_checked must cover federal, state and internal, e.g. "federal; state:NC none; internal",
  scrubbed_by (the person or company who ran the scrub) and vendor (the DNC service used, or "self (own SAN)").
  A row missing lists_checked parts, scrubbed_by or vendor counts as an incomplete scrub.
- call_review.csv: your decision per number or owner_key: call_eligibility = blocked or
  reviewed_for_campaign, reviewed_by, review_date, hours_verified (Y when you checked the calling
  hours yourself; required when call_window_check says VERIFY). Pass it with --call-review (the pipeline also
  reads out/state/call_review.csv).
- consent.csv: texting consent. Every column except review_status / revoked_* is required:
  consented_to = your business name exactly, purpose, method, consent_date, consent_source,
  consent_evidence (where the proof is kept), confirmed = Y. When someone withdraws consent,
  fill revoked_date and revoked_how: the kit drops the row and adds the number to your suppression list.
- manual_requests.csv: do-not-contact requests your employees receive by phone, letter, email or in person.
  Save it in suppress/ (or run scripts/suppression.py add). Rows are never removed.
