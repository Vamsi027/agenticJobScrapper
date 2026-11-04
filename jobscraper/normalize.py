"""Schema cleanup and deduplication. No user-specific filtering happens here:
every posting is stored, and matching against a resume is done per user in
the database (public.match_jobs)."""

import re
from datetime import date
from html import unescape

YEARS_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b")


def clean_text(value):
    """Unescape entities, strip HTML tags, collapse whitespace."""
    if value is None:
        return ""
    text = unescape(unescape(str(value)))  # Greenhouse double-escapes its HTML
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def iso_date(value):
    """'2026-11-02T10:00:00Z' -> '2026-11-02'; anything unparseable -> None."""
    text = clean_text(value)[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def min_years_required(text):
    """Lowest "N+ years" / "2-5 years" / "4 to 6 yrs" figure in the text, or None."""
    years = [int(y) for y in YEARS_RE.findall(text.lower()) if 0 < int(y) <= 20]
    return min(years) if years else None


def dedupe_key(job):
    """Same company + title + location is one job, even if several boards list it.
    Location is part of the key because big employers post the same title in
    many cities, and each city matters to different users."""
    if job["company"] and job["title"]:
        return "|".join(job[f].lower() for f in ("company", "title", "location"))
    return job["url"].lower().rstrip("/")


def normalize_job(raw, max_description_chars=None):
    job = {field: clean_text(raw.get(field))
           for field in ("title", "company", "location", "salary", "url", "source")}
    description = clean_text(raw.get("description"))
    job["remote"] = bool(raw.get("remote")) or "remote" in job["location"].lower()
    job["posted_date"] = iso_date(raw.get("posted_date"))
    job["years_required"] = min_years_required(f"{job['title']} {description}")
    job["description"] = description[:max_description_chars] if max_description_chars else description
    job["dedupe_key"] = dedupe_key(job)
    return job


def normalize_all(raw_jobs, settings):
    """Clean every posting and drop duplicates (same company + title, or same URL)."""
    seen = set()
    jobs = []
    for raw in raw_jobs:
        job = normalize_job(raw, settings.get("max_description_chars"))
        if not job["title"] or not job["url"] or job["dedupe_key"] in seen:
            continue
        seen.add(job["dedupe_key"])
        jobs.append(job)
    return jobs
