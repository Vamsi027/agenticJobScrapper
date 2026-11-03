"""Pipeline: run every enabled source, normalize/filter/score/dedupe the
results, store them in SQLite, and print only the jobs not seen before.

Run with: python -m jobscraper [--config path]
"""

import argparse
import json
from pathlib import Path

from jobscraper import storage
from jobscraper.export import export_ranked
from jobscraper.normalize import normalize_and_filter
from jobscraper.sources import SOURCES

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "config.json"


def run(config):
    raw_jobs = []
    enabled = config.get("sources", {})
    for name, module in SOURCES.items():
        if not enabled.get(name, False):
            continue
        print(f"Fetching {name} ...")
        try:
            found = module.fetch(config)
        except Exception as exc:
            print(f"  {name}: failed ({exc})")
            continue
        print(f"  {name}: {len(found)} postings")
        raw_jobs.extend(found)

    jobs = normalize_and_filter(raw_jobs, config)
    new_jobs = storage.save_new(jobs)

    print(f"\n{len(raw_jobs)} fetched, {len(jobs)} after filters/dedupe, "
          f"{len(new_jobs)} new (db total: {storage.total_count()})")
    export_ranked(jobs)

    if new_jobs:
        print("\nNew jobs:")
        for job in new_jobs:
            loc = f" [{job['location']}]" if job["location"] else ""
            print(f"- [{job['score']:>2}] {job['title']} @ {job['company']}{loc} ({job['source']})")
            print(f"  {job['url']}")
    return new_jobs


def main():
    parser = argparse.ArgumentParser(description="Scrape job boards into SQLite.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help="Path to config.json")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)
    run(config)

