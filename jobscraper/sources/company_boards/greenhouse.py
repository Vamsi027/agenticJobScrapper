"""Greenhouse public job boards, one API call per company. Every posting is kept."""

from jobscraper.fetchers import get_json
from jobscraper.normalize import clean_text
from jobscraper.sites import GREENHOUSE_API as API_URL


def fetch(config):
    limit = config.get("max_per_source")
    jobs = []
    for company in config.get("greenhouse_companies", []):
        try:
            data = get_json(API_URL.format(company=company), params={"content": "true"})
        except Exception as exc:
            print(f"  greenhouse/{company}: skipped ({exc})")
            continue
        for entry in data.get("jobs", [])[:limit]:
            location = clean_text((entry.get("location") or {}).get("name", ""))
            jobs.append({
                "title": entry.get("title", ""),
                "company": company,
                "location": location,
                "remote": "remote" in location.lower(),
                "salary": "",
                "url": entry.get("absolute_url", ""),
                # first_published = original posting date; updated_at changes on every edit
                "posted_date": (entry.get("first_published") or entry.get("updated_at") or "")[:10],
                "description": entry.get("content", ""),
                "source": "greenhouse",
            })
    return jobs
