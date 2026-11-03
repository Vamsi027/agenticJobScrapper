"""JSearch on RapidAPI (Google for Jobs). Needs the RAPIDAPI_KEY env var.

Surfaces LinkedIn / Naukri / Indeed / Glassdoor listings without scraping them.
Free tier is small (~200 requests/month), so each run makes one request
per entry in config "jsearch.queries".
Sign up: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
"""

import os

from jobscraper.fetchers import get_json
from jobscraper.sites import JSEARCH_API as API_URL, JSEARCH_HOST


def _location(entry):
    parts = [entry.get("job_city"), entry.get("job_state"), entry.get("job_country")]
    place = ", ".join(p for p in parts if p)
    if entry.get("job_is_remote"):
        return f"Remote - {place}" if place else "Remote"
    return place


def fetch(config):
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        print("  jsearch: RAPIDAPI_KEY not set, skipping")
        return []

    jsearch = config.get("jsearch", {})
    keywords = " ".join(config.get("keywords", []))
    headers = {"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": JSEARCH_HOST}
    limit = config.get("max_per_source", 100)

    jobs = []
    for q in jsearch.get("queries", []):
        params = {
            "query": q["query"].format(keywords=keywords),
            "country": jsearch.get("country", "in"),
            "date_posted": jsearch.get("date_posted", "week"),
        }
        if q.get("remote"):
            params["work_from_home"] = "true"
        try:
            data = get_json(API_URL, params=params, headers=headers)
        except Exception as exc:
            print(f"  jsearch/{params['query']!r}: skipped ({exc})")
            continue
        # search-v2 wraps results as {"data": {"jobs": [...], "cursor": ...}}; 10 jobs per request
        for entry in (data.get("data") or {}).get("jobs", [])[:limit]:
            salary = ""
            if entry.get("job_min_salary") and entry.get("job_max_salary"):
                salary = (f"{entry.get('job_salary_currency') or ''} "
                          f"{entry['job_min_salary']:,.0f} - {entry['job_max_salary']:,.0f}").strip()
            jobs.append({
                "title": entry.get("job_title", ""),
                "company": entry.get("employer_name", ""),
                "location": _location(entry),
                "remote": bool(entry.get("job_is_remote")),
                "salary": salary,
                "url": entry.get("job_apply_link", ""),
                "posted_date": entry.get("job_posted_at_datetime_utc", ""),
                "description_snippet": entry.get("job_description", ""),
                "source": f"jsearch:{entry.get('job_publisher', '')}",
            })
    return jobs
