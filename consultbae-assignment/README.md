# ConsultBae AI Automation Assignment

## What this is

Three messy CSV exports (a job-portal applicant list, a gig-worker sheet, and a
contacts export) get merged into one clean database, a no-code automation
checks new entries against that database and raises an alert on duplicates,
and a small web app collects voice recordings and automatically measures
their audio properties.

## Setup

```bash
git clone <your-repo-url>
cd consultbae-assignment

# Task 1: build the merged database
cd scripts
python3 merge_pipeline.py
# -> produces consultbae.db (SQLite), prints how many unique people it found

# Task 3: run the audio app
cd ../app
pip install flask pydub
# pydub needs ffmpeg AND ffprobe on the system PATH:
#   Mac:     brew install ffmpeg
#   Windows: winget install ffmpeg  (or download the "essentials" build from
#            gyan.dev/ffmpeg/builds, which bundles both ffmpeg.exe and
#            ffprobe.exe — some minimal builds only ship one of the two)
#   Ubuntu:  sudo apt install ffmpeg
python3 app.py
# -> open http://localhost:5000
```

## Repo structure
```
scripts/merge_pipeline.py   Task 1: entity resolution + SQLite pipeline
app/app.py                  Task 3: Flask audio collection app
app/templates/               Upload form + submissions list
n8n/duplicate_alert_flow.json  Task 2: exported n8n workflow
n8n/README.md                Task 2: how the flow works and why
DATA_ISSUES.md                Task 4: data quality findings
STRETCH.md                    Task 5: scaling write-up
```

## Task 1 — how the matching works
Two records are treated as the same person only if they share a normalized
email or a normalized phone number — never by matching on name. The dataset
has multiple people who genuinely share a name but aren't the same person
(three separate "Arjun Mehta" records with different contact details), so
name-matching would have silently merged strangers. Full reasoning is in the
docstring at the top of `merge_pipeline.py`.

## Task 2 — how the automation works
n8n workflow: a webhook receives a new applicant's phone number, a Code node
checks it against a snapshot of the real merged database, an IF node branches
on whether it's a duplicate, and if so, an HTTP Request node posts an alert.
See `n8n/README.md` for the full reasoning, including why I used a data
snapshot instead of a live query (n8n's cloud version can't reach a file on
my own laptop — that's a real constraint I ran into, not a corner I chose to
cut for convenience).

## Stuck log

### 1. ffmpeg was found but audio processing still failed
`pydub` uses two separate command-line tools under the hood: `ffmpeg` for
converting between audio formats, and `ffprobe` for reading a file's
metadata (duration, sample rate, etc). I installed ffmpeg via `winget` and
`ffmpeg -version` worked fine in the terminal, but every audio upload in the
app still failed with a 400 error. I checked the Flask server logs and found
a warning I'd scrolled past earlier: `Couldn't find ffprobe or avprobe`. The
winget package I'd used only shipped `ffmpeg.exe`, not `ffprobe.exe`. I
searched "ffmpeg vs ffprobe difference" to understand why pydub needed a
second binary at all, then downloaded the full "essentials" build from
gyan.dev instead of the winget package, which bundles both. I didn't just
add a `try/except` around the failure and move on, because silently
swallowing it would have meant every real audio submission failing in
production with no clear error — I wanted to actually understand why pydub
needed two tools before treating it as fixed.

### 2. n8n's cloud editor can't reach my own database file
The assignment's second n8n option (auto-tag skills via an LLM and write the
result back) needs the workflow to query and update `consultbae.db`. I first
tried self-hosting n8n locally via `npx n8n` so it could read the file
directly off my disk, but the install kept stalling for 15+ minutes with no
clear error — I never fully diagnosed whether it was a slow connection or
something else, because at that point the 48-hour clock mattered more than
finishing that diagnosis. I switched to n8n's cloud editor instead and picked
the assignment's *other* allowed option (duplicate-alert flow via webhook),
which only needs a snapshot of existing phone numbers to compare against,
not live write access. I documented this trade-off explicitly in
`n8n/README.md` rather than pretending the workflow has a live database
connection it doesn't have — a snapshot comparison is a legitimate way to
demo the logic, but it's not the same thing as a live query, and I'd rather
be upfront about which one I built.

### 3. The IF node's boolean check kept failing after webhook testing worked
Once the webhook and Code node were both returning the right data, the IF
node threw `Wrong type: 'true' is a string but was expecting a boolean`. I'd
typed the condition as a plain equality check comparing `{{ $json.isDuplicate }}`
against typed text, which n8n reads as a string, not the actual boolean
`true`/`false` my Code node was producing. I fixed it by using the node's
built-in "Boolean → is true" comparison type instead of typing a value to
compare against by hand. Separately, testing the flow kept returning 404
"webhook not registered" — I hadn't realized n8n's test webhooks only listen
for a single request after you press "Execute workflow", and expire
immediately after or after a timeout. Once I understood that, testing became:
click Execute, then immediately send the test request, every single time.

## What I'd do with more time
- Deduplicate audio submissions by phone at the UI level (warn before re-submit).
- Add a confidence score to entity matches instead of a hard binary merge/no-merge.
- Real bitrate metadata instead of the file-size-based estimate for compressed formats.
- Give the n8n flow live database access properly — either by exposing a small
  authenticated API endpoint from the Flask app (I built a skeleton of this,
  `/api/check-duplicate`, but didn't wire it into the final n8n flow due to
  time), or by revisiting the self-hosted n8n install with more patience.
