"""Central registry of job websites and their API endpoints.

Scoped to two targets: remote roles open to India, and on-site/hybrid
roles in Hyderabad, India.

Import the endpoint constants from here instead of hardcoding URLs in
source modules, e.g.:

    from job_sites import REMOTEOK_API

Endpoints with {placeholders} are templates — fill them with .format().
Sites under "key required" need an API key in env vars before use.
"""

# --- Active sources, no auth needed (implemented in jobscraper/sources/) -----

REMOTEOK_API = "https://remoteok.com/api"                                # remote only
REMOTIVE_API = "https://remotive.com/api/remote-jobs"                    # remote only
JOBICY_API = "https://jobicy.com/api/v2/remote-jobs"                     # remote; geo=anywhere/apac
HN_ALGOLIA_API = "https://hn.algolia.com/api/v1/search_by_date"          # mixed, mostly remote/US
GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
LEVER_API = "https://api.lever.co/v0/postings/{company}"

# --- Active sources, API key required (skipped when the key is missing) ------
# These are the main way to get Hyderabad jobs: they aggregate Indian boards.

# Adzuna India: country="in", where="Hyderabad". Env: ADZUNA_APP_ID, ADZUNA_APP_KEY
ADZUNA_API = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
# JSearch = Google for Jobs (covers LinkedIn, Naukri, Indeed, Glassdoor listings). Env: RAPIDAPI_KEY
JSEARCH_API = "https://jsearch.p.rapidapi.com/search-v2"  # "/search" was retired
JSEARCH_HOST = "jsearch.p.rapidapi.com"
# Bright Data Web Scraper API, "LinkedIn job listings" dataset. Env: BRIGHTDATA_API_KEY (paid, per record)
BRIGHTDATA_API = "https://api.brightdata.com/datasets/v3"
BRIGHTDATA_LINKEDIN_JOBS_DATASET = "gd_lpfll7v5hcqtkxl6l"

# --- Browser only: login wall or anti-bot, no public API ---------------------
# Not fetched directly; use JSearch (above) to see their listings legally.

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search/?keywords=python&location=Hyderabad%2C%20Telangana%2C%20India"
NAUKRI_JOBS_URL = "https://www.naukri.com/python-jobs-in-hyderabad"
INDEED_IN_JOBS_URL = "https://in.indeed.com/jobs?q=python&l=Hyderabad%2C+Telangana"
GLASSDOOR_IN_JOBS_URL = "https://www.glassdoor.co.in/Job/hyderabad-python-jobs-SRCH_IL.0,9_IC2865319_KO10,16.htm"
FOUNDIT_JOBS_URL = "https://www.foundit.in/srp/results?query=python&locations=Hyderabad"
INSTAHYRE_JOBS_URL = "https://www.instahyre.com/python-jobs-in-hyderabad/"
WELLFOUND_JOBS_URL = "https://wellfound.com/role/l/python-developer/hyderabad"
CUTSHORT_JOBS_URL = "https://cutshort.io/jobs/python-jobs-in-hyderabad"

# One row per site: homepage, API endpoint (None = browser only), auth needs, coverage.
JOB_SITES = {
    # API, no auth
    "remoteok":   {"name": "RemoteOK",           "website": "https://remoteok.com",          "api": REMOTEOK_API,   "auth": None, "covers": "remote"},
    "remotive":   {"name": "Remotive",           "website": "https://remotive.com",          "api": REMOTIVE_API,   "auth": None, "covers": "remote"},
    "jobicy":     {"name": "Jobicy",             "website": "https://jobicy.com",            "api": JOBICY_API,     "auth": None, "covers": "remote (anywhere/APAC)"},
    "hn":         {"name": "HN Who is hiring",   "website": "https://news.ycombinator.com",  "api": HN_ALGOLIA_API, "auth": None, "covers": "remote, some India"},
    "greenhouse": {"name": "Greenhouse boards",  "website": "https://boards.greenhouse.io",  "api": GREENHOUSE_API, "auth": None, "covers": "per company; Hyderabad + remote"},
    "lever":      {"name": "Lever postings",     "website": "https://jobs.lever.co",         "api": LEVER_API,      "auth": None, "covers": "per company; Hyderabad + remote"},
    # API, key required
    "adzuna":     {"name": "Adzuna India",       "website": "https://www.adzuna.in",         "api": ADZUNA_API,     "auth": "ADZUNA_APP_ID + ADZUNA_APP_KEY (free)", "covers": "Hyderabad"},
    "brightdata_linkedin": {"name": "LinkedIn via Bright Data", "website": "https://brightdata.com/products/web-scraper/linkedin", "api": BRIGHTDATA_API, "auth": "BRIGHTDATA_API_KEY (paid, per record)", "covers": "Hyderabad + remote"},
    "jsearch":    {"name": "JSearch (RapidAPI)", "website": "https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch", "api": JSEARCH_API, "auth": "RAPIDAPI_KEY (free tier)", "covers": "Hyderabad + remote"},
    # Browser only
    "linkedin":   {"name": "LinkedIn Jobs",      "website": LINKEDIN_JOBS_URL,     "api": None, "auth": "login wall; ToS prohibits scraping (fetched via Bright Data instead)", "covers": "Hyderabad + remote"},
    "naukri":     {"name": "Naukri",             "website": NAUKRI_JOBS_URL,       "api": None, "auth": "anti-bot; ToS prohibits scraping",  "covers": "Hyderabad"},
    "indeed":     {"name": "Indeed India",       "website": INDEED_IN_JOBS_URL,    "api": None, "auth": "Cloudflare anti-bot",               "covers": "Hyderabad"},
    "glassdoor":  {"name": "Glassdoor India",    "website": GLASSDOOR_IN_JOBS_URL, "api": None, "auth": "login wall after a few pages; anti-bot", "covers": "Hyderabad"},
    "foundit":    {"name": "foundit (Monster India)", "website": FOUNDIT_JOBS_URL, "api": None, "auth": "anti-bot; JS-rendered",             "covers": "Hyderabad"},
    "instahyre":  {"name": "Instahyre",          "website": INSTAHYRE_JOBS_URL,    "api": None, "auth": "login required to see/apply",       "covers": "Hyderabad"},
    "wellfound":  {"name": "Wellfound",          "website": WELLFOUND_JOBS_URL,    "api": None, "auth": "login required; anti-bot",          "covers": "Hyderabad + remote startups"},
    "cutshort":   {"name": "Cutshort",           "website": CUTSHORT_JOBS_URL,     "api": None, "auth": "login required to see details",     "covers": "Hyderabad"},
}
