"""Local web UI: lists every stored job, ranked live against the config profile.

Usage:
    python -m jobscraper.web                 # http://127.0.0.1:8000
    python -m jobscraper.web --port 8080 --config config/other.json
    python -m jobscraper.web --export site   # static copy for GitHub Pages

Jobs are re-scored on every request, so editing the profile in config.json and
refreshing the page re-ranks everything (including jobs stored before scoring
existed).
"""

import argparse
import json
import re
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from jobscraper.normalize import _mentions, min_years_required, remote_open_to_us
from jobscraper.pipeline import DEFAULT_CONFIG
from jobscraper.storage import DB_PATH

STATIC_DIR = Path(__file__).resolve().parent / "static"
_run_lock = threading.Lock()


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evaluate(job, profile, remote_allowed):
    """Score a job against the profile and explain the result."""
    title = job["title"].lower()
    text = f"{title} {(job['description_snippet'] or '').lower()}"
    matched = {s: w for s, w in profile.get("skills", {}).items() if _mentions(text, [s])}
    reasons = []
    if profile.get("title_include") and not _mentions(title, profile["title_include"]):
        reasons.append("title is not an engineering role")
    excluded = [t for t in profile.get("title_exclude", []) if _mentions(title, [t])]
    if excluded:
        reasons.append(f"title contains '{excluded[0]}'")
    years = min_years_required(text)
    max_years = profile.get("max_years_required")
    if max_years is not None and years is not None and years > max_years:
        reasons.append(f"asks for {years}+ years")
    score = sum(matched.values())
    if score < profile.get("min_score", 1):
        reasons.append(f"score below {profile.get('min_score', 1)}")
    remote = bool(job["remote"])
    return {
        **job,
        "remote": remote,
        "remote_ok": remote and remote_open_to_us(job["location"] or "", remote_allowed),
        "score": score,
        "matched_skills": sorted(matched, key=lambda s: -matched[s]),
        "years_required": years,
        "eligible": not reasons,
        "reasons": reasons,
    }


def list_jobs(config):
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM jobs")]
    profile = config.get("profile") or {}
    allowed = config.get("remote_allowed_regions", [])
    jobs = [evaluate(r, profile, allowed) for r in rows]
    jobs.sort(key=lambda j: (j["eligible"], j["score"], j["posted_date"] or ""), reverse=True)
    for rank, job in enumerate((j for j in jobs if j["eligible"]), start=1):
        job["rank"] = rank
    return jobs


def profile_summary(config):
    profile = config.get("profile") or {}
    comment = profile.get("_comment", "")
    return {
        "summary": re.sub(r"^From resume \([^)]*\):\s*", "", comment),
        "skills": profile.get("skills", {}),
        "min_score": profile.get("min_score", 1),
        "max_years_required": profile.get("max_years_required"),
        "title_exclude": profile.get("title_exclude", []),
        "locations": config.get("locations", []),
        "max_days_old": config.get("max_days_old"),
        "max_possible": sum(profile.get("skills", {}).values()),
    }


def export_static(out_dir, config):
    """Write a read-only copy of the UI (HTML/JS/CSS + api/*.json) for static hosting."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(STATIC_DIR, out_dir)
    (out_dir / "api").mkdir()
    profile = {**profile_summary(config), "static": True,
               "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes")}
    jobs = list_jobs(config)
    (out_dir / "api" / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    (out_dir / "api" / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    print(f"Exported {len(jobs)} jobs to {out_dir}")


def make_handler(config_path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

        def _json(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/api/jobs", "/api/jobs.json"):
                return self._json(list_jobs(load_config(config_path)))
            if path in ("/api/profile", "/api/profile.json"):
                return self._json(profile_summary(load_config(config_path)))
            return super().do_GET()

        def do_POST(self):
            if urlparse(self.path).path != "/api/run":
                return self._json({"error": "not found"}, 404)
            if not _run_lock.acquire(blocking=False):
                return self._json({"error": "a scrape is already running"}, 409)
            try:
                from jobscraper.pipeline import run
                new_jobs = run(load_config(config_path))
                return self._json({"new": len(new_jobs)})
            except Exception as exc:
                return self._json({"error": str(exc)}, 500)
            finally:
                _run_lock.release()

        def log_request(self, code="-", size="-"):
            # Only log API calls; static file requests are noise.
            if "/api/" in self.path:
                super().log_request(code, size)

        def log_error(self, fmt, *args):
            # 404s etc. go through here; log_message itself is left unfiltered.
            if self.path != "/favicon.ico":
                super().log_error(fmt, *args)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Browse ranked jobs in the browser.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--export", metavar="DIR",
                        help="write a static copy of the UI to DIR instead of serving")
    args = parser.parse_args()

    if args.export:
        export_static(args.export, load_config(args.config))
        return

    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.config))
    print(f"Job board UI at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
