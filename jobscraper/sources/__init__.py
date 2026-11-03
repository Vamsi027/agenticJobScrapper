"""Registry of fetchable sources, keyed by the names used in config "sources".

Each module exposes fetch(config) -> list of raw job dicts.
"""

from jobscraper.sources.aggregators import adzuna, brightdata_linkedin, jsearch
from jobscraper.sources.browser import browser_board
from jobscraper.sources.company_boards import greenhouse, lever
from jobscraper.sources.remote_boards import hn, jobicy, remoteok, remotive

SOURCES = {
    "remoteok": remoteok,
    "remotive": remotive,
    "jobicy": jobicy,
    "hn": hn,
    "greenhouse": greenhouse,
    "lever": lever,
    "adzuna": adzuna,
    "jsearch": jsearch,
    "brightdata_linkedin": brightdata_linkedin,
    "browser_board": browser_board,
}
