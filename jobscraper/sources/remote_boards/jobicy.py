"""Jobicy public API. Remote jobs only, queried per region slug (no India slug exists)."""

from jobscraper.fetchers import get_json
from jobscraper.sites import JOBICY_API as API_URL


def fetch(config):
    limit = config.get("max_per_source", 100)
    jobs = []
    for geo in config.get("jobicy_geos", ["anywhere", "apac"]):
        try:
            data = get_json(API_URL, params={"count": min(limit, 100), "geo": geo})
        except Exception as exc:
            print(f"  jobicy/{geo}: skipped ({exc})")
            continue
        for entry in data.get("jobs", [])[:limit]:
            region = entry.get("jobGeo", "") or geo
            jobs.append({
                "title": entry.get("jobTitle", ""),
                "company": entry.get("companyName", ""),
                "location": f"Remote - {region}",
                "remote": True,
                "salary": "",
                "url": entry.get("url", ""),
                "posted_date": entry.get("pubDate", ""),
                "description_snippet": entry.get("jobExcerpt", ""),
                "source": "jobicy",
            })
    return jobs
