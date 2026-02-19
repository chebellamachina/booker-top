"""Google Search via Serper.dev API for event discovery."""

import os
import httpx


# ── Platform-specific sources by country ──────────────────────
# Each entry is (site_domain, search_terms) — search_terms help Google
# find actual event pages rather than just homepages.

PLATFORM_QUERIES = {
    "AR": [
        ("ra.co", "events {city}"),
        ("passline.com", "fiestas eventos {city}"),
        ("venti.com.ar", "eventos {city}"),
        ("allaccess.com.ar", "eventos fiestas {city}"),
        ("wearebombo.com", "fiestas {city}"),
        ("eventbrite.com.ar", "fiestas eventos noche {city}"),
        ("livepass.com.ar", "eventos {city}"),
        ("buenosaliens.com", "agenda fiestas {city}"),
        ("musicaelectronica.club", "eventos {city}"),
    ],
    "ES": [
        ("ra.co", "events {city}"),
        ("fourvenues.com", "discotecas fiestas {city}"),
        ("xceed.me", "fiestas clubs {city}"),
        ("feverup.com", "planes fiestas {city}"),
        ("dice.fm", "events {city}"),
        ("wearebombo.com", "fiestas {city}"),
    ],
    "US": [
        ("ra.co", "events {city}"),
        ("eventbrite.com", "parties nightlife {city}"),
        ("dice.fm", "events {city}"),
        ("shotgun.live", "events parties {city}"),
        ("feverup.com", "things to do parties {city}"),
        ("songkick.com", "concerts {city}"),
    ],
    "GB": [
        ("ra.co", "events {city}"),
        ("dice.fm", "events {city}"),
        ("shotgun.live", "events {city}"),
        ("skiddle.com", "club nights {city}"),
        ("feverup.com", "things to do {city}"),
        ("songkick.com", "concerts {city}"),
    ],
    "DE": [
        ("ra.co", "events {city}"),
        ("dice.fm", "events {city}"),
        ("eventbrite.de", "party nachtleben {city}"),
    ],
    "FR": [
        ("ra.co", "events {city}"),
        ("dice.fm", "events {city}"),
        ("shotgun.live", "soirées {city}"),
    ],
    "NL": [
        ("ra.co", "events {city}"),
        ("dice.fm", "events {city}"),
        ("partyflock.nl", "feesten {city}"),
    ],
    "BR": [
        ("ra.co", "events {city}"),
        ("eventbrite.com.br", "festas baladas {city}"),
        ("shotgun.live", "events {city}"),
        ("sympla.com.br", "festas eventos {city}"),
        ("wearebombo.com", "festas {city}"),
    ],
    "CL": [
        ("ra.co", "events {city}"),
        ("passline.com", "fiestas eventos {city}"),
        ("eventbrite.cl", "fiestas eventos {city}"),
        ("wearebombo.com", "fiestas {city}"),
    ],
    "CO": [
        ("ra.co", "events {city}"),
        ("eventbrite.co", "fiestas eventos rumbas {city}"),
        ("wearebombo.com", "fiestas {city}"),
    ],
    "MX": [
        ("ra.co", "events {city}"),
        ("eventbrite.com.mx", "fiestas eventos antros {city}"),
        ("boletia.com", "fiestas eventos {city}"),
        ("wearebombo.com", "fiestas {city}"),
    ],
    "PE": [
        ("ra.co", "events {city}"),
        ("joinnus.com", "fiestas eventos {city}"),
        ("wearebombo.com", "fiestas {city}"),
    ],
    "UY": [
        ("ra.co", "events {city}"),
        ("passline.com", "fiestas eventos {city}"),
        ("wearebombo.com", "fiestas {city}"),
    ],
    "_default": [
        ("ra.co", "events {city}"),
        ("eventbrite.com", "parties events {city}"),
        ("dice.fm", "events {city}"),
        ("feverup.com", "things to do {city}"),
        ("songkick.com", "concerts {city}"),
    ],
}

# ── Direct URLs to scrape per city (high-value listing pages) ──────
# These are scraped directly WITHOUT going through Google search,
# guaranteeing we always hit the best sources.

# NOTE on blocked sites: ra.co, passline.com and musicaelectronica.club all
# use Cloudflare bot protection that blocks both static and Playwright scraping.
# We still search them via Serper (Google has cached content), but don't waste
# time on direct scraping.  Focus direct URLs on sites that actually respond.

DIRECT_URLS = {
    "Buenos Aires": [
        "https://venti.com.ar/explorar",
        "https://www.eventbrite.com.ar/d/argentina--buenos-aires/fiestas/",
        "https://www.timeout.com/es/buenos-aires/agenda",
        "https://www.buenosaliens.com/",
        "https://www.allaccess.com.ar/list/Buenos+aires",
        "https://www.bresh.com",
    ],
    "Madrid": [
        "https://www.eventbrite.es/d/spain--madrid/fiestas/",
        "https://xceed.me/en/madrid/events",
    ],
    "Barcelona": [
        "https://www.eventbrite.es/d/spain--barcelona/fiestas/",
        "https://xceed.me/en/barcelona/events",
    ],
    "Ibiza": [
        "https://www.eventbrite.es/d/spain--ibiza/events/",
    ],
    "New York": [
        "https://www.eventbrite.com/d/ny--new-york/parties/",
        "https://www.songkick.com/metro-areas/7644-us-new-york/events",
    ],
    "Los Angeles": [
        "https://www.eventbrite.com/d/ca--los-angeles/parties/",
    ],
    "Miami": [
        "https://www.eventbrite.com/d/fl--miami/parties/",
    ],
    "London": [
        "https://www.eventbrite.co.uk/d/united-kingdom--london/nightlife/",
        "https://www.skiddle.com/whats-on/London/",
    ],
    "Berlin": [
        "https://www.eventbrite.de/d/germany--berlin/nachtleben/",
    ],
    "Paris": [
        "https://www.eventbrite.fr/d/france--paris/soirées/",
    ],
    "Amsterdam": [
        "https://www.eventbrite.nl/d/netherlands--amsterdam/nightlife/",
    ],
    "São Paulo": [
        "https://www.eventbrite.com.br/d/brazil--são-paulo/festas/",
    ],
    "Santiago": [
        "https://www.eventbrite.cl/d/chile--santiago/fiestas/",
    ],
    "Bogotá": [
        "https://www.eventbrite.co/d/colombia--bogotá/fiestas/",
    ],
    "México City": [
        "https://www.eventbrite.com.mx/d/mexico--ciudad-de-méxico/fiestas/",
    ],
    "Lima": [
        "https://www.eventbrite.com/d/peru--lima/fiestas/",
    ],
    "Montevideo": [
        "https://www.eventbrite.com/d/uruguay--montevideo/fiestas/",
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

    # ── General queries (English) — parties, clubs, nightlife ──
    for month in months_en:
        queries.append({"query": f"events parties {city} {month}", "type": "general"})
        queries.append({"query": f"club nights DJ sets {city} {month}", "type": "general"})
        queries.append({"query": f"nightlife parties {city} {month} tickets", "type": "general"})
        queries.append({"query": f"concerts live music {city} {month}", "type": "general"})

        # Segment-specific queries
        if segments:
            for seg in segments:
                queries.append({"query": f"{seg} party events {city} {month}", "type": "segment"})

    # ── Spanish queries ──
    if country in ("ES", "AR", "CL", "CO", "MX", "PE", "UY"):
        for month in months_es:
            queries.append({"query": f"fiestas eventos {city} {month}", "type": "general_es"})
            queries.append({"query": f"fiestas electrónicas DJ {city} {month}", "type": "general_es"})
            queries.append({"query": f"boliches clubs noche {city} {month}", "type": "general_es"})
            queries.append({"query": f"recitales shows {city} {month} entradas", "type": "general_es"})
            if segments:
                for seg in segments:
                    queries.append({"query": f"fiestas {seg} {city} {month}", "type": "segment_es"})

    # ── Portuguese queries for Brazil ──
    if country == "BR":
        month_names_pt = {
            1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
            5: "maio", 6: "junho", 7: "julho", 8: "agosto",
            9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
        }
        months_pt = set()
        current_pt = start
        while current_pt <= end:
            months_pt.add(f"{month_names_pt[current_pt.month]} {current_pt.year}")
            if current_pt.month == 12:
                current_pt = current_pt.replace(year=current_pt.year + 1, month=1)
            else:
                current_pt = current_pt.replace(month=current_pt.month + 1)
        for month in months_pt:
            queries.append({"query": f"festas baladas {city} {month}", "type": "general_pt"})
            queries.append({"query": f"eventos noite DJ {city} {month}", "type": "general_pt"})

    # ── Platform-specific queries ──
    # Format: "site:domain.com search_terms" (no month — ticketeras index by listing, not by date text)
    platform_entries = PLATFORM_QUERIES.get(country, PLATFORM_QUERIES["_default"])
    for domain, terms in platform_entries:
        q = f"site:{domain} {terms.format(city=city)}"
        queries.append({"query": q, "type": "platform"})

    # Cap total queries: 12 general + up to 9 platform = 21 max
    general = [q for q in queries if q["type"] != "platform"]
    platform = [q for q in queries if q["type"] == "platform"]

    # Deduplicate
    seen = set()
    deduped = []
    for q in general[:12] + platform[:9]:
        if q["query"] not in seen:
            seen.add(q["query"])
            deduped.append(q)

    return deduped


def get_direct_urls(city: str) -> list[str]:
    """Return known high-value listing URLs for a city (scraped directly, not via Google)."""
    return DIRECT_URLS.get(city, [])


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
        "Fever": f"https://feverup.com/en/{city.lower().replace(' ', '-')}",
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
