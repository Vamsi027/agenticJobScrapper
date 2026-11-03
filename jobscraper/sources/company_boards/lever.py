"""Lever public postings API, one call per company in the config."""

from datetime import datetime, timezone

from jobscraper.fetchers import get_json
from jobscraper.normalize import clean_text, config_location_ok
from jobscraper.sites import LEVER_API as API_URL


def fetch(config):
    limit = config.get("max_per_source", 100)
    jobs = []
    for company in config.get("lever_companies", []):
        try:
            data = get_json(API_URL.format(company=company), params={"mode": "json"})
        except Exception as exc:
            print(f"  lever/{company}: skipped ({exc})")
            continue
        kept = 0
        for entry in data:
            location = clean_text((entry.get("categories") or {}).get("location", ""))
            # Big boards list hundreds of jobs worldwide; cap only the ones we'd keep.
            if not config_location_ok(location, "remote" in location.lower(), config):
                continue
            if kept >= limit:
                break
            kept += 1
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
                "description_snippet": entry.get("descriptionPlain", ""),
                "source": "lever",
            })
    return jobs
