"""Adzuna API (India). Needs ADZUNA_APP_ID and ADZUNA_APP_KEY env vars.

Free keys: https://developer.adzuna.com/signup
"""

import os

from jobscraper.fetchers import get_json
from jobscraper.sites import ADZUNA_API as API_URL


def fetch(config):
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("  adzuna: ADZUNA_APP_ID / ADZUNA_APP_KEY not set, skipping")
        return []

    adzuna = config.get("adzuna", {})
    limit = config.get("max_per_source", 100)
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": min(limit, 50),
        "what_or": " ".join(config.get("keywords", [])),
        "where": adzuna.get("where", "Hyderabad"),
        "max_days_old": adzuna.get("max_days_old", 30),
        "content-type": "application/json",
    }
    url = API_URL.format(country=adzuna.get("country", "in"), page=1)
    data = get_json(url, params=params)

    jobs = []
    for entry in data.get("results", [])[:limit]:
        salary = ""
        if entry.get("salary_min") and entry.get("salary_max"):
            salary = f"INR {entry['salary_min']:,.0f} - {entry['salary_max']:,.0f}"
        jobs.append({
            "title": entry.get("title", ""),
            "company": (entry.get("company") or {}).get("display_name", ""),
            "location": (entry.get("location") or {}).get("display_name", ""),
            "remote": False,
            "salary": salary,
            "url": entry.get("redirect_url", ""),
            "posted_date": entry.get("created", ""),
            "description_snippet": entry.get("description", ""),
            "source": "adzuna",
        })
    return jobs
