"""Remotive public API. Remote jobs only; location is the candidate region."""

from jobscraper.fetchers import get_json
from jobscraper.sites import REMOTIVE_API as API_URL


def fetch(config):
    limit = config.get("max_per_source")
    data = get_json(API_URL, params={"limit": limit} if limit else None)
    jobs = []
    for entry in data.get("jobs", [])[:limit]:
        region = entry.get("candidate_required_location", "") or "Worldwide"
        jobs.append({
            "title": entry.get("title", ""),
            "company": entry.get("company_name", ""),
            "location": f"Remote - {region}",
            "remote": True,
            "salary": entry.get("salary", ""),
            "url": entry.get("url", ""),
            "posted_date": entry.get("publication_date", ""),
            "description": entry.get("description", ""),
            "source": "remotive",
        })
    return jobs
