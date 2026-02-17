"""Google Search via Serper.dev API for event discovery."""

import os
import httpx


# ── Platform-specific sources by country ──────────────────────

PLATFORM_QUERIES = {
    "AR": [
        "site:ra.co {city}",
        "site:passline.com {city}",
        "site:eventbrite.com.ar {city}",
        "site:livepass.com.ar {city}",
    ],
    "ES": [
        "site:ra.co {city}",
        "site:fourvenues.com {city}",
        "site:xceed.me {city}",
        "site:fever.co {city}",
        "site:dice.fm {city}",
    ],
    "US": [
        "site:ra.co {city}",
        "site:eventbrite.com {city}",
        "site:dice.fm {city}",
        "site:shotgun.live {city}",
    ],
    # Default for any other country
    "_default": [
        "site:ra.co {city}",
        "site:eventbrite.com {city}",
        "site:dice.fm {city}",
    ],
}


def search_events(
    city: str,
    country: str,
    date_from: str,
    date_to: str,
    segments: list[str] | None = None,
    num_results: int = 20,
) -> tuple[list[dict], list[dict]]:
    """Search Google for events in a city during a date range.

    Returns a tuple of:
    - list of search results with title, link, snippet
    - list of query debug entries [{query, result_count, source_type}]
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        results = _fallback_search(city, country, date_from, date_to, segments)
        debug = [{"query": "fallback (no API key)", "result_count": len(results), "source_type": "fallback"}]
        return results, debug

    queries = _build_queries(city, country, date_from, date_to, segments)
    all_results = []
    seen_urls = set()
    query_debug = []

    for query_info in queries:
        query_text = query_info["query"]
        source_type = query_info["type"]
        results = _serper_search(api_key, query_text, num_results=num_results)
        new_count = 0
        for r in results:
            url = r.get("link", "")
            if url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)
                new_count += 1

        query_debug.append({
            "query": query_text,
            "result_count": len(results),
            "new_unique": new_count,
            "source_type": source_type,
        })

    return all_results, query_debug


def _build_queries(
    city: str, country: str, date_from: str, date_to: str,
    segments: list[str] | None
) -> list[dict]:
    """Build search queries for event discovery.

    Returns list of {query: str, type: str} dicts.
    """
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

    # ── General queries (English) ──
    for month in months_en:
        queries.append({"query": f"events {city} {month}", "type": "general"})
        queries.append({"query": f"concerts parties {city} {month}", "type": "general"})
        queries.append({"query": f"nightlife {city} {month} what's on", "type": "general"})

        # Segment-specific queries
        if segments:
            for seg in segments:
                queries.append({"query": f"{seg} events {city} {month}", "type": "segment"})

    # ── Spanish queries for Spanish-speaking cities ──
    if country in ("ES", "AR"):
        for month in months_es:
            queries.append({"query": f"eventos {city} {month}", "type": "general_es"})
            queries.append({"query": f"fiestas {city} {month}", "type": "general_es"})
            if segments:
                for seg in segments:
                    queries.append({"query": f"eventos {seg} {city} {month}", "type": "segment_es"})

    # ── Platform-specific queries ──
    platform_templates = PLATFORM_QUERIES.get(country, PLATFORM_QUERIES["_default"])
    for month in months_en:
        for tmpl in platform_templates:
            q = tmpl.format(city=city) + f" {month}"
            queries.append({"query": q, "type": "platform"})

    # Cap total queries: 8 general + up to 6 platform = 14 max
    general = [q for q in queries if q["type"] != "platform"]
    platform = [q for q in queries if q["type"] == "platform"]

    # Deduplicate
    seen = set()
    deduped = []
    for q in general[:8] + platform[:6]:
        if q["query"] not in seen:
            seen.add(q["query"])
            deduped.append(q)

    return deduped


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
