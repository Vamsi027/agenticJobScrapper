"""Export the jobs database to CSV (Excel-friendly).

Usage:
    python -m jobscraper.export          # writes data/jobs.csv
    python -m jobscraper.export out.csv  # custom output path
"""

import csv
import sqlite3
import sys
from pathlib import Path

from jobscraper.storage import DB_PATH

DEFAULT_CSV = DB_PATH.with_suffix(".csv")
RANKED_CSV = DB_PATH.parent / "ranked_jobs.csv"
RANKED_FIELDS = ("rank", "score", "title", "company", "location", "remote", "salary",
                 "posted_date", "source", "url", "description_snippet")


def export_ranked(jobs, csv_path=RANKED_CSV):
    """Write one run's matched jobs (already sorted by score) with a rank column."""
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=RANKED_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for rank, job in enumerate(jobs, start=1):
            writer.writerow({**job, "rank": rank})
    print(f"Ranked {len(jobs)} jobs -> {csv_path}")
    return csv_path


def export_csv(db_path=DB_PATH, csv_path=DEFAULT_CSV):
    csv_path = Path(csv_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT score, title, company, location, remote, salary, posted_date, "
            "source, first_seen, url, description_snippet "
            "FROM jobs ORDER BY first_seen DESC, score DESC, company, title"
        )
        header = [d[0] for d in rows.description]
        # utf-8-sig so Excel detects the encoding and shows accents correctly
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            count = 0
            for row in rows:
                writer.writerow(row)
                count += 1
    print(f"Exported {count} jobs to {csv_path}")
    return csv_path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    if not Path(DB_PATH).exists():
        sys.exit(f"No database at {DB_PATH} - run python -m jobscraper first.")
    export_csv(csv_path=target)
