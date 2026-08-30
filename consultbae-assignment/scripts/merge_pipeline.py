"""
ConsultBae Assignment - Task 1: Merge Pipeline
================================================

WHY THIS APPROACH:
Three sources, no single common ID:
  - source1 (naukri_applicants): has EMAIL + PHONE
  - source2 (gig_workers):       has EMAIL only (no phone)
  - source3 (cbnexus_contacts):  has PHONE only (no email)

The naive approach is "match by name" - but this dataset deliberately breaks
that: there are multiple "Arjun Mehta" records that are NOT the same person
(different emails, different phones, different project histories). Matching
on name alone would silently merge strangers.

So the identity model is:
  - Two records are the SAME PERSON only if they share a normalized EMAIL
    or a normalized PHONE NUMBER (the two identifiers that are actually
    unique-ish across a population).
  - We build this as a graph: each record contributes an "email" node and/or
    a "phone" node, connected to each other. Connected components =
    one person. This is a Union-Find (disjoint set), the standard way to
    solve exactly this "record linkage" problem.
  - Name is NEVER used as a merge key. It's only used for display and as
    a manual-review flag when things look suspicious (see data_issues.py).

Run: python3 merge_pipeline.py
Produces: consultbae.db (SQLite)
"""

import sqlite3
import csv
import re
from datetime import datetime

DB_PATH = "consultbae.db"


# ---------- Normalization helpers ----------

def norm_email(email):
    if not email or not email.strip():
        return None
    return email.strip().lower()


def norm_phone(phone):
    """Strip +91, leading 0, spaces, dashes -> last 10 digits."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 10:
        return digits[-10:]
    return None


def norm_city(city):
    if not city:
        return None
    c = city.strip().lower()
    # Known aliases for the same metro area (Gurgaon was renamed Gurugram)
    aliases = {
        "gurgaon": "gurugram",
        "gurugram": "gurugram",
        "bangalore": "bengaluru",
        "bengaluru": "bengaluru",
        "new delhi": "delhi",
        "delhi ncr": "delhi",  # ambiguous NCR label -> bucket with delhi, flagged separately
        "delhi": "delhi",
        "noida": "noida",
        "pune": "pune",
    }
    return aliases.get(c, c)


def norm_name(name):
    if not name:
        return None
    return " ".join(name.strip().split())


def parse_date(raw):
    """source1 dates come in at least 4 different formats."""
    if not raw:
        return None
    raw = raw.strip()
    formats = ["%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%m/%d/%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None  # unparseable -> logged as an issue


def parse_ctc_to_annual_inr(raw):
    """
    source1 'Current CTC' mixes two units in the SAME column:
      - large numbers like 417964        -> already annual rupees
      - small numbers like 4.2, 8.3      -> LPA (lakhs per annum), i.e. x100000
    Heuristic: anything under 100 is obviously LPA notation, not a real salary.
    """
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    if val < 100:
        return round(val * 100000)
    return round(val)


def parse_gig_rate(raw):
    """
    source2 'rate' mixes hourly ('1415/hr') and monthly ('15k/month').
    Normalize everything to an estimated monthly INR figure using
    a flat 160 working hours/month assumption (documented in data issues report).
    Returns (raw_value, unit, monthly_est)
    """
    if not raw:
        return None, None, None
    raw = raw.strip()
    m = re.match(r"([\d.]+)k?/(hr|month)", raw, re.IGNORECASE)
    if not m:
        return raw, "unknown", None
    num, unit = m.groups()
    num = float(num)
    if "k" in raw.lower() and unit.lower() == "month":
        monthly = num * 1000
    elif unit.lower() == "hr":
        monthly = num * 160
    else:
        monthly = num
    return raw, unit.lower(), round(monthly)


def norm_bool(raw):
    if raw is None:
        return None
    r = raw.strip().lower()
    if r in ("y", "yes", "true", "1"):
        return 1
    if r in ("n", "no", "false", "0"):
        return 0
    return None


# ---------- Union-Find ----------

class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


# ---------- Load raw rows from each source ----------

def load_source1(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "source": "naukri",
                "name": norm_name(r["Full Name"]),
                "email": norm_email(r["Email"]),
                "phone": norm_phone(r["Phone"]),
                "city": norm_city(r["City"]),
                "experience_years": float(r["Experience (Years)"]) if r["Experience (Years)"] else None,
                "ctc_annual_inr": parse_ctc_to_annual_inr(r["Current CTC"]),
                "applied_date": parse_date(r["Applied Date"]),
                "skills": [s.strip().lower() for s in r["Skills"].split(",")] if r["Skills"] else [],
            })
    return rows


def load_source2(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            email = r.get("email_id", "")
            name = r.get("worker_name", "")
            # Skip fully blank rows (planted junk row)
            if not email.strip() and not name.strip():
                continue
            # Skip shift-corrupted rows: email_id field doesn't look like an email
            if email and "@" not in email:
                continue
            raw_rate, unit, monthly_est = parse_gig_rate(r.get("rate"))
            rows.append({
                "source": "gig_workers",
                "name": norm_name(name),
                "email": norm_email(email),
                "phone": None,
                "city": norm_city(r.get("location")),
                "gig_status": (r.get("status") or "").strip().lower() or None,
                "gig_rate_raw": raw_rate,
                "gig_rate_unit": unit,
                "gig_rate_monthly_est": monthly_est,
                "skills": [s.strip().lower() for s in r["skill_tags"].split(",")] if r.get("skill_tags") else [],
            })
    return rows


def load_source3(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Planted issue: header row repeated mid-file
            if r.get("Name") == "Name":
                continue
            rows.append({
                "source": "cbnexus",
                "name": norm_name(r["Name"]),
                "email": None,
                "phone": norm_phone(r["Phone Number"]),
                "city": norm_city(r["City"]),
                "verified": norm_bool(r["Verified"]),
                "projects_completed": int(r["Projects Completed"]) if r["Projects Completed"] else None,
            })
    return rows


# ---------- Entity resolution ----------

def resolve_identities(all_rows):
    """
    Returns: dict record_index -> person_id (int)
    Builds a graph over (email, phone) identifiers per record and finds
    connected components.
    """
    uf = UnionFind()
    for i, row in enumerate(all_rows):
        keys = []
        if row.get("email"):
            keys.append(("email", row["email"]))
        if row.get("phone"):
            keys.append(("phone", row["phone"]))
        # union all identifier-keys this record carries together
        for k in keys:
            uf.union(("record", i), k)
        # a record with only one identifier still needs a node so find() works
        if not keys:
            uf.union(("record", i), ("record", i))

    root_to_person = {}
    record_to_person = {}
    next_id = 1
    for i in range(len(all_rows)):
        root = uf.find(("record", i))
        if root not in root_to_person:
            root_to_person[root] = next_id
            next_id += 1
        record_to_person[i] = root_to_person[root]
    return record_to_person


# ---------- Build database ----------

SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
    person_id INTEGER PRIMARY KEY,
    display_name TEXT,
    primary_email TEXT,
    primary_phone TEXT,
    city TEXT,
    in_naukri INTEGER DEFAULT 0,
    in_gig_workers INTEGER DEFAULT 0,
    in_cbnexus INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS naukri_application (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(person_id),
    experience_years REAL,
    ctc_annual_inr INTEGER,
    applied_date TEXT,
    skills TEXT
);

CREATE TABLE IF NOT EXISTS gig_worker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(person_id),
    status TEXT,
    rate_raw TEXT,
    rate_unit TEXT,
    rate_monthly_est INTEGER,
    skills TEXT
);

CREATE TABLE IF NOT EXISTS cbnexus_contact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(person_id),
    verified INTEGER,
    projects_completed INTEGER
);

-- Task 3 will insert into this table
CREATE TABLE IF NOT EXISTS audio_submission (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(person_id),
    name TEXT,
    phone TEXT,
    file_path TEXT,
    duration_sec REAL,
    sample_rate_hz INTEGER,
    bitrate_kbps INTEGER,
    loudness_dbfs REAL,
    submitted_at TEXT
);
"""


def build_db(all_rows, record_to_person):
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("DROP TABLE IF EXISTS person; DROP TABLE IF EXISTS naukri_application; "
                        "DROP TABLE IF EXISTS gig_worker; DROP TABLE IF EXISTS cbnexus_contact; "
                        "DROP TABLE IF EXISTS audio_submission;")
    conn.executescript(SCHEMA)
    cur = conn.cursor()

    # group rows by person
    people = {}
    for i, row in enumerate(all_rows):
        pid = record_to_person[i]
        people.setdefault(pid, []).append(row)

    for pid, rows in people.items():
        # Prefer the fullest-looking name (most words, then longest string) as
        # the canonical display name - handles cases like "R. Verma" vs
        # "Rohit Verma" for the same person (duplicate applicant, abbreviated
        # name on one submission).
        candidate_names = [r["name"] for r in rows if r.get("name")]
        name = max(candidate_names, key=lambda n: (len(n.split()), len(n)), default=None)
        email = next((r["email"] for r in rows if r.get("email")), None)
        phone = next((r["phone"] for r in rows if r.get("phone")), None)
        city = next((r["city"] for r in rows if r.get("city")), None)
        sources = {r["source"] for r in rows}
        cur.execute(
            "INSERT INTO person (person_id, display_name, primary_email, primary_phone, city, "
            "in_naukri, in_gig_workers, in_cbnexus) VALUES (?,?,?,?,?,?,?,?)",
            (pid, name, email, phone, city,
             int("naukri" in sources), int("gig_workers" in sources), int("cbnexus" in sources))
        )
        for r in rows:
            if r["source"] == "naukri":
                cur.execute(
                    "INSERT INTO naukri_application (person_id, experience_years, ctc_annual_inr, "
                    "applied_date, skills) VALUES (?,?,?,?,?)",
                    (pid, r["experience_years"], r["ctc_annual_inr"], r["applied_date"],
                     ",".join(r["skills"]))
                )
            elif r["source"] == "gig_workers":
                cur.execute(
                    "INSERT INTO gig_worker (person_id, status, rate_raw, rate_unit, "
                    "rate_monthly_est, skills) VALUES (?,?,?,?,?,?)",
                    (pid, r["gig_status"], r["gig_rate_raw"], r["gig_rate_unit"],
                     r["gig_rate_monthly_est"], ",".join(r["skills"]))
                )
            elif r["source"] == "cbnexus":
                cur.execute(
                    "INSERT INTO cbnexus_contact (person_id, verified, projects_completed) "
                    "VALUES (?,?,?)",
                    (pid, r["verified"], r["projects_completed"])
                )
    conn.commit()
    conn.close()


def main():
    s1 = load_source1("../data/source1_naukri_applicants.csv")
    s2 = load_source2("../data/source2_gig_workers.csv")
    s3 = load_source3("../data/source3_cbnexus_contacts.csv")
    all_rows = s1 + s2 + s3
    record_to_person = resolve_identities(all_rows)
    build_db(all_rows, record_to_person)

    n_people = len(set(record_to_person.values()))
    print(f"Loaded {len(s1)} naukri rows, {len(s2)} gig_worker rows, {len(s3)} cbnexus rows")
    print(f"Total raw rows: {len(all_rows)}")
    print(f"Resolved to {n_people} unique people")
    print(f"Database written to {DB_PATH}")


if __name__ == "__main__":
    main()
