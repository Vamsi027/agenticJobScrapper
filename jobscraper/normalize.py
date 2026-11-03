"""Schema cleanup, keyword/location filtering, and deduplication."""

import re
from datetime import date, timedelta
from html import unescape

SCHEMA_FIELDS = (
    "title", "company", "location", "remote", "salary",
    "url", "posted_date", "description_snippet", "source",
)

SNIPPET_LEN = 300


def clean_text(value):
    """Unescape entities, strip HTML tags, collapse whitespace."""
    if value is None:
        return ""
    text = unescape(unescape(str(value)))  # Greenhouse double-escapes its HTML
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_job(raw):
    job = {field: raw.get(field, "") for field in SCHEMA_FIELDS}
    for field in ("title", "company", "location", "salary", "url", "source"):
        job[field] = clean_text(job[field])
    job["remote"] = bool(raw.get("remote")) or "remote" in job["location"].lower()
    job["posted_date"] = clean_text(job["posted_date"])[:10]  # keep ISO date part
    job["description_snippet"] = clean_text(job["description_snippet"])
    return job


def dedupe_key(job):
    if job["company"] and job["title"]:
        return f"{job['company'].lower()}|{job['title'].lower()}"
    return job["url"].lower().rstrip("/")


def _mentions(text, terms):
    return any(re.search(rf"\b{re.escape(t.lower())}\b", text) for t in terms)


def remote_open_to_us(location, allowed):
    """A remote job counts if it names an allowed region (worldwide, India, APAC...)
    or names no place at all. "Remote - US" or "Remote, Kansas" is rejected,
    since those are usually restricted to that country."""
    loc = location.lower()
    if _mentions(loc, allowed):
        return True
    return not re.sub(r"\bremote\b|[^a-z]", "", loc)


def location_ok(location, remote, locations, remote_only=False, remote_allowed=()):
    """True if a posting's location fits the configured locations/remote rules."""
    remote_ok = remote and remote_open_to_us(location, remote_allowed)
    if remote_only and not remote_ok:
        return False
    if locations:
        places = [loc for loc in locations if loc.lower() != "remote"]
        want_remote = len(places) < len(locations)
        in_place = any(p.lower() in location.lower() for p in places)
        return in_place or (want_remote and remote_ok)
    return True


def config_location_ok(location, remote, config):
    """location_ok() using the locations/remote settings from config.json."""
    locations = config.get("locations") or ([config["location"]] if config.get("location") else [])
    return location_ok(location, remote, locations, config.get("remote_only", False),
                       config.get("remote_allowed_regions", []))


def matches(job, keywords, locations, remote_only, remote_allowed=()):
    if not location_ok(job["location"], job["remote"], locations, remote_only, remote_allowed):
        return False
    if keywords:
        haystack = f"{job['title']} {job['description_snippet']}".lower()
        return any(kw.lower() in haystack for kw in keywords)
    return True


# "3+ years", "2-5 years", "4 to 6 yrs" -> captures the lower bound
YEARS_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b")


def min_years_required(text):
    years = [int(y) for y in YEARS_RE.findall(text) if 0 < int(y) <= 20]
    return min(years) if years else None


def profile_score(job, profile):
    """Return the resume-match score, or None if the job fails the profile's hard filters.

    Hard filters: title must contain a title_include term and no title_exclude
    term; the posting must not require more than max_years_required years.
    Score: sum of weights of profile skills found in the title + description.
    """
    title = job["title"].lower()
    text = f"{title} {job['description_snippet'].lower()}"
    if not _mentions(title, profile.get("title_include", [])):
        return None
    if _mentions(title, profile.get("title_exclude", [])):
        return None
    max_years = profile.get("max_years_required")
    required = min_years_required(text)
    if max_years is not None and required is not None and required > max_years:
        return None
    return sum(w for skill, w in profile.get("skills", {}).items() if _mentions(text, [skill]))


def posted_within(posted_date, max_days_old, today=None):
    """True if an ISO posted_date is at most max_days_old days ago.
    Undated or unparseable postings are rejected, since their age is unknown."""
    if max_days_old is None:
        return True
    try:
        posted = date.fromisoformat(posted_date[:10])
    except ValueError:
        return False
    return posted >= (today or date.today()) - timedelta(days=max_days_old)


def normalize_and_filter(raw_jobs, config):
    keywords = config.get("keywords", [])
    locations = config.get("locations") or ([config["location"]] if config.get("location") else [])
    remote_only = config.get("remote_only", False)
    remote_allowed = config.get("remote_allowed_regions", [])
    profile = config.get("profile")
    max_days_old = config.get("max_days_old")

    seen = set()
    jobs = []
    for raw in raw_jobs:
        job = normalize_job(raw)
        if not job["title"] or not job["url"]:
            continue
        if not posted_within(job["posted_date"], max_days_old):
            continue
        # With a profile, skill scoring replaces the plain keyword filter.
        if not matches(job, [] if profile else keywords, locations, remote_only, remote_allowed):
            continue
        job["score"] = 0
        if profile:
            score = profile_score(job, profile)
            if score is None or score < profile.get("min_score", 1):
                continue
            job["score"] = score
        key = dedupe_key(job)
        if key in seen:
            continue
        seen.add(key)
        job["description_snippet"] = job["description_snippet"][:SNIPPET_LEN]
        jobs.append(job)
    jobs.sort(key=lambda j: j["score"], reverse=True)
    return jobs
