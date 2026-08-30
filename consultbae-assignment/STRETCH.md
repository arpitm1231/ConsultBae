# Task 5 — Stretch: launching the audio app to 5,000 gig workers in a weekend

## What breaks first

**The database.** Right now every submission writes straight to a single
SQLite file, and SQLite only allows one writer at a time. That's fine for me
testing it alone, but the moment a few hundred workers are submitting
recordings at the same time, some of those writes are going to fail or sit
waiting, and people will see errors for no reason they can understand.

**The audio processing itself.** When someone submits a recording, my Flask
app converts it and pulls out its properties (duration, sample rate, etc)
*before* it responds back to the browser. That's fine for one person testing
locally — for 5,000 people it means every single upload ties up a server
thread for however long ffmpeg takes to decode that file. A burst of
uploads right after launch would queue up and start timing out.

**Where the files live.** Recordings are saved to a folder on whatever
server is running the app. If that's a single free-tier instance, a restart
or redeploy can wipe everything, and there's only so much disk space to
begin with.

**No protection against accidental double-submits.** If someone's upload
times out and their app or browser retries automatically, nothing currently
stops that same recording from being saved twice.

## What I'd change before launch

- **Move off SQLite** — Postgres, or at minimum turn on SQLite's WAL mode as
  a quick stopgap, so writes don't queue behind each other.
- **Don't process audio during the request.** Save the raw file immediately,
  tell the user "got it, thanks" right away, and do the actual conversion
  and property extraction afterward in the background (a simple job queue
  would do it). The user shouldn't be sitting there waiting for ffmpeg.
- **Store files somewhere durable** — S3 or similar — instead of on the
  app server's own disk.
- **Give each submission an ID generated on the client side** so a retried
  request doesn't turn into two saved recordings.
- **Watch submissions-per-minute and error rate from the start.** A launch
  weekend is exactly when I'd want to notice a problem in the first ten
  minutes, not from a pile of complaints later.

## On storage cost
5,000 people submitting one short voice clip each is maybe 5GB total — not a
real storage cost concern. The thing that would actually bite is everyone
trying to onboard in the same hour right after the announcement goes out,
which is a bandwidth/concurrency problem, not a total-size problem.

## Duplicates
The same identity logic from Task 1 — matching people by phone number, not
name — is already what the audio app uses to decide whether a submission
belongs to an existing person or a new one. So someone submitting from two
different phones or browsers still lands as one person in the database. What
it *doesn't* stop is the same person submitting many recordings on purpose —
whether that should be allowed is more of a product question than an
engineering one, and I'd want to ask before building a limit either way.
