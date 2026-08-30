# Data Issues Report

Found by running `scripts/merge_pipeline.py` against the 3 source files and inspecting
the resulting `consultbae.db`. 102 raw rows across 3 files resolved to 60 unique people.

## 1. No shared primary key across sources
- `source1_naukri_applicants.csv` has email + phone.
- `source2_gig_workers.csv` has email only (no phone column at all).
- `source3_cbnexus_contacts.csv` has phone only (no email column at all).
- **Fix:** built entity resolution as a graph/union-find over normalized (email, phone)
  pairs rather than matching on name. Name is display-only, never a merge key.

## 2. Name alone is not a safe identity key (the "same name, different person" trap)
- There are **three separate "Arjun Mehta" records** in the raw data:
  `arjun.mehta9@example.in` / phone `9000000131` (naukri + cbnexus),
  `arjun.mehta77@mailtest.example.org` (gig_workers only, no phone),
  and phone `9000000272` (cbnexus only, no email).
  None of these three share an email or phone with each other, so they are kept as
  **three distinct people**, not merged. A naive "match on name" approach would have
  wrongly collapsed them into one.
- **Fix:** identity resolution never merges on name alone.

## 3. Duplicate applicants (same person applied twice)
- **Nikhil Chopra**, phone `9000000103`, appears twice in `source1` under two different
  emails (`nikhil.chopra70@example.com` and `alt.nikhil.chopra70@example.com`) with
  identical skills and applied date — a duplicate/repeat submission.
- **Rohit Verma**, email `rohit.verma13@mailtest.example.org`, appears twice under two
  name spellings ("R. Verma" and "Rohit Verma") with identical data — same submission
  duplicated.
- **Fix:** these collapse into one `person` row via shared identifier; display name
  logic picks the fuller name string ("Rohit Verma" over "R. Verma").

## 4. Malformed rows in `source2_gig_workers.csv`
- One completely blank row (`,,,,,`).
- One row with columns shifted left by one: the `skill_tags` value
  (`"react, javascript, mysql"`) is sitting in the `email_id` column, and the real
  email is missing — this row duplicates an existing Isha Chopra record with corrupted
  columns.
- **Fix:** both rows are detected (blank name+email, or email field with no `@`) and
  dropped during load rather than silently ingested as garbage.

## 5. Repeated header row mid-file in `source3_cbnexus_contacts.csv`
- The header row (`Name,Phone Number,City,Verified,Projects Completed`) appears a
  second time partway through the file, which — if not filtered — would be ingested
  as a fake "person" named "Name".
- **Fix:** rows where `Name == "Name"` are skipped.

## 6. Inconsistent formatting across nearly every field
- **Phone numbers:** mixed `+91` prefix, leading `0`, `91` prefix, plain 10-digit, no
  separators. Normalized to last 10 digits.
- **Email casing:** `ISHA.CHOPRA95@MAILTEST.EXAMPLE.ORG` vs `isha.chopra95@...` for the
  same person. Normalized to lowercase before matching (without this, the merge for
  Isha Chopra would have failed).
- **City names:** `Bengaluru` / `bangalore` / `BANGALORE`; `Gurgaon` / `gurugram` /
  `GURUGRAM`; `New Delhi` / `new delhi` / `Delhi NCR`; trailing whitespace (`"Noida "`).
  Normalized to lowercase + trimmed, with `Gurgaon→Gurugram` and `Bangalore→Bengaluru`
  treated as the same city (post-rename aliases). `"Delhi NCR"` is bucketed with Delhi
  but flagged as genuinely ambiguous — it could mean Delhi, Noida, or Gurugram, and the
  source data gives no way to disambiguate it further.
- **Verified flag** (source3): mixed `Y/N`, `Yes/No`, `yes/no`. Normalized to boolean.
- **Applied dates** (source1): four different formats in the same column —
  `24-07-2026` (DD-MM), `2026-08-08` (ISO), `7 Jul 2026` (text month), `08/19/2026`
  (unambiguously MM/DD, since day 19 rules out DD/MM). Parsed with a format-fallback
  chain; anything that still fails to parse is left `NULL` rather than guessed.

## 7. Mixed units hidden in a single numeric column
- `Current CTC` in source1 mixes **absolute annual rupees** (e.g. `417964`) and
  **LPA notation** (e.g. `4.2`, meaning ₹4.2 lakh/year = 420,000) in the same column
  with no unit label. Any value under 100 is unambiguously LPA shorthand (nobody's
  annual salary is ₹99). Normalized: values < 100 × 100,000; otherwise used as-is.
- `rate` in source2 mixes **hourly** (`1415/hr`) and **monthly** (`15k/month`) pay in
  the same column. Normalized to an estimated monthly figure (documented assumption:
  160 working hours/month) — this is a rough estimate and is stored alongside the raw
  value rather than replacing it, so the assumption is visible/auditable.

## 8. Skill tag vocabulary is inconsistent, not just casing
- Same skills written as `n8n`, `N8N`; `REST APIs`, `rest apis`; `Web Scraping`,
  `web scraping` across sources. Normalized to lowercase before storage/tagging so
  Task 2's skill-tagging automation isn't fooled by casing.

## 9. Ambiguous / unresolvable cases (flagged, not force-merged)
- `manish.bhatia3@example.com` (gig_workers) vs `MANISH BHATIA` phone `919000000161`
  (cbnexus) — plausibly the same person, same city (Noida), but there is no shared
  identifier between the two records to confirm it. **Left as two separate people**
  rather than guessed — this is a judgment call worth defending: false merges are
  worse than missed merges for a system that might, e.g., send someone else's payment
  history to the wrong inbox.
