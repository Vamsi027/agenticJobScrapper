"""Pipeline: build search queries from the applicants in Supabase, run every
enabled source, clean/dedupe the results, and upsert them all into
public.job_postings. Matching to each user happens in the database.

Run with: python -m jobscraper [--only remoteok,greenhouse] [--dry-run]
"""

import argparse
from collections import Counter

from jobscraper import db
from jobscraper.normalize import normalize_all
from jobscraper.queries import search_targets
from jobscraper.settings import SETTINGS
from jobscraper.sources import SOURCES


def fetch_all(config, only=None):
    raw_jobs = []
    enabled = config.get("sources", {})
    for name, module in SOURCES.items():
        if only is not None and name not in only:
            continue
        if only is None and not enabled.get(name, False):
            continue
        print(f"Fetching {name} ...")
        try:
            found = module.fetch(config)
        except Exception as exc:
            print(f"  {name}: failed ({exc})")
            continue
        print(f"  {name}: {len(found)} postings")
        raw_jobs.extend(found)
    return raw_jobs


def run(settings=SETTINGS, only=None, dry_run=False):
    conn = None if dry_run else db.client()
    try:
        applicants = db.fetch_applicants(conn) if conn else []
        config = {**settings, "search_targets": search_targets(applicants)}
        print(f"{len(applicants)} applicants -> {len(config['search_targets'])} search targets")

        raw_jobs = fetch_all(config, only)
        jobs = normalize_all(raw_jobs, settings)
        print(f"\n{len(raw_jobs)} fetched, {len(jobs)} after dedupe")
        if dry_run:
            for source, n in Counter(j["source"].split(":")[0] for j in jobs).most_common():
                print(f"  {source}: {n}")
            return jobs

        new_jobs = db.ingest(conn, jobs)
        pruned = db.prune(conn, settings["prune_after_days"]) if settings.get("prune_after_days") else 0
        print(f"{len(new_jobs)} new, {pruned} stale removed (db total: {db.total_count(conn)})")
        for job in new_jobs[:50]:
            loc = f" [{job['location']}]" if job["location"] else ""
            print(f"- {job['title']} @ {job['company']}{loc} ({job['source']})")
        if len(new_jobs) > 50:
            print(f"... and {len(new_jobs) - 50} more")
        return new_jobs
    finally:
        if conn:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Scrape job boards into Supabase.")
    parser.add_argument("--only", help="comma-separated source names to run (ignores the enabled flags)")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and count, but don't touch Supabase (no applicant-based queries)")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    if only and (unknown := only - SOURCES.keys()):
        parser.error(f"unknown sources: {', '.join(sorted(unknown))}")
    run(only=only, dry_run=args.dry_run)
