"""SQLite storage. Only jobs never seen before are returned as new."""

import sqlite3
from datetime import date
from pathlib import Path

from jobscraper.normalize import dedupe_key

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.sqlite"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    dedupe_key          TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    company             TEXT,
    location            TEXT,
    remote              INTEGER,
    salary              TEXT,
    url                 TEXT,
    posted_date         TEXT,
    description_snippet TEXT,
    source              TEXT,
    first_seen          TEXT,
    score               INTEGER
)
"""


def save_new(jobs, db_path=DB_PATH):
    """Insert jobs not already in the database; return the newly inserted ones."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    new_jobs = []
    with sqlite3.connect(db_path) as conn:
        conn.execute(CREATE_SQL)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(jobs)")]
        if "score" not in columns:  # databases created before resume scoring
            conn.execute("ALTER TABLE jobs ADD COLUMN score INTEGER")
        today = date.today().isoformat()
        for job in jobs:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO jobs (dedupe_key, title, company, location, remote, "
                "salary, url, posted_date, description_snippet, source, first_seen, score) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    dedupe_key(job), job["title"], job["company"], job["location"],
                    int(job["remote"]), job["salary"], job["url"], job["posted_date"],
                    job["description_snippet"], job["source"], today, job.get("score", 0),
                ),
            )
            if cursor.rowcount:
                new_jobs.append(job)
    return new_jobs


def total_count(db_path=DB_PATH):
    db_path = Path(db_path)
    if not db_path.exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
