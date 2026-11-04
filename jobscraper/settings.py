"""Scraper settings: which sources run and how. Nothing here is user-specific.

What the search-based sources look for (Adzuna, JSearch, LinkedIn via Bright
Data) comes from the applicants in Supabase: see jobscraper.queries.
"""

SETTINGS = {
    # Per-source cap on postings kept per run. None = keep everything the source returns.
    "max_per_source": None,
    # Delete postings no source has returned for this many days. None = keep forever.
    "prune_after_days": 60,
    # Descriptions longer than this are cut (keeps the database small; scoring
    # rarely needs more than the first few thousand characters).
    "max_description_chars": 20000,

    "sources": {
        "remoteok": True,
        "remotive": True,
        "jobicy": True,
        "hn": True,
        "greenhouse": True,
        "lever": True,
        "adzuna": True,
        "jsearch": True,
        "brightdata_linkedin": True,
        "browser_board": True,
    },

    # Company boards: every posting is kept, wherever it is located.
    "greenhouse_companies": [
        "highradius", "zscaler", "coinbase", "newrelic", "gitlab", "samsara", "twilio",
        "databricks", "zenoti", "singlestore", "starburst", "netskope", "airbnb", "yugabyte",
        "sentinellabs", "fivetran", "turing",
    ],
    "lever_companies": ["zeta", "outreach", "cred", "jumpcloud", "mindtickle"],

    "jobicy_geos": ["anywhere", "apac", "emea", "usa", "europe"],

    # Search-based sources. Queries are built from applicants' target roles x
    # cities (plus a remote query per role and country), most-shared first,
    # capped by max_queries because each query costs quota or money.
    "adzuna": {
        "max_queries": 6,
        "max_days_old": 7,
        "results_per_page": 50,
    },
    "jsearch": {
        "max_queries": 5,          # free plan is ~200 requests/month
        "date_posted": "week",
    },
    "brightdata_linkedin": {
        "max_queries": 4,
        "limit_per_input": 25,     # billed per record: max_queries x limit_per_input
        "time_range": "Past week",
        "timeout_minutes": 10,
        "poll_seconds": 15,
    },

    # S&P Global's Workday careers site (JS-rendered). The data-automation-id
    # selectors work on any *.myworkdayjobs.com board: change name + url only.
    "browser_board": {
        "name": "spglobal",
        "url": "https://spgi.wd5.myworkdayjobs.com/SPGI_Careers",
        "item_selector": 'section[data-automation-id="jobResults"] li:has([data-automation-id="jobTitle"])',
        "fields": {
            "title": '[data-automation-id="jobTitle"]',
            "location": '[data-automation-id="locations"] dd',
            "posted": '[data-automation-id="postedOn"] dd',
        },
        "link_selector": '[data-automation-id="jobTitle"]',
        "wait_selector": '[data-automation-id="jobTitle"]',
        "detail_fields": {
            "description": '[data-automation-id="jobPostingDescription"]',
            "location": '[data-automation-id="locations"] dd',
        },
        "detail_limit": 20,
    },
}
