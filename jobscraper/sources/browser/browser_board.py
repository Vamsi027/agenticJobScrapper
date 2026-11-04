"""Playwright-based fetcher for a JS-rendered job board.

Site-agnostic: the board URL and CSS selectors come from the
"browser_board" block in jobscraper/settings.py, so switching boards means
editing settings, not code.

Optional config keys:
  detail_fields  field -> selector read from each job's own page (e.g. the
                 full description, or all locations when the list only says
                 "2 Locations"). Costs one page load per job.
  detail_limit   visit at most this many detail pages per run.
  posted         selector for a "Posted 3 Days Ago"-style label; converted to
                 an ISO date. Can be a list-page field or a detail field.
"""

import re
from datetime import date, timedelta

from jobscraper.fetchers import fetch_elements


def parse_posted(text, today=None):
    """'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago' / '30+ Days Ago' -> ISO date."""
    today = today or date.today()
    text = (text or "").lower()
    if "today" in text or "just posted" in text:
        return today.isoformat()
    if "yesterday" in text:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*(day|week|month)s?\s+ago", text)
    if not m:
        return ""
    days = int(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2)]
    return (today - timedelta(days=days)).isoformat()


def fetch(config):
    board = config.get("browser_board", {})
    url = board.get("url", "")
    if not url or "example.com" in url:
        print("  browser_board: no real board configured, skipping")
        return []

    records = fetch_elements(
        url,
        item_selector=board["item_selector"],
        field_selectors=board.get("fields", {}),
        link_selector=board.get("link_selector"),
        wait_selector=board.get("wait_selector"),
        limit=config.get("max_per_source") or 100,
        detail_fields=board.get("detail_fields"),
        detail_limit=board.get("detail_limit"),
    )

    jobs = []
    for rec in records:
        location = rec.get("location", "")
        jobs.append({
            "title": rec.get("title", ""),
            "company": rec.get("company", "") or board.get("name", ""),
            "location": location,
            "remote": "remote" in location.lower(),
            "salary": rec.get("salary", ""),
            "url": rec.get("url", ""),
            "posted_date": parse_posted(rec.get("posted", "")),
            "description": rec.get("description", ""),
            "source": f"browser:{board.get('name', 'board')}",
        })
    return jobs
