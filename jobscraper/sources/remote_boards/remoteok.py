"""RemoteOK public API. First array element is a legal notice, not a job."""

from jobscraper.fetchers import get_json
from jobscraper.sites import REMOTEOK_API as API_URL


def fetch(config):
    limit = config.get("max_per_source", 100)
    data = get_json(API_URL)
    jobs = []
    for entry in data:
        if "position" not in entry:  # skips the legal-notice element
            continue
        salary = ""
        if entry.get("salary_min") and entry.get("salary_max"):
            salary = f"${entry['salary_min']:,} - ${entry['salary_max']:,}"
        jobs.append({
            "title": entry.get("position", ""),
            "company": entry.get("company", ""),
            "location": entry.get("location", "") or "Remote",
            "remote": True,
            "salary": salary,
            "url": entry.get("url", ""),
            "posted_date": entry.get("date", ""),
            "description_snippet": entry.get("description", ""),
            "source": "remoteok",
        })
        if len(jobs) >= limit:
            break
    return jobs
