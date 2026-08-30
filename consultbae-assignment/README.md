# ConsultBae AI Automation Assignment

## Setup

```bash
git clone <your-repo-url>
cd consultbae-assignment

# Task 1: build the merged database
cd scripts
python3 merge_pipeline.py
# -> produces consultbae.db (SQLite)

# Task 3: run the audio app
cd ../app
pip install flask pydub
# pydub needs ffmpeg installed on the system:
#   Mac:   brew install ffmpeg
#   Ubuntu: sudo apt install ffmpeg
python3 app.py
# -> open http://localhost:5000
```

## Repo structure
```
scripts/merge_pipeline.py   Task 1: entity resolution + SQLite pipeline
app/app.py                  Task 3: Flask audio collection app
app/templates/              Upload form + submissions list
n8n/README.md               Task 2: n8n flow build steps + exported flow JSON
DATA_ISSUES.md               Task 4: data quality findings
STRETCH.md                   Task 5: scaling write-up
```

## Task 1 — how matching works (read this before the live defense)
Identity resolution uses a union-find over normalized (email, phone) pairs —
NOT name matching. This matters because the dataset has multiple people who
share a name but are NOT the same person (see `DATA_ISSUES.md` #2), and
multiple records of the same person under different name spellings/emails
that SHOULD merge (`DATA_ISSUES.md` #3). Full reasoning is in the docstring
at the top of `merge_pipeline.py`.

## Stuck log

*(Replace this with your own — write it AFTER you've actually built the thing,
not before. Genuine confusion and how you resolved it is literally what's
being scored; a polished-sounding fake stuck log is worse than an honest messy
one.)*

### 1. [Where you got stuck]
- What happened:
- What you searched / asked AI:
- What you tried that didn't work, and why you rejected it:
- What actually fixed it:

### 2. [Where you got stuck]
- What happened:
- What you searched / asked AI:
- What you tried that didn't work, and why you rejected it:
- What actually fixed it:

### 3. [Where you got stuck]
- What happened:
- What you searched / asked AI:
- What you tried that didn't work, and why you rejected it:
- What actually fixed it:

## What I'd do with more time
- Deduplicate audio submissions by phone at the UI level (warn before re-submit).
- Add a confidence score to entity matches instead of a hard binary merge/no-merge.
- Real bitrate metadata instead of the file-size-based estimate for compressed formats.
