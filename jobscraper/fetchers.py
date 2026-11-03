"""Fetch strategies: plain HTTP for API sources, Playwright for JS-rendered boards."""

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) job-scraper (personal use)",
    "Accept": "application/json",
}


def get_json(url, params=None, headers=None, timeout=30):
    with httpx.Client(headers={**HEADERS, **(headers or {})},
                      follow_redirects=True, timeout=timeout) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def fetch_elements(url, item_selector, field_selectors, link_selector=None,
                   wait_selector=None, limit=100, timeout_ms=30000,
                   detail_fields=None, detail_limit=None):
    """Render a JS-heavy page in headless Chromium and extract one dict per item.

    field_selectors maps output field name -> CSS selector (text content is taken).
    link_selector, if given, is queried for an href on each item.
    detail_fields, if given, maps field name -> CSS selector on each item's own
    page (opened via its link). Matches are joined with ", " and override the
    list-page value, e.g. to get the full description or every location.
    Only the first detail_limit items get a detail visit (default: all).
    """
    from urllib.parse import urljoin

    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=timeout_ms)
        for item in page.query_selector_all(item_selector)[:limit]:
            record = {}
            for field, selector in field_selectors.items():
                el = item.query_selector(selector)
                record[field] = el.inner_text().strip() if el else ""
            if link_selector:
                link = item.query_selector(link_selector)
                href = (link.get_attribute("href") or "") if link else ""
                record["url"] = urljoin(url, href) if href else ""
            results.append(record)

        if detail_fields:
            detail = browser.new_page(user_agent=HEADERS["User-Agent"])
            first_selector = next(iter(detail_fields.values()))
            for record in results[:detail_limit]:
                if not record.get("url"):
                    continue
                try:
                    detail.goto(record["url"], timeout=timeout_ms, wait_until="domcontentloaded")
                    detail.wait_for_selector(first_selector, timeout=timeout_ms)
                except Exception as exc:
                    print(f"  detail page failed ({record['url']}): {exc.__class__.__name__}")
                    continue
                for field, selector in detail_fields.items():
                    texts = [el.inner_text().strip() for el in detail.query_selector_all(selector)]
                    if any(texts):
                        record[field] = ", ".join(t for t in texts if t)
        browser.close()
    return results
