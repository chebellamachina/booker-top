"""Scrape event pages using Playwright (JS-heavy) or httpx+BS4 (static)."""

import httpx
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def scrape_page_static(url: str) -> str | None:
    """Scrape a page using simple HTTP request + BeautifulSoup.
    Good for static HTML pages."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        }
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script, style, nav, footer elements
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        # Get main content text
        text = soup.get_text(separator="\n", strip=True)

        # Truncate to avoid massive pages
        if len(text) > 15000:
            text = text[:15000] + "\n... [truncated]"

        return text

    except Exception as e:
        print(f"Static scrape failed for {url}: {e}")
        return None


def scrape_page_dynamic(url: str) -> str | None:
    """Scrape a JS-heavy page using Playwright headless browser.
    Use for sites that require JavaScript rendering (RA, Fever, etc.)."""
    if not HAS_PLAYWRIGHT:
        return scrape_page_static(url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
            })
            page.goto(url, timeout=20000, wait_until="domcontentloaded")

            # Wait a bit for JS to render
            page.wait_for_timeout(3000)

            # Get text content
            text = page.inner_text("body")
            browser.close()

            if len(text) > 15000:
                text = text[:15000] + "\n... [truncated]"

            return text

    except Exception as e:
        print(f"Dynamic scrape failed for {url}: {e}")
        return None


def scrape_page(url: str, use_playwright: bool = False) -> str | None:
    """Scrape a page. Auto-detects whether to use static or dynamic scraping."""
    # Sites that need Playwright (JS-heavy)
    js_heavy_domains = [
        "ra.co", "residentadvisor.net",
        "ffrfrr.com", "fever.co",
        "fourvenues.com",
        "xceed.me",
        "dice.fm",
    ]

    needs_js = use_playwright or any(domain in url for domain in js_heavy_domains)

    if needs_js:
        result = scrape_page_dynamic(url)
        if result:
            return result
        # Fallback to static if Playwright fails
        return scrape_page_static(url)
    else:
        return scrape_page_static(url)


def scrape_multiple(urls: list[str], max_pages: int = 15) -> list[dict]:
    """Scrape multiple pages and return their content.
    Limits to max_pages to avoid excessive scraping."""
    results = []
    for url in urls[:max_pages]:
        content = scrape_page(url)
        if content:
            results.append({
                "url": url,
                "content": content,
            })
    return results
