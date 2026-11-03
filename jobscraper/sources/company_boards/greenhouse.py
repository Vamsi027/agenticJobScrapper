"""Greenhouse public job boards, one API call per company in the config."""

from jobscraper.fetchers import get_json
from jobscraper.normalize import clean_text, config_location_ok
from jobscraper.sites import GREENHOUSE_API as API_URL


def fetch(config):
    limit = config.get("max_per_source", 100)
    jobs = []
    for company in config.get("greenhouse_companies", []):
        try:
            data = get_json(API_URL.format(company=company), params={"content": "true"})
        except Exception as exc:
            print(f"  greenhouse/{company}: skipped ({exc})")
            continue
        kept = 0
        for entry in data.get("jobs", []):
            location = clean_text((entry.get("location") or {}).get("name", ""))
            # Big boards list hundreds of jobs worldwide; cap only the ones we'd keep.
            if not config_location_ok(location, "remote" in location.lower(), config):
                continue
            if kept >= limit:
                break
            kept += 1
            jobs.append({
                "title": entry.get("title", ""),
                "company": company,
                "location": location,
                "remote": "remote" in location.lower(),
                "salary": "",
                "url": entry.get("absolute_url", ""),
                # first_published = original posting date; updated_at changes on every edit
                "posted_date": (entry.get("first_published") or entry.get("updated_at") or "")[:10],
                "description_snippet": entry.get("content", ""),
                "source": "greenhouse",
            })
    return jobs
