"""Search Orchestrator: coordinates event discovery, weather, and venue search."""

import json
from datetime import date, datetime

from db.database import (
    create_search, update_search_status, insert_event,
    insert_weather_day, get_city_by_id, get_events_for_search,
    get_weather_for_search,
)
from scrapers.google_search import search_events
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

    try:
        if progress_callback:
            progress_callback("Searching Google for events...", 0.1)

        # Step 1: Google Search for events
        search_results = search_events(
            city=city["name"],
            country=city["country"],
            date_from=date_from,
            date_to=date_to,
            segments=segments if segments else None,
        )

        if progress_callback:
            progress_callback(
                f"Found {len(search_results)} search results. Scraping pages...", 0.3
            )

        # Step 2: Scrape top results
        urls = [r["link"] for r in search_results if r.get("link")]
        scraped_pages = scrape_multiple(urls, max_pages=12)

        if progress_callback:
            progress_callback(
                f"Scraped {len(scraped_pages)} pages. Extracting events with AI...", 0.5
            )

        # Step 3: AI-parse events from scraped pages
        events = parse_events_batch(
            pages=scraped_pages,
            city=city["name"],
            date_from=date_from,
            date_to=date_to,
        )

        if progress_callback:
            progress_callback(
                f"Found {len(events)} events. Fetching weather data...", 0.7
            )

        # Step 4: Store events
        for event in events:
            insert_event(search_id, event)

        # Step 5: Fetch weather
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

        update_search_status(search_id, "completed")

    except Exception as e:
        update_search_status(search_id, "failed")
        raise e

    return search_id


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
