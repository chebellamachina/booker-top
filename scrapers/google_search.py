"""Google Search via Serper.dev API for event discovery."""

import os
import httpx


def search_events(
    city: str,
    country: str,
    date_from: str,
    date_to: str,
    segments: list[str] | None = None,
    num_results: int = 20,
) -> list[dict]:
    """Search Google for events in a city during a date range.

    Returns a list of search results with title, link, snippet.
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return _fallback_search(city, country, date_from, date_to, segments)

    queries = _build_queries(city, country, date_from, date_to, segments)
    all_results = []
    seen_urls = set()

    for query in queries:
        results = _serper_search(api_key, query, num_results=num_results)
        for r in results:
            url = r.get("link", "")
            if url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    return all_results


def _build_queries(
    city: str, country: str, date_from: str, date_to: str,
    segments: list[str] | None
) -> list[str]:
    """Build search queries for event discovery."""
    # Parse month/year from dates for natural language queries
    from datetime import datetime
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")

    month_names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December",
    }
    month_names_es = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
    }

    months_en = set()
    months_es = set()
    current = start
    while current <= end:
        months_en.add(f"{month_names[current.month]} {current.year}")
        months_es.add(f"{month_names_es[current.month]} {current.year}")
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    queries = []

    for month in months_en:
        # General event queries
        queries.append(f"events {city} {month}")
        queries.append(f"concerts parties {city} {month}")
        queries.append(f"nightlife {city} {month} what's on")

        # Segment-specific queries
        if segments:
            for seg in segments:
                queries.append(f"{seg} events {city} {month}")

    # Spanish queries for Spanish-speaking cities
    if country in ("ES", "AR"):
        for month in months_es:
            queries.append(f"eventos {city} {month}")
            queries.append(f"fiestas {city} {month}")
            if segments:
                for seg in segments:
                    queries.append(f"eventos {seg} {city} {month}")

    return queries[:10]  # Cap at 10 queries to stay within free tier


def _serper_search(api_key: str, query: str, num_results: int = 20) -> list[dict]:
    """Execute a search via Serper.dev API."""
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": num_results,
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("organic", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "serper",
            })

        # Also capture event-specific results if available
        for item in data.get("events", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": f"{item.get('date', '')} - {item.get('address', '')}",
                "source": "serper_event",
            })

        return results

    except Exception as e:
        print(f"Serper search failed for '{query}': {e}")
        return []


def _fallback_search(
    city: str, country: str, date_from: str, date_to: str,
    segments: list[str] | None
) -> list[dict]:
    """Fallback when no Serper API key: return known event platform URLs
    that the user can manually check or that we can scrape directly."""
    platforms = {
        "Resident Advisor": f"https://ra.co/events/{city.lower().replace(' ', '-')}",
        "Eventbrite": f"https://www.eventbrite.com/d/{city.lower().replace(' ', '-')}/events/",
        "Fever": f"https://ffrfrr.com/en/{city.lower().replace(' ', '-')}/",
    }

    if country == "ES":
        platforms["Fourvenues"] = f"https://fourvenues.com/"
        platforms["Xceed"] = f"https://xceed.me/en/{city.lower().replace(' ', '-')}/events"

    if country == "AR":
        platforms["Passline"] = "https://www.passline.com/"

    return [
        {
            "title": f"{name} - Events in {city}",
            "link": url,
            "snippet": f"Check {name} for events in {city} from {date_from} to {date_to}",
            "source": "fallback",
        }
        for name, url in platforms.items()
    ]
