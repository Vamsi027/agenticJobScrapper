"""Hacker News "Ask HN: Who is hiring?" threads via the Algolia API.

Comments are freeform; by convention the first line is
"Company | Role | Location | ...", which we parse best-effort.
"""

import re
from html import unescape

from jobscraper.fetchers import get_json
from jobscraper.sites import HN_ALGOLIA_API as SEARCH_URL


def _latest_thread_id():
    data = get_json(SEARCH_URL, params={
        "query": "Ask HN: Who is hiring?",
        "tags": "story,author_whoishiring",
        "hitsPerPage": 1,
    })
    hits = data.get("hits", [])
    return hits[0]["objectID"] if hits else None


def _first_line(comment_html):
    text = re.sub(r"<p>", "\n", comment_html or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return text.strip().splitlines()[0].strip() if text.strip() else ""


def fetch(config):
    limit = config.get("max_per_source") or 1000  # Algolia's per-page maximum
    thread_id = _latest_thread_id()
    if not thread_id:
        return []

    hits, page = [], 0
    while len(hits) < limit:
        data = get_json(SEARCH_URL, params={
            "tags": f"comment,story_{thread_id}",
            "hitsPerPage": min(limit, 1000),
            "page": page,
        })
        # Only top-level comments are job posts; replies are discussion.
        hits += [h for h in data.get("hits", []) if str(h.get("parent_id")) == str(thread_id)]
        page += 1
        if page >= data.get("nbPages", 0):
            break

    jobs = []
    for hit in hits[:limit]:
        comment = hit.get("comment_text") or ""
        header = _first_line(comment)
        if not header:
            continue
        parts = [p.strip() for p in header.split("|")]
        company = parts[0] if parts else ""
        title = parts[1] if len(parts) > 1 else header
        location = parts[2] if len(parts) > 2 else ""
        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "remote": "remote" in comment.lower(),
            "salary": "",
            "url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
            "posted_date": (hit.get("created_at") or "")[:10],
            "description": comment,
            "source": "hn",
        })
    return jobs
