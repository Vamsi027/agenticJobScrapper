"""LinkedIn job postings via Bright Data's Web Scraper API. Needs BRIGHTDATA_API_KEY.

Uses the "LinkedIn job listings" dataset with keyword discovery. Discovery is
always asynchronous: trigger one job for all queries -> poll progress ->
download the snapshot. Takes a few minutes per run.

Bright Data bills per record returned, so "limit_per_input" in the config
caps the cost: at most limit_per_input x number of queries records per run.
Docs: https://docs.brightdata.com/api-reference/scrapers/social-media-apis/linkedin-jobs-discover-by-keyword
"""

import os
import time

import httpx

from jobscraper.sites import BRIGHTDATA_API, BRIGHTDATA_LINKEDIN_JOBS_DATASET as DATASET_ID

# Fields Bright Data accepts per query; anything else in a config query is ignored.
INPUT_FIELDS = ("keyword", "location", "country", "time_range", "job_type",
                "experience_level", "remote", "company", "location_radius", "selective_search")


def _check(resp):
    """raise_for_status(), but with Bright Data's error message included."""
    if resp.is_error:
        raise RuntimeError(f"Bright Data HTTP {resp.status_code} on {resp.url.path}: {resp.text[:300]}")
    return resp


def _salary(entry):
    if entry.get("job_base_pay_range"):
        return entry["job_base_pay_range"]
    pay = entry.get("base_salary") or {}
    if pay.get("min_amount") and pay.get("max_amount"):
        period = f" / {pay['payment_period'].lower()}" if pay.get("payment_period") else ""
        return (f"{pay.get('currency') or ''} {pay['min_amount']:,.0f} - "
                f"{pay['max_amount']:,.0f}{period}").strip()
    return ""


def _to_job(entry):
    location = entry.get("job_location") or ""
    asked_remote = ((entry.get("discovery_input") or {}).get("remote") or "").lower() == "remote"
    return {
        "title": entry.get("job_title") or "",
        "company": entry.get("company_name") or "",
        "location": location,
        "remote": asked_remote or "remote" in location.lower(),
        "salary": _salary(entry),
        "url": (entry.get("url") or "").split("?")[0],
        "posted_date": entry.get("job_posted_date") or "",
        "description_snippet": entry.get("job_summary") or "",
        "source": "linkedin",
    }


def trigger(client, queries, limit_per_input):
    inputs = [{k: q[k] for k in INPUT_FIELDS if q.get(k) not in (None, "")} for q in queries]
    resp = client.post(
        f"{BRIGHTDATA_API}/trigger",
        params={"dataset_id": DATASET_ID, "type": "discover_new", "discover_by": "keyword",
                "include_errors": "true"},
        json={"input": inputs, "limit_per_input": limit_per_input},
    )
    _check(resp)
    return resp.json()["snapshot_id"]


def wait_until_ready(client, snapshot_id, timeout_s, poll_s):
    deadline = time.monotonic() + timeout_s
    while True:
        resp = client.get(f"{BRIGHTDATA_API}/progress/{snapshot_id}")
        _check(resp)
        progress = resp.json()
        status = progress.get("status")
        if status == "ready":
            return
        if status in ("failed", "canceled"):
            raise RuntimeError(f"snapshot {snapshot_id} {status}: {progress.get('error_message', '')}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"snapshot {snapshot_id} still '{status}' after {timeout_s}s; "
                               "it keeps running on Bright Data's side")
        time.sleep(poll_s)


def download(client, snapshot_id):
    resp = client.get(f"{BRIGHTDATA_API}/snapshot/{snapshot_id}", params={"format": "json"})
    _check(resp)
    return resp.json()


def collect(client, settings):
    """Trigger, wait, download; returns raw Bright Data records."""
    queries = settings.get("queries", [])
    if not queries:
        return []
    snapshot_id = trigger(client, queries, settings.get("limit_per_input", 25))
    print(f"  linkedin: Bright Data snapshot {snapshot_id} started, waiting ...")
    wait_until_ready(client, snapshot_id,
                     timeout_s=settings.get("timeout_minutes", 10) * 60,
                     poll_s=settings.get("poll_seconds", 15))
    return download(client, snapshot_id)


def fetch(config, transport=None):
    api_key = os.environ.get("BRIGHTDATA_API_KEY")
    if not api_key:
        print("  linkedin: BRIGHTDATA_API_KEY not set, skipping")
        return []

    settings = config.get("brightdata_linkedin", {})
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(headers=headers, timeout=60, transport=transport) as client:
        records = collect(client, settings)

    jobs, errors = [], 0
    for entry in records:
        # include_errors=true puts failed inputs in the results with an "error" key
        if entry.get("error") or entry.get("error_code") or not entry.get("job_title"):
            errors += 1
            continue
        jobs.append(_to_job(entry))
    if errors:
        print(f"  linkedin: {errors} error/empty records skipped")
    return jobs[: config.get("max_per_source", 100)]
