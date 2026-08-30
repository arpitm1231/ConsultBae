# Task 5 — Stretch: launching the audio app to 5,000 gig workers in a weekend

*(Draft — rewrite this in your own words before submitting; these are real
engineering concerns given how the app in this repo is actually built, not
generic boilerplate.)*

## What breaks first
- **SQLite write locking.** The app writes every submission straight to a single
  SQLite file. SQLite allows only one writer at a time — under concurrent load
  from thousands of workers, submissions will start failing or queueing with
  "database is locked" errors well before 5,000 users, probably in the low
  hundreds of concurrent writers.
- **Synchronous audio processing on the request thread.** Right now, `pydub`
  decodes and re-exports every file inline during the HTTP request before
  responding. On a slow phone upload with a large file, that request thread is
  blocked for the full decode time — a burst of concurrent uploads will exhaust
  the server's worker threads and everyone's request will time out, even if
  each individual conversion is fast.
- **Local disk storage.** Audio files are saved to a local `uploads/` folder.
  On a single free-tier instance (Render/Railway), disk is small and ephemeral —
  a redeploy or restart can wipe all submitted audio, and disk fills up fast at
  scale.
- **No upload size/type enforcement beyond a blanket 25MB cap.** A single
  worker submitting a 25MB file repeatedly, or many workers doing so
  simultaneously, exhausts bandwidth and disk fast.
- **No idempotency / duplicate submission protection.** If a worker's request
  times out and their app retries, there's nothing stopping the same recording
  being saved and charged/counted twice.

## What I'd change before launch
- **Swap SQLite for Postgres** (or at minimum enable WAL mode as a stopgap) —
  removes the single-writer bottleneck.
- **Move audio processing off the request path**: accept the upload, save the
  raw file immediately, return success to the user right away, and process
  (convert + extract properties) asynchronously via a queue (e.g. a simple
  Redis + RQ/Celery worker, or a serverless function triggered on upload).
  The user shouldn't wait on ffmpeg.
- **Move storage to object storage** (S3 / Cloudflare R2 / Backblaze) instead
  of local disk — durable, doesn't depend on the app server's lifecycle, and
  scales storage independently of compute.
- **Add a submission ID / idempotency key** generated client-side so retried
  requests don't double-count.
- **Rate-limit per phone number** to blunt accidental or malicious repeat
  submissions.
- **Add basic monitoring**: a dashboard of submissions/minute and failure rate,
  so a launch-weekend spike or outage is visible immediately rather than
  discovered from complaints.

## Storage & cost napkin math
5,000 workers × ~1 recording × ~1MB average (a short voice clip) ≈ 5GB total —
cheap on any object store, but the number that actually matters is **concurrent
upload bandwidth during a launch spike**, not total storage, since gig workers
onboarding tends to cluster around the announcement time rather than spread
evenly across the weekend.

## Duplicates
Task 1's identity-resolution logic (match by phone, not name) is directly
reusable here: the Flask app already looks up `person` by normalized phone
before creating a new record, so a worker submitting twice from two devices
still attaches to one person — but nothing currently stops the *same person*
submitting many audio files, which may or may not be desired behavior and is
worth a product decision, not just an engineering one.
