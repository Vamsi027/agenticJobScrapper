"""Supabase access for the scraper, over the PostgREST API (plain httpx).

Needs two environment variables:
  SUPABASE_URL         https://<project-ref>.supabase.co
  SUPABASE_SECRET_KEY  a secret key (sb_secret_...) or the legacy service_role JWT.
                       It bypasses row-level security, so keep it out of the browser
                       and out of git.
"""

import os
from datetime import datetime, timedelta, timezone

import httpx

BATCH_SIZE = 200


class SupabaseConfigError(RuntimeError):
    pass


def client():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        raise SupabaseConfigError("Set SUPABASE_URL and SUPABASE_SECRET_KEY (see README).")
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):  # legacy JWT keys also go in Authorization; sb_ keys must not
        headers["Authorization"] = f"Bearer {key}"
    return httpx.Client(base_url=f"{url}/rest/v1", headers=headers, timeout=60)


def _check(resp):
    if resp.is_error:
        raise RuntimeError(f"Supabase HTTP {resp.status_code} on {resp.url.path}: {resp.text[:500]}")
    return resp


def fetch_applicants(db):
    """Search preferences of every applicant (used to build source queries)."""
    resp = db.get("/applicant", params={"select": "target_roles,locations,open_to_remote"})
    return _check(resp).json()


def ingest(db, jobs):
    """Upsert jobs; return the ones that were not in the database before."""
    new_keys = set()
    for start in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[start:start + BATCH_SIZE]
        resp = db.post("/rpc/ingest_jobs", json={"jobs": batch})
        new_keys.update(row["dedupe_key"] for row in _check(resp).json() if row["inserted"])
    return [job for job in jobs if job["dedupe_key"] in new_keys]


def prune(db, days):
    """Delete postings that no source has returned in `days` days. Returns the count."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    resp = db.delete("/job_postings", params={"last_seen_at": f"lt.{cutoff}"},
                     headers={"Prefer": "return=minimal,count=exact"})
    return _content_range_total(_check(resp))


def total_count(db):
    resp = db.get("/job_postings", params={"select": "id"},
                  headers={"Prefer": "count=exact", "Range": "0-0"})
    return _content_range_total(_check(resp))


def _content_range_total(resp):
    # "0-0/1234" or "*/0"
    total = resp.headers.get("content-range", "*/0").rsplit("/", 1)[-1]
    return int(total) if total.isdigit() else 0
