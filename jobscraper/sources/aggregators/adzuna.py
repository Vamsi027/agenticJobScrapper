"""Adzuna API. Needs ADZUNA_APP_ID and ADZUNA_APP_KEY env vars.

One request per (role, city) search target from the applicants, in the
country Adzuna covers for that city. Free keys: https://developer.adzuna.com/signup
"""

import os

from jobscraper.fetchers import get_json
from jobscraper.sites import ADZUNA_API as API_URL

# Countries Adzuna has a site for (lowercase ISO codes used in its URL).
COUNTRIES = {"at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "gb", "in", "it",
             "mx", "nl", "nz", "pl", "sg", "us", "za"}


def queries(config):
    settings = config.get("adzuna", {})
    out = []
    for target in config.get("search_targets", []):
        code = target["country_code"].lower()
        code = "gb" if code == "uk" else code
        if target["remote"] or not target["city"] or code not in COUNTRIES:
            continue
        out.append({"what": target["role"], "where": target["city"], "country": code})
    return out[: settings.get("max_queries", 6)]


def fetch(config):
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("  adzuna: ADZUNA_APP_ID / ADZUNA_APP_KEY not set, skipping")
        return []

    settings = config.get("adzuna", {})
    jobs = []
    for q in queries(config):
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": settings.get("results_per_page", 50),
            "what": q["what"],
            "where": q["where"],
            "max_days_old": settings.get("max_days_old", 7),
            "content-type": "application/json",
        }
        try:
            data = get_json(API_URL.format(country=q["country"], page=1), params=params)
        except Exception as exc:
            print(f"  adzuna/{q['what']!r} in {q['where']}: skipped ({exc})")
            continue
        for entry in data.get("results", []):
            salary = ""
            if entry.get("salary_min") and entry.get("salary_max"):
                salary = f"{entry['salary_min']:,.0f} - {entry['salary_max']:,.0f}"
            jobs.append({
                "title": entry.get("title", ""),
                "company": (entry.get("company") or {}).get("display_name", ""),
                "location": (entry.get("location") or {}).get("display_name", ""),
                "remote": False,
                "salary": salary,
                "url": entry.get("redirect_url", ""),
                "posted_date": entry.get("created", ""),
                "description": entry.get("description", ""),
                "source": "adzuna",
            })
    return jobs[: config.get("max_per_source")]
