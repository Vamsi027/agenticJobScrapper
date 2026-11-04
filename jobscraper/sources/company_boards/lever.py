"""Lever public postings API, one call per company. Every posting is kept."""

from datetime import datetime, timezone

from jobscraper.fetchers import get_json
from jobscraper.normalize import clean_text
from jobscraper.sites import LEVER_API as API_URL


def fetch(config):
    limit = config.get("max_per_source")
    jobs = []
    for company in config.get("lever_companies", []):
        try:
            data = get_json(API_URL.format(company=company), params={"mode": "json"})
        except Exception as exc:
            print(f"  lever/{company}: skipped ({exc})")
            continue
        for entry in data[:limit]:
            location = clean_text((entry.get("categories") or {}).get("location", ""))
            posted = ""
            if entry.get("createdAt"):
                posted = datetime.fromtimestamp(
                    entry["createdAt"] / 1000, tz=timezone.utc
                ).date().isoformat()
            jobs.append({
                "title": entry.get("text", ""),
                "company": company,
                "location": location,
                "remote": "remote" in location.lower(),
                "salary": "",
                "url": entry.get("hostedUrl", ""),
                "posted_date": posted,
                "description": entry.get("descriptionPlain", ""),
                "source": "lever",
            })
    return jobs
