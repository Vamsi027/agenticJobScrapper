# agenticProj — Job Matching

A daily scraper collects job postings from many job sites into Supabase, unfiltered. Anyone can sign in, upload a resume, and see every stored posting ranked against their own skills, experience, target roles and locations.

## How it works

```
                 daily (GitHub Actions)                              in the browser (GitHub Pages)
┌───────────────────────────────────────────────────┐     ┌──────────────────────────────────────────────┐
│ applicants' target roles + cities -> search queries│     │ sign in (email link) -> upload resume (PDF)  │
│ fetch all sources -> clean + dedupe                │     │   -> parse-resume Edge Function (Claude)     │
│   -> upsert into job_postings (no filtering)       │     │   -> applicant row                           │
└───────────────────────────────────────────────────┘     │ match_jobs() ranks job_postings for the user │
                         │                                 └──────────────────────────────────────────────┘
                         └──────────────── Supabase (Postgres + Auth + Storage) ─────┘
```

### Supabase objects

| Object | What it holds | Who can access it |
|---|---|---|
| `job_postings` | Every scraped posting: title, company, location, remote, salary, url, full description, posted date, years required, source, first/last seen | Everyone can read; only the scraper (secret key) writes |
| `applicant` | One row per user: name, headline, years of experience, target roles, locations, remote preference, weighted skills, title words, max years a job may ask for, min score, resume path | Each user reads/edits only their own row; rows are created by the Edge Function |
| `match_jobs(p_max_days, p_include_ineligible, p_limit)` | Scores postings for the signed-in user: sum of matched skill weights, and the reasons a job doesn't fit (title, seniority, years, score, location) | Signed-in users |
| `ingest_jobs(jobs)` | Upsert used by the scraper; returns which postings are new | Scraper only |
| `resumes` bucket | Uploaded resumes, `resumes/<user id>/resume.pdf` | Each user only their own folder |
| `parse-resume` Edge Function | Sends the resume to Claude (`claude-opus-5-5`, structured output) and saves the profile | Signed-in users |

Schema and policies: [supabase/migrations/](supabase/migrations/). The first applicant (the profile that used to live in `config/config.json`) is seeded with an email address and attaches to that account on its first sign-in.

### Sources

| Source | Access method | What is fetched | Auth |
|---|---|---|---|
| RemoteOK, Remotive, Jobicy | Public JSON APIs | Everything they return (Remotive's API caps at 10) | None |
| Hacker News "Who is hiring" | Algolia API | Every top-level comment in the latest thread | None |
| Greenhouse / Lever boards | Public JSON per company | Every posting, worldwide | None |
| Browser board (Workday) | Playwright | First results page of one employer | None |
| Adzuna | API | One search per (target role, city) | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` (free) |
| JSearch (RapidAPI) | API over Google for Jobs | One search per (role, city) or (role, remote) | `RAPIDAPI_KEY` (free tier) |
| LinkedIn (Bright Data) | Web Scraper API, keyword discovery | Same searches, one snapshot per run | `BRIGHTDATA_API_KEY` (paid, per record) |

The search-based sources (Adzuna, JSearch, Bright Data) need search terms, and they cost quota or money per query. They are built from **all applicants combined**: each applicant's target roles x cities, plus a remote search per role. Searches shared by more applicants come first, then applicants take turns, and each source stops at its `max_queries` ([jobscraper/settings.py](jobscraper/settings.py)). So the cost grows with the number of distinct roles and places, not with the number of users.

Bright Data bills per record: at most `max_queries x limit_per_input` (4 x 25 = 100) LinkedIn records per run. If a run times out, the snapshot keeps running on Bright Data's side and is still billed. LinkedIn's terms prohibit scraping; Bright Data collects only publicly visible postings, but whether to use it is your call.

Postings are deduplicated on company + title + location. A posting that no source has returned for `prune_after_days` (60) is deleted.

### Matching

A posting **fits** a user when:

- its title contains one of their `title_include` words (e.g. engineer, developer), if they have any;
- it doesn't ask for more than `max_years_required` years;
- the sum of the weights of their skills found in the title + description is at least `min_score`;
- it is in one of their cities, or it is remote and either names one of their `remote_allowed_regions` or names no place.

Seniority isn't filtered: senior and lead roles show up when they match. Skills are matched as whole terms through a full-text index, so `java` doesn't match `javascript` but does match `Java/Kotlin`, and `node.js`, `c++`, `c#`, `ci/cd` work as written. Users edit roles, locations, skill weights, the minimum score and the years limit directly in the sidebar; changes save automatically and re-rank the list. Uploading a new resume rebuilds the profile.

## Setup

### 1. Supabase

1. Apply the migrations in [supabase/migrations/](supabase/migrations/), in filename order: SQL editor, or `supabase db push` with the Supabase CLI.
2. Deploy the Edge Function and give it a Claude API key:
   ```sh
   supabase functions deploy parse-resume --no-verify-jwt   # the function verifies the user itself
   supabase secrets set ANTHROPIC_API_KEY=sk-ant-...
   ```
3. **Authentication -> URL Configuration**: set **Site URL** to the GitHub Pages URL and add `http://localhost:8000` and the Pages URL under **Redirect URLs**. Magic links redirect only to listed URLs.
4. For more than a handful of users, set up custom SMTP (**Authentication -> Emails**). The built-in email sender is rate-limited to a few emails per hour.

### 2. Scraper keys

The scraper writes with a **secret** key (Project Settings -> API Keys -> Secret keys). It bypasses row-level security: keep it out of the browser and out of git.

```powershell
setx SUPABASE_URL        "https://<project-ref>.supabase.co"
setx SUPABASE_SECRET_KEY "sb_secret_..."
setx ADZUNA_APP_ID       "your-app-id"       # https://developer.adzuna.com/signup
setx ADZUNA_APP_KEY      "your-app-key"
setx RAPIDAPI_KEY        "your-rapidapi-key" # JSearch free plan on RapidAPI
setx BRIGHTDATA_API_KEY  "your-key"          # Bright Data -> Account settings -> API keys
```

A missing source key just skips that source. Open a new terminal after `setx`.

### 3. Run

```sh
pip install -r requirements.txt
playwright install chromium                     # only for the browser board

python -m jobscraper                            # full run: query applicants, scrape, upsert
python -m jobscraper --only remoteok,greenhouse # just these sources
python -m jobscraper --dry-run                  # fetch and count; doesn't touch Supabase
python -m jobscraper.web                        # UI at http://localhost:8000
```

The UI's Supabase URL and publishable key are in [jobscraper/static/config.js](jobscraper/static/config.js). Both are safe to publish.

## Hosting

- [.github/workflows/daily-scrape.yml](.github/workflows/daily-scrape.yml) runs the scraper every day at **07:00 IST**. Add `SUPABASE_URL`, `SUPABASE_SECRET_KEY` and any source keys under **Settings -> Secrets and variables -> Actions**. **Actions -> Daily job scrape -> Run workflow** runs it now.
- [.github/workflows/pages.yml](.github/workflows/pages.yml) publishes `jobscraper/static` to GitHub Pages when it changes (**Settings -> Pages -> Source: GitHub Actions**).
- GitHub pauses scheduled workflows after 60 days without repository activity. The scraper no longer commits data, so re-enable the workflow if that happens.

**Privacy:** resumes and profiles are private to each user (row-level security and storage policies). Job postings are public. Resumes are sent to the Claude API for parsing.

## Project layout

```
agenticProj/
├── .github/workflows/
│   ├── daily-scrape.yml       Daily scrape into Supabase
│   └── pages.yml              Deploy the UI to GitHub Pages
├── supabase/
│   ├── migrations/            Schema, RLS policies, match_jobs(), storage bucket, first applicant
│   └── functions/parse-resume Edge Function: resume -> applicant profile via Claude
├── jobscraper/                Python package
│   ├── __main__.py            Entry point for `python -m jobscraper`
│   ├── pipeline.py            Applicants -> queries -> fetch -> normalize -> upsert
│   ├── settings.py            Enabled sources, company lists, per-source limits
│   ├── queries.py             Builds search targets from all applicants
│   ├── db.py                  Supabase REST client (applicants, ingest, prune)
│   ├── normalize.py           Cleanup, dates, years required, dedupe
│   ├── sites.py               API endpoint constants
│   ├── fetchers.py            HTTP (httpx) + browser (Playwright) helpers
│   ├── web.py                 Local static server for the UI
│   ├── static/                UI: index.html, app.js, style.css, config.js
│   └── sources/               remote_boards/, company_boards/, aggregators/, browser/
├── requirements.txt
└── README.md
```

To add a source: create a module with `fetch(config)` in the matching `sources/` subfolder, register it in `sources/__init__.py`, and enable it in `settings.py`. Search-based sources read `config["search_targets"]`.
