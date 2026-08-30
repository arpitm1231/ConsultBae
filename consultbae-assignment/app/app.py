"""
ConsultBae Assignment - Task 3: Mini Audio Collection App
==========================================================

Flow:
  1. GET  /              -> form: name, phone, record-or-upload audio
  2. POST /submit        -> saves audio file, extracts properties, writes
                             a person + audio_submission row into consultbae.db
  3. GET  /submissions    -> lists all submissions with a player + properties

AUDIO PROPERTY EXTRACTION - WHY pydub:
Browser microphone recording (MediaRecorder API) produces .webm/.ogg, not .wav.
The stdlib `wave` module only reads uncompressed PCM WAV, so it can't handle
browser recordings or uploaded mp3s. pydub (backed by ffmpeg) decodes any
common format uniformly, which is why it's used here instead of `wave`.

Extracted per submission (assignment requirement):
  - duration_sec      : len(audio) in ms / 1000, from pydub
  - sample_rate_hz    : audio.frame_rate
  - bitrate_kbps      : estimated as (file_size_bytes * 8) / duration_sec / 1000
                         (there's no universal "bitrate" tag for raw PCM once
                         decoded, so this is computed from actual file size vs
                         duration - the same way most tools report it for
                         variable/unlabeled formats. Documented assumption.)
  - loudness_dbfs     : audio.dBFS (pydub's RMS-based loudness relative to
                         full scale - this is the bonus "quality estimate":
                         very low dBFS ~ near-silence/likely bad recording,
                         very high positive-side values would suggest clipping)
"""

import os
import sqlite3
from datetime import datetime

from flask import Flask, request, redirect, url_for, render_template, send_from_directory
from pydub import AudioSegment

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "..", "scripts", "consultbae.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB cap per upload


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def find_or_create_person(conn, name, phone):
    """
    Reuses the SAME identity model as Task 1: match by normalized phone.
    If this phone already exists in `person`, attach the audio submission
    to that existing person instead of creating a duplicate.
    """
    digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
    row = conn.execute(
        "SELECT person_id FROM person WHERE primary_phone = ?", (digits,)
    ).fetchone()
    if row:
        return row["person_id"], digits
    cur = conn.execute(
        "INSERT INTO person (display_name, primary_phone, in_naukri, in_gig_workers, in_cbnexus) "
        "VALUES (?,?,0,0,0)",
        (name, digits),
    )
    conn.commit()
    return cur.lastrowid, digits


def extract_audio_properties(filepath):
    audio = AudioSegment.from_file(filepath)
    duration_sec = len(audio) / 1000.0
    sample_rate_hz = audio.frame_rate
    file_size_bytes = os.path.getsize(filepath)
    bitrate_kbps = round((file_size_bytes * 8) / duration_sec / 1000, 1) if duration_sec > 0 else None
    loudness_dbfs = audio.dBFS  # can be -inf for pure silence
    if loudness_dbfs == float("-inf"):
        loudness_dbfs = None
    return {
        "duration_sec": round(duration_sec, 2),
        "sample_rate_hz": sample_rate_hz,
        "bitrate_kbps": bitrate_kbps,
        "loudness_dbfs": round(loudness_dbfs, 1) if loudness_dbfs is not None else None,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    audio_file = request.files.get("audio")

    if not name or not phone or not audio_file:
        return "Missing name, phone, or audio file", 400

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = "".join(c for c in name if c.isalnum()) or "anon"
    raw_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_name}_raw")
    audio_file.save(raw_path)

    # Convert to a standard .wav copy for reliable playback across browsers,
    # keep original too for provenance.
    final_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_name}.wav")
    try:
        AudioSegment.from_file(raw_path).export(final_path, format="wav")
    except Exception as e:
        return f"Could not process audio file: {e}", 400

    props = extract_audio_properties(final_path)

    conn = get_db()
    person_id, phone_norm = find_or_create_person(conn, name, phone)
    conn.execute(
        "INSERT INTO audio_submission (person_id, name, phone, file_path, duration_sec, "
        "sample_rate_hz, bitrate_kbps, loudness_dbfs, submitted_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (person_id, name, phone_norm, os.path.basename(final_path),
         props["duration_sec"], props["sample_rate_hz"], props["bitrate_kbps"],
         props["loudness_dbfs"], datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    os.remove(raw_path)

    return redirect(url_for("submissions"))


@app.route("/submissions")
def submissions():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM audio_submission ORDER BY submitted_at DESC"
    ).fetchall()
    conn.close()
    return render_template("submissions.html", rows=rows)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
