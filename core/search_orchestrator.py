"""Search Orchestrator: coordinates event discovery, weather, and venue search."""

import json
from datetime import date, datetime
from urllib.parse import urlparse

from db.database import (
    create_search, update_search_status, insert_event,
    insert_weather_day, get_city_by_id, get_events_for_search,
    get_weather_for_search, save_debug_log,
)
from scrapers.google_search import search_events, get_direct_urls
from scrapers.page_scraper import scrape_multiple
from scrapers.event_parser import parse_events_batch
from integrations.weather.open_meteo import get_weather_for_range


def run_search(
    city_id: int,
    date_from: str,
    date_to: str,
    segments: list[str],
    radius_km: int = 20,
    progress_callback=None,
) -> int:
    """Run a full search for events + weather in a city/date range.

    Returns the search_id for retrieving results.
    """
    city = get_city_by_id(city_id)
    if not city:
        raise ValueError(f"City not found: {city_id}")

    # Create search record
    search_id = create_search(city_id, date_from, date_to, segments, radius_km)

    # Debug log collects all pipeline info
    debug = {
        "queries": [],
        "search_results_total": 0,
        "direct_urls_scraped": 0,
        "scrape_attempts": [],
        "scrape_success": 0,
        "scrape_fail": 0,
        "ai_input_pages": 0,
        "events_extracted": 0,
        "events_by_source": {},
        "top_domains": {},
    }

    try:
        if progress_callback:
            progress_callback("Searching Google for events...", 0.1)

        # Step 1: Google Search for events (now returns debug info too)
        search_results, query_debug = search_events(
            city=city["name"],
            country=city["country"],
            date_from=date_from,
            date_to=date_to,
            segments=segments if segments else None,
        )
        debug["queries"] = query_debug
        debug["search_results_total"] = len(search_results)

        if progress_callback:
            progress_callback(
                f"Found {len(search_results)} search results. Scraping pages...", 0.2
            )

        # Step 2a: Scrape direct known listing URLs (guaranteed high-value)
        direct_urls = get_direct_urls(city["name"])
        direct_pages = scrape_multiple(direct_urls, max_pages=len(direct_urls)) if direct_urls else []
        debug["direct_urls_scraped"] = len(direct_pages)
        for durl in direct_urls:
            debug["scrape_attempts"].append({
                "url": durl,
                "domain": _extract_domain(durl),
                "success": any(p["url"] == durl for p in direct_pages),
                "source": "direct",
            })

        if progress_callback:
            progress_callback(
                f"Scraped {len(direct_pages)} direct sources. Scraping Google results...", 0.35
            )

        # Step 2b: Scrape top Google results — track success/fail per URL
        urls = [r["link"] for r in search_results if r.get("link")]
        # Exclude URLs we already scraped directly
        direct_url_set = set(direct_urls)
        urls = [u for u in urls if u not in direct_url_set]
        scraped_pages = scrape_multiple(urls, max_pages=25)

        # Build scrape debug info
        scraped_urls = {p["url"] for p in scraped_pages}
        for url in urls[:25]:
            success = url in scraped_urls
            debug["scrape_attempts"].append({
                "url": url,
                "domain": _extract_domain(url),
                "success": success,
            })
        debug["scrape_success"] = len(scraped_pages)
        debug["scrape_fail"] = min(len(urls), 25) - len(scraped_pages)

        if progress_callback:
            progress_callback(
                f"Scraped {len(scraped_pages) + len(direct_pages)} pages. Extracting events with AI...", 0.50
            )

        # Step 3: Build combined content for AI parsing
        all_pages = list(direct_pages) + list(scraped_pages)

        # Bundle Serper snippets as an extra "page" for AI to parse
        serper_text = _build_serper_digest(search_results)
        if serper_text:
            all_pages.append({
                "url": "google-search-results",
                "content": serper_text,
            })

        debug["ai_input_pages"] = len(all_pages)

        # Step 4: AI-parse events from all sources
        events = parse_events_batch(
            pages=all_pages,
            city=city["name"],
            date_from=date_from,
            date_to=date_to,
        )

        debug["events_extracted"] = len(events)

        # Track events per source domain
        source_counts = {}
        for e in events:
            src_url = e.get("source_url") or ""
            domain = _extract_domain(src_url) if src_url else "serper-snippet"
            source_counts[domain] = source_counts.get(domain, 0) + 1
        debug["events_by_source"] = source_counts

        # Track top domains from all search results
        domain_counts = {}
        for r in search_results:
            dom = _extract_domain(r.get("link", ""))
            if dom:
                domain_counts[dom] = domain_counts.get(dom, 0) + 1
        debug["top_domains"] = dict(
            sorted(domain_counts.items(), key=lambda x: -x[1])[:20]
        )

        if progress_callback:
            progress_callback(
                f"Found {len(events)} events. Fetching weather data...", 0.8
            )

        # Step 5: Store events
        for event in events:
            insert_event(search_id, event)

        # Step 6: Fetch weather
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
        weather_data = get_weather_for_range(
            latitude=city["latitude"],
            longitude=city["longitude"],
            date_from=d_from,
            date_to=d_to,
        )

        for w in weather_data:
            insert_weather_day(search_id, w)

        if progress_callback:
            progress_callback("Search complete!", 1.0)

        # Save debug log
        save_debug_log(search_id, debug)

        update_search_status(search_id, "completed")

    except Exception as e:
        # Save whatever debug we have even on failure
        debug["error"] = str(e)
        try:
            save_debug_log(search_id, debug)
        except Exception:
            pass
        update_search_status(search_id, "failed")
        raise e

    return search_id


def _extract_domain(url: str) -> str:
    """Extract domain from URL, e.g. 'ra.co' from 'https://ra.co/events/...'."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or ""
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _build_serper_digest(search_results: list[dict]) -> str:
    """Build a text digest from Serper search result snippets.

    This gives the AI parser data to work with even when scraping fails,
    since Serper returns titles, snippets, and sometimes dates/venues.
    """
    if not search_results:
        return ""

    lines = ["=== GOOGLE SEARCH RESULTS ===\n"]
    for i, r in enumerate(search_results[:30], 1):
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        link = r.get("link", "")
        source = r.get("source", "")
        lines.append(f"[{i}] {title}")
        if snippet:
            lines.append(f"    {snippet}")
        if link:
            lines.append(f"    URL: {link}")
        lines.append("")

    text = "\n".join(lines)
    return text if len(text) > 50 else ""


def get_results_by_date(search_id: int) -> dict:
    """Get search results organized by date.

    Returns dict with dates as keys, each containing:
    - events: list of events for that date
    - weather: weather data for that date
    - competition_level: low/medium/high based on event count
    """
    events = get_events_for_search(search_id)
    weather_days = get_weather_for_search(search_id)

    # Index weather by date
    weather_by_date = {w["date"]: w for w in weather_days}

    # Group events by date
    events_by_date: dict[str, list] = {}
    for event in events:
        d = event.get("date")
        if d:
            events_by_date.setdefault(d, []).append(event)

    # Build combined results
    all_dates = sorted(set(list(events_by_date.keys()) + list(weather_by_date.keys())))
    results = {}

    for d in all_dates:
        day_events = events_by_date.get(d, [])
        day_weather = weather_by_date.get(d)
        event_count = len(day_events)

        # Determine competition level
        if event_count == 0:
            competition = "none"
        elif event_count <= 2:
            competition = "low"
        elif event_count <= 5:
            competition = "medium"
        else:
            competition = "high"

        # Count by segment
        segment_counts = {}
        for e in day_events:
            seg = e.get("segment") or "other"
            segment_counts[seg] = segment_counts.get(seg, 0) + 1

        has_own_event = any(e.get("is_own_event") for e in day_events)

        results[d] = {
            "date": d,
            "day_name": _day_name(d),
            "events": day_events,
            "event_count": event_count,
            "competition_level": competition,
            "segment_counts": segment_counts,
            "weather": day_weather,
            "has_own_event": has_own_event,
        }

    return results


def _day_name(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%A")
    except Exception:
        return ""
