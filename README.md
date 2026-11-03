# agenticProj — Job Scraping Workflow

An agentic pipeline that collects job postings from popular job sites, normalizes them into a single schema, and saves the results for review.

## Workflow overview

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌─────────────┐   ┌──────────┐
│ 1. Sources   │ → │ 2. Fetch      │ → │ 3. Parse      │ → │ 4. Normalize │ → │ 5. Output │
│ (site list,  │   │ (API / HTTP / │   │ (extract      │   │ + dedupe     │   │ (JSON/CSV/│
│  keywords)   │   │  web MCP)     │   │  job fields)  │   │  + filter    │   │  SQLite)  │
└─────────────┘   └──────────────┘   └──────────────┘   └─────────────┘   └──────────┘
```

### Stage 1 — Sources

Define search targets in `config/config.json`: keywords, `locations` (currently `["Hyderabad", "Remote"]`), and which sites to query. A remote job only counts if its location names a region in `remote_allowed_regions` (worldwide, India, APAC...) or no place at all, so "Remote - US" is dropped.

| Source | Access method | Covers | Auth |
|---|---|---|---|
| RemoteOK, Remotive, Jobicy | Public JSON APIs | Remote | None |
| Hacker News "Who is hiring" | Algolia API | Remote, some India | None |
| Greenhouse / Lever boards | Public JSON per company | Hyderabad + "Remote - India" | None |
| Adzuna India | API (`country=in`, `where=Hyderabad`) | Hyderabad | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` (free) |
| JSearch (RapidAPI) | API over Google for Jobs | Hyderabad + remote; includes LinkedIn/Naukri/Indeed listings | `RAPIDAPI_KEY` (free tier) |
| LinkedIn (Bright Data) | Bright Data Web Scraper API, keyword discovery | Hyderabad + remote India | `BRIGHTDATA_API_KEY` (paid, per record) |
| LinkedIn (direct), Naukri, Indeed India, Glassdoor, foundit, Instahyre, Wellfound, Cutshort | Browser only | Hyderabad | Login wall or anti-bot; not fetched directly (LinkedIn comes via Bright Data, the rest via JSearch) |

### Job age

`max_days_old` (default `5`) drops postings published more than that many days ago, and postings with no date. The aggregators are also asked for recent jobs only: `adzuna.max_days_old` is `5` and `jsearch.date_posted` is `"week"` (JSearch has no 5-day option). Greenhouse dates use `first_published`, not `updated_at`, because editing an old posting changes `updated_at`. Remove `max_days_old` to keep jobs of any age. The web UI's **Posted within** filter starts at the same value and can be widened to see older stored jobs.

### Resume profile (ranking)

The `profile` block in `config/config.json` filters and ranks jobs against the resume:

- `title_include` / `title_exclude`: the title must name an engineering role and must not be above the target level (staff, principal, lead, manager...).
- `max_years_required`: drops postings whose lowest "N+ years" requirement is higher than this.
- `skills`: weight per skill; a job's score is the sum of weights found in its title + description. Jobs below `min_score` are dropped.

Results are printed and exported highest score first (`score` column in the database/CSV). Remove the `profile` block to fall back to plain `keywords` matching.

### API keys

Adzuna and JSearch are skipped until their keys are set. Set them once as user environment variables (PowerShell), then open a new terminal:

```powershell
setx ADZUNA_APP_ID  "your-app-id"     # https://developer.adzuna.com/signup
setx ADZUNA_APP_KEY "your-app-key"
setx RAPIDAPI_KEY   "your-rapidapi-key"  # subscribe to JSearch's free plan on RapidAPI
```

```powershell
setx BRIGHTDATA_API_KEY "your-key"   # Bright Data control panel -> Account settings -> API keys
```

**LinkedIn via Bright Data** (`brightdata_linkedin` in config): each run starts one Bright Data keyword-discovery job covering every entry in `brightdata_linkedin.queries`, polls until it's ready (usually a few minutes, up to `timeout_minutes`), then downloads the results. Bright Data bills per record, so `limit_per_input` (default 25) caps a run at `limit_per_input x number of queries` records, 100 by default. Query fields: `keyword`, `location` (required), `country`, `time_range` (`Past 24 hours` / `Past week` / `Past month` / `Any time`), `experience_level` (e.g. `Entry level`, `Associate`, `Mid-Senior level`), `job_type`, `remote` (`Remote` / `On-site` / `Hybrid`), `company`. If a run times out, the job keeps running on Bright Data's side and is still billed. Raise `timeout_minutes` rather than re-running straight away. LinkedIn's terms prohibit scraping; Bright Data collects only publicly visible postings, but whether to use it is your call.

JSearch's free plan has a small monthly request quota; each run uses one request per entry in `jsearch.queries` (2 by default).

**Prefer APIs over HTML scraping wherever one exists** — they are faster, more stable, and don't break when the page layout changes.

### Stage 2 — Fetch

Two fetch strategies, chosen per source:

1. **Direct HTTP** (`requests` / `httpx`) for API-based sources — the default.
2. **Browser automation** for JavaScript-rendered sites — via a **web MCP server** (see below) or Playwright directly.

### Stage 3 — Parse

Extract a common set of fields from each posting: `title`, `company`, `location`, `remote`, `salary`, `url`, `posted_date`, `description_snippet`, `source`.

### Stage 4 — Normalize, dedupe, filter

- Lowercase/trim fields, parse dates to ISO format.
- Dedupe on `(company, title)` or canonical URL — the same job often appears on multiple boards.
- Apply keyword/location filters from the config.

### Stage 5 — Output

Append results to `data/jobs.sqlite` (or `jobs.json` / `jobs.csv`). Only newly seen jobs are reported on each run, so the workflow can run daily as a cron/scheduled task.

## Can a web MCP be used as the scraping tool?

**Yes — and it's a good fit for the hard sites, but not for all of them.**

An MCP (Model Context Protocol) server that exposes browser/web tools — e.g. the **Playwright MCP server** (`@playwright/mcp`), a **Fetch MCP server**, or Claude Code's built-in browser tools — lets the agent:

- Navigate pages, click "Load more"/pagination, and fill search forms.
- Read fully JavaScript-rendered content (LinkedIn, Indeed, Glassdoor render jobs client-side, so plain `requests` gets nothing useful).
- Extract structured data by reading the page accessibility tree or running small page scripts.

**When to use web MCP:** JS-heavy sites, sites requiring login or interaction, and one-off exploratory scraping where the agent adapts to page structure on the fly.

**When NOT to use it:** sources with a JSON API (RemoteOK, Greenhouse, Lever, HN). Driving a browser through an LLM for those is slower, costs tokens, and adds flakiness — a plain HTTP call in Python is strictly better.

**Caveats:**

- Anti-bot systems (Cloudflare, LinkedIn's detection) can still block an MCP-driven browser; it is not a bypass tool.
- Respect each site's `robots.txt` and Terms of Service, use modest request rates, and prefer official APIs. LinkedIn's ToS in particular prohibits scraping.
- MCP-based scraping runs inside an agent session; for a scheduled headless pipeline, plain Playwright/`httpx` in Python is easier to automate.

**Recommended hybrid:** Python + `httpx` for all API sources (the bulk of the data), with a web MCP server as the agent-driven fallback for the few JS-rendered boards you care about.

## Requirements

- Python 3.10+
- `httpx` (or `requests`) for API fetching
- Optional: `playwright` or a web MCP server (e.g. `npx @playwright/mcp`) for browser-based sources
- Optional: `sqlite3` (stdlib) for storage

```sh
pip install -r requirements.txt
playwright install chromium   # only if using browser-based fetching
```

## Running it

Run from the project root:

```sh
python -m jobscraper                             # full pipeline with config/config.json
python -m jobscraper --config config/other.json  # alternate config
python -m jobscraper.export                      # export the database to data/jobs.csv (Excel-friendly)
python -m jobscraper.web                         # browse ranked jobs at http://127.0.0.1:8000
python -m jobscraper.web --export site           # static copy of the UI (what GitHub Pages serves)
```

### Web UI

`python -m jobscraper.web` (options: `--port`, `--host`, `--config`) serves a local page that lists every job in `data/jobs.sqlite`, ranked by resume-match score. Jobs are re-scored on each page load against the current `profile`, so after you edit `config/config.json`, refresh the page to see the new ranking. Each job card shows its rank, score, which profile skills matched, and years required. Jobs that fail the profile filters are hidden; turn on "Show jobs that don't fit profile" to see them along with the reason each one was dropped. Use the **Run scraper** button to fetch new postings without leaving the page.

Each run prints per-source counts and lists only jobs not seen in previous runs. Results accumulate in `data/jobs.sqlite`.

Edit `config/config.json` to change keywords, locations, remote-only filtering, enabled sources, and the Greenhouse/Lever company lists. The company lists were picked because they had Hyderabad or Remote-India openings (checked against the live APIs in Nov 2026; zenoti, singlestore, starburst, netskope, airbnb, yugabyte, sentinellabs, fivetran and turing were added then). Company boards return every posting worldwide, so `max_per_source` caps only the postings that pass the location filter.

### Browser board (JS-rendered sites)

`browser_board` uses Playwright (`pip install playwright && playwright install chromium`) to scrape one JS-rendered board defined in config. It's set up for **S&P Global's Workday careers site** (a large Hyderabad tech employer). Its `data-automation-id` selectors work on any `*.myworkdayjobs.com` board, so to switch to another Workday company you only change `name` and `url` (keep the search in `?q=`).

- `fields`: CSS selectors read from each list item (`title`, `location`, `posted`, ...). A "Posted 3 Days Ago" label becomes an ISO date.
- `detail_fields`: selectors read from each job's own page, which override the list value. Used to get the full description (without it, skill scoring only sees the title) and every location (the list just says "2 Locations"). This costs one page load per job, roughly 2s each, capped by `detail_limit`.

Large employers' boards skew senior, so many runs will add nothing that passes the profile. That's expected.

## Project layout

```
agenticProj/
├── .github/workflows/
│   └── daily-scrape.yml       Daily GitHub Actions run + GitHub Pages deploy
├── config/
│   └── config.json            Keywords, locations, resume profile, sources, company lists
├── data/                      Output: jobs.sqlite + ranked_jobs.csv (committed), jobs.csv (gitignored)
├── jobscraper/                Python package
│   ├── __main__.py            Entry point for `python -m jobscraper`
│   ├── pipeline.py            Orchestrates the 5 stages
│   ├── sites.py               Registry of job sites + API endpoint constants
│   ├── fetchers.py            HTTP (httpx) + browser (Playwright) fetch helpers
│   ├── normalize.py           Cleanup, location filter, resume scoring, dedupe
│   ├── storage.py             SQLite writer; returns only never-seen-before jobs
│   ├── export.py              SQLite -> CSV
│   ├── web.py                 Local web UI server (python -m jobscraper.web)
│   ├── static/                UI frontend: index.html, app.js, style.css
│   └── sources/
│       ├── __init__.py        SOURCES registry (config name -> module)
│       ├── remote_boards/     remoteok, remotive, jobicy, hn   (no auth)
│       ├── company_boards/    greenhouse, lever                (no auth, per company)
│       ├── aggregators/       adzuna, jsearch, brightdata_linkedin (API keys)
│       └── browser/           browser_board                    (Playwright)
├── requirements.txt           httpx, playwright
├── .gitignore
└── README.md
```

To add a source: create a module with `fetch(config)` in the matching `sources/` subfolder, add its URL to `sites.py`, register it in `sources/__init__.py`, and enable it under `sources` in the config.

## Hosting on GitHub (daily scheduled run)

`.github/workflows/daily-scrape.yml` runs the whole pipeline on GitHub Actions every day at **07:00 IST** (01:30 UTC; GitHub can start scheduled runs up to about 30 minutes late). Each run:

1. Installs `requirements.txt` and Playwright's Chromium.
2. Runs `python -m jobscraper` with your API keys taken from repository secrets.
3. Commits the updated `data/jobs.sqlite` back to the repo. That's how the next run knows which jobs are new, and the daily commits also stop GitHub from pausing the schedule after 60 days of inactivity.
4. Publishes a read-only copy of the web UI to GitHub Pages (`python -m jobscraper.web --export site`). On the hosted copy, the Run scraper button is hidden and the page shows when the data was last updated.

### One-time setup

1. Create an **empty** repository on github.com (no README or .gitignore).
2. Push this project from the project root:
   ```powershell
   git init -b main
   git add .
   git commit -m "Job scraper"
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. **Settings -> Secrets and variables -> Actions -> New repository secret**: add `BRIGHTDATA_API_KEY`, and `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `RAPIDAPI_KEY` if you have them. A missing key just skips that source.
4. **Settings -> Pages -> Build and deployment -> Source: GitHub Actions**.
5. **Actions -> Daily job scrape -> Run workflow** to test it now. When it finishes, the site is at `https://<you>.github.io/<repo>/`.

**Privacy:** a GitHub Pages site is public, even when the repo is private (private-repo Pages also needs a paid plan). Anyone with the URL can see the job list and the profile summary from `config.json` (the `profile._comment` text). In a public repo the config and database are visible too. Edit `_comment` if that's more than you want to share.

**Cost:** each run uses Bright Data credits (at most `limit_per_input x queries` LinkedIn records) and JSearch quota. To pause, use **Actions -> Daily job scrape -> ... -> Disable workflow**.

### Running locally on a schedule instead (Windows)

```sh
schtasks /Create /SC DAILY /ST 09:00 /TN "JobScraper" ^
  /TR "cmd /c cd /d C:\Users\underratedNoob\Documents\agenticProj && python -m jobscraper"
```

Because storage dedupes on `(company, title)`, each scheduled run reports only newly appeared jobs.

## Next steps

- Add more companies to `greenhouse_companies` / `lever_companies` as your targets change (check a board with `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs`).
- Point `browser_board` at another Workday employer if S&P Global keeps producing no matches.
