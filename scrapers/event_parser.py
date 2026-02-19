"""AI-assisted event parsing: extract structured events from scraped text."""

import os
import json
from openai import OpenAI


def parse_events_from_text(
    text: str,
    source_url: str,
    city: str,
    date_from: str,
    date_to: str,
) -> list[dict]:
    """Use OpenAI GPT to extract structured events from scraped page text."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _regex_fallback(text, source_url, city, date_from, date_to)

    prompt = f"""Extract all events from this text that take place in or near {city} between {date_from} and {date_to}.

For each event, return a JSON object with these fields:
- name: event name (string)
- date: event date in YYYY-MM-DD format (string)
- time: start time in HH:MM format if available (string or null)
- venue_name: venue name if mentioned (string or null)
- venue_address: venue address if mentioned (string or null)
- is_indoor: true/false/null based on venue type
- genre: main music genre (electronic, urban, pop, latin, rock, live-music, other)
- segment: one of: electronic, party/nightlife, urban/hip-hop, pop/commercial, latin/reggaeton, rock/indie, live-music, festival, other
- target_audience: audience type (underground, mainstream, premium, mass)
- price_range: price range if mentioned (string like "€20-30" or null)
- estimated_capacity: estimated venue capacity as number (null if unknown)
- description: one-line description of the event (string)

Segment classification guide:
- "electronic": techno, house, trance, EDM focused events with specific DJ lineups
- "party/nightlife": club nights, themed parties, raves, after parties, pool parties, open bar events, nightclub events without specific genre focus
- "urban/hip-hop": hip-hop, trap, R&B focused events
- "latin/reggaeton": reggaeton, cumbia, salsa, Latin-focused parties
- "pop/commercial": mainstream pop, Top 40 events
- "rock/indie": rock concerts, indie shows
- "live-music": concerts with live bands/singers
- "festival": multi-day or large-scale multi-act events
- Use "party/nightlife" for any general nightclub event, DJ party, themed party, or fiesta that doesn't clearly fit another genre

Rules:
- Only include events within the date range {date_from} to {date_to}
- If a date is ambiguous, make your best guess based on context
- For capacity, estimate based on venue type if not explicit (club ~500, festival ~5000, bar ~200)
- Include ALL events you find: parties, concerts, club nights, DJ sets, festivals, etc.
- Return an empty array if no events are found
- Return ONLY valid JSON array, no other text

Page text:
{text[:8000]}"""

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.1,
        )

        content = response.choices[0].message.content

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        events = json.loads(content.strip())

        # Add source info
        platform = _detect_platform(source_url)
        for event in events:
            event["source_url"] = source_url
            event["source_platform"] = platform

        return events

    except Exception as e:
        print(f"AI parsing failed for {source_url}: {e}")
        return _regex_fallback(text, source_url, city, date_from, date_to)


def parse_events_batch(
    pages: list[dict],
    city: str,
    date_from: str,
    date_to: str,
) -> list[dict]:
    """Parse events from multiple scraped pages."""
    all_events = []

    for page in pages:
        events = parse_events_from_text(
            text=page["content"],
            source_url=page["url"],
            city=city,
            date_from=date_from,
            date_to=date_to,
        )
        all_events.extend(events)

    deduped = _deduplicate(all_events)
    return flag_own_events(deduped)


def _deduplicate(events: list[dict]) -> list[dict]:
    """Remove duplicate events based on name + date + venue."""
    seen = set()
    unique = []

    for event in events:
        key = (
            (event.get("name") or "").lower().strip(),
            event.get("date"),
            (event.get("venue_name") or "").lower().strip(),
        )
        if key not in seen:
            seen.add(key)
            unique.append(event)

    return unique


def _get_own_brand_keywords() -> list[str]:
    """Get brand keywords at runtime (not import time) so env vars are available."""
    raw = os.getenv("OWN_BRAND_KEYWORDS", "").lower()
    return [k.strip() for k in raw.split(",") if k.strip()]


def flag_own_events(events: list[dict]) -> list[dict]:
    """Flag events that match our own brand keywords (set via OWN_BRAND_KEYWORDS env var)."""
    keywords = _get_own_brand_keywords()
    if not keywords:
        return events
    for event in events:
        name = (event.get("name") or "").lower()
        desc = (event.get("description") or "").lower()
        venue = (event.get("venue_name") or "").lower()
        combined = f"{name} {desc} {venue}"
        event["is_own_event"] = any(kw in combined for kw in keywords)
    return events


def _detect_platform(url: str) -> str:
    """Detect which platform a URL belongs to."""
    domain_map = {
        "ra.co": "Resident Advisor",
        "residentadvisor.net": "Resident Advisor",
        "eventbrite.com": "Eventbrite",
        "eventbrite.": "Eventbrite",
        "feverup.com": "Fever",
        "fourvenues.com": "Fourvenues",
        "xceed.me": "Xceed",
        "dice.fm": "DICE",
        "shotgun.live": "Shotgun",
        "passline.com": "Passline",
        "livepass.com": "LivePass",
        "venti.com.ar": "Venti",
        "bomboapp.com": "Bombo",
        "all-access.com.ar": "All Access",
        "skiddle.com": "Skiddle",
        "sympla.com.br": "Sympla",
        "joinnus.com": "Joinnus",
        "boletia.com": "Boletia",
        "partyflock.nl": "Partyflock",
        "ticketmaster.": "Ticketmaster",
    }
    for domain, name in domain_map.items():
        if domain in url:
            return name
    return "Web"


def _regex_fallback(
    text: str, source_url: str, city: str,
    date_from: str, date_to: str
) -> list[dict]:
    """Basic regex-based event extraction when no AI API available."""
    import re

    events = []
    platform = _detect_platform(source_url)

    date_patterns = [
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})",
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
    ]

    lines = text.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or len(line) < 5 or len(line) > 200:
            continue

        context = "\n".join(lines[max(0, i-2):min(len(lines), i+3)])
        has_date = any(re.search(p, context) for p in date_patterns)

        if has_date and not line.startswith("http"):
            events.append({
                "name": line[:100],
                "date": date_from,
                "time": None,
                "venue_name": None,
                "venue_address": None,
                "is_indoor": None,
                "genre": "other",
                "segment": "other",
                "target_audience": "mainstream",
                "source_url": source_url,
                "source_platform": platform,
                "price_range": None,
                "estimated_capacity": None,
                "description": f"Found on {platform}",
            })

    return events[:20]
