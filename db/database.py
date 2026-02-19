"""SQLite database setup and operations."""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "bookertop.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            timezone TEXT NOT NULL,
            radius_km INTEGER DEFAULT 20,
            preferred_days TEXT DEFAULT '["Friday","Saturday"]',
            venue_preference TEXT DEFAULT 'both',
            peak_season_start INTEGER,
            peak_season_end INTEGER,
            known_sources TEXT DEFAULT '[]',
            UNIQUE(name, country)
        );

        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id INTEGER NOT NULL,
            date_from TEXT NOT NULL,
            date_to TEXT NOT NULL,
            segments TEXT DEFAULT '[]',
            radius_km INTEGER DEFAULT 20,
            status TEXT DEFAULT 'pending',
            debug_log TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (city_id) REFERENCES cities(id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT,
            venue_name TEXT,
            venue_address TEXT,
            is_indoor INTEGER,
            genre TEXT,
            segment TEXT,
            target_audience TEXT,
            source_url TEXT,
            source_platform TEXT,
            price_range TEXT,
            estimated_capacity INTEGER,
            description TEXT,
            FOREIGN KEY (search_id) REFERENCES searches(id),
            UNIQUE(search_id, name, date, venue_name)
        );

        CREATE TABLE IF NOT EXISTS weather_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            temp_max_c REAL,
            temp_min_c REAL,
            precip_prob REAL,
            wind_kmh REAL,
            conditions TEXT,
            outdoor_score INTEGER,
            recommendation TEXT,
            FOREIGN KEY (search_id) REFERENCES searches(id),
            UNIQUE(search_id, date)
        );

        CREATE TABLE IF NOT EXISTS venue_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            address TEXT,
            venue_type TEXT,
            is_indoor INTEGER,
            capacity INTEGER,
            rating REAL,
            place_id TEXT,
            image_url TEXT,
            FOREIGN KEY (search_id) REFERENCES searches(id)
        );
    """)
    conn.commit()

    # Migrate: add debug_log column if missing (existing DBs)
    try:
        conn.execute("SELECT debug_log FROM searches LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE searches ADD COLUMN debug_log TEXT DEFAULT '{}'")
        conn.commit()

    conn.close()


def seed_cities():
    """Insert default cities if they don't exist."""
    cities = [
        {
            "name": "Buenos Aires",
            "country": "AR",
            "latitude": -34.6037,
            "longitude": -58.3816,
            "timezone": "America/Argentina/Buenos_Aires",
            "radius_km": 25,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": 10,
            "peak_season_end": 3,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "passline.com",
                "venti.com.ar",
                "allaccess.com.ar",
                "wearebombo.com",
                "feverup.com",
                "livepass.com.ar",
                "buenosaliens.com",
                "musicaelectronica.club",
            ]),
        },
        {
            "name": "Ibiza",
            "country": "ES",
            "latitude": 38.9067,
            "longitude": 1.4206,
            "timezone": "Europe/Madrid",
            "radius_km": 20,
            "preferred_days": json.dumps(["Thursday", "Friday", "Saturday", "Sunday"]),
            "venue_preference": "outdoor",
            "peak_season_start": 5,
            "peak_season_end": 10,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "ibiza-spotlight.com",
            ]),
        },
        {
            "name": "Madrid",
            "country": "ES",
            "latitude": 40.4168,
            "longitude": -3.7038,
            "timezone": "Europe/Madrid",
            "radius_km": 20,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "fourvenues.com",
                "feverup.com",
            ]),
        },
        {
            "name": "Miami",
            "country": "US",
            "latitude": 25.7617,
            "longitude": -80.1918,
            "timezone": "America/New_York",
            "radius_km": 30,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": 10,
            "peak_season_end": 5,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "eventbrite.com",
            ]),
        },
        {
            "name": "Barcelona",
            "country": "ES",
            "latitude": 41.3874,
            "longitude": 2.1686,
            "timezone": "Europe/Madrid",
            "radius_km": 20,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": 5,
            "peak_season_end": 10,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "fourvenues.com",
                "xceed.me",
                "dice.fm",
            ]),
        },
        {
            "name": "New York",
            "country": "US",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "timezone": "America/New_York",
            "radius_km": 25,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "indoor",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "dice.fm",
                "eventbrite.com",
                "shotgun.live",
            ]),
        },
        {
            "name": "Los Angeles",
            "country": "US",
            "latitude": 34.0522,
            "longitude": -118.2437,
            "timezone": "America/Los_Angeles",
            "radius_km": 30,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "dice.fm",
                "eventbrite.com",
            ]),
        },
        {
            "name": "London",
            "country": "GB",
            "latitude": 51.5074,
            "longitude": -0.1278,
            "timezone": "Europe/London",
            "radius_km": 20,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "indoor",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "dice.fm",
                "shotgun.live",
                "skiddle.com",
            ]),
        },
        {
            "name": "Berlin",
            "country": "DE",
            "latitude": 52.5200,
            "longitude": 13.4050,
            "timezone": "Europe/Berlin",
            "radius_km": 20,
            "preferred_days": json.dumps(["Friday", "Saturday", "Sunday"]),
            "venue_preference": "indoor",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "dice.fm",
            ]),
        },
        {
            "name": "Santiago",
            "country": "CL",
            "latitude": -33.4489,
            "longitude": -70.6693,
            "timezone": "America/Santiago",
            "radius_km": 25,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": 10,
            "peak_season_end": 3,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "passline.com",
            ]),
        },
        {
            "name": "São Paulo",
            "country": "BR",
            "latitude": -23.5505,
            "longitude": -46.6333,
            "timezone": "America/Sao_Paulo",
            "radius_km": 30,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "eventbrite.com.br",
                "shotgun.live",
            ]),
        },
        {
            "name": "Bogotá",
            "country": "CO",
            "latitude": 4.7110,
            "longitude": -74.0721,
            "timezone": "America/Bogota",
            "radius_km": 20,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "eventbrite.co",
            ]),
        },
        {
            "name": "México City",
            "country": "MX",
            "latitude": 19.4326,
            "longitude": -99.1332,
            "timezone": "America/Mexico_City",
            "radius_km": 25,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "eventbrite.com.mx",
                "boletia.com",
            ]),
        },
        {
            "name": "Lima",
            "country": "PE",
            "latitude": -12.0464,
            "longitude": -77.0428,
            "timezone": "America/Lima",
            "radius_km": 20,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "joinnus.com",
            ]),
        },
        {
            "name": "Montevideo",
            "country": "UY",
            "latitude": -34.9011,
            "longitude": -56.1645,
            "timezone": "America/Montevideo",
            "radius_km": 20,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": 11,
            "peak_season_end": 3,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "passline.com",
                "wearebombo.com",
            ]),
        },
        {
            "name": "Paris",
            "country": "FR",
            "latitude": 48.8566,
            "longitude": 2.3522,
            "timezone": "Europe/Paris",
            "radius_km": 20,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "indoor",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "dice.fm",
                "shotgun.live",
            ]),
        },
        {
            "name": "Amsterdam",
            "country": "NL",
            "latitude": 52.3676,
            "longitude": 4.9041,
            "timezone": "Europe/Amsterdam",
            "radius_km": 20,
            "preferred_days": json.dumps(["Friday", "Saturday"]),
            "venue_preference": "both",
            "peak_season_start": None,
            "peak_season_end": None,
            "known_sources": json.dumps([
                "residentadvisor.net",
                "dice.fm",
                "partyflock.nl",
            ]),
        },
    ]

    conn = get_connection()
    for city in cities:
        conn.execute("""
            INSERT OR IGNORE INTO cities
            (name, country, latitude, longitude, timezone, radius_km,
             preferred_days, venue_preference, peak_season_start, peak_season_end,
             known_sources)
            VALUES (:name, :country, :latitude, :longitude, :timezone, :radius_km,
                    :preferred_days, :venue_preference, :peak_season_start, :peak_season_end,
                    :known_sources)
        """, city)
    conn.commit()
    conn.close()


def get_all_cities() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM cities ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_city_by_id(city_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM cities WHERE id = ?", (city_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_search(city_id: int, date_from: str, date_to: str,
                  segments: list[str], radius_km: int) -> int:
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO searches (city_id, date_from, date_to, segments, radius_km, status)
        VALUES (?, ?, ?, ?, ?, 'running')
    """, (city_id, date_from, date_to, json.dumps(segments), radius_km))
    search_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return search_id


def update_search_status(search_id: int, status: str):
    conn = get_connection()
    conn.execute("UPDATE searches SET status = ? WHERE id = ?", (status, search_id))
    conn.commit()
    conn.close()


def insert_event(search_id: int, event: dict):
    conn = get_connection()
    conn.execute("""
        INSERT OR IGNORE INTO events
        (search_id, name, date, time, venue_name, venue_address, is_indoor,
         genre, segment, target_audience, source_url, source_platform,
         price_range, estimated_capacity, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        search_id,
        event.get("name"),
        event.get("date"),
        event.get("time"),
        event.get("venue_name"),
        event.get("venue_address"),
        event.get("is_indoor"),
        event.get("genre"),
        event.get("segment"),
        event.get("target_audience"),
        event.get("source_url"),
        event.get("source_platform"),
        event.get("price_range"),
        event.get("estimated_capacity"),
        event.get("description"),
    ))
    conn.commit()
    conn.close()


def insert_weather_day(search_id: int, weather: dict):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO weather_days
        (search_id, date, temp_max_c, temp_min_c, precip_prob, wind_kmh,
         conditions, outdoor_score, recommendation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        search_id,
        weather.get("date"),
        weather.get("temp_max_c"),
        weather.get("temp_min_c"),
        weather.get("precip_prob"),
        weather.get("wind_kmh"),
        weather.get("conditions"),
        weather.get("outdoor_score"),
        weather.get("recommendation"),
    ))
    conn.commit()
    conn.close()


def get_search_history() -> list[dict]:
    """Get all completed searches with city name and event count."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            s.id,
            c.name as city_name,
            s.date_from,
            s.date_to,
            s.segments,
            s.status,
            s.created_at,
            (SELECT COUNT(*) FROM events e WHERE e.search_id = s.id) as event_count
        FROM searches s
        JOIN cities c ON s.city_id = c.id
        WHERE s.status = 'completed'
        ORDER BY s.created_at DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_search(search_id: int):
    """Delete a search and its associated events/weather."""
    conn = get_connection()
    conn.execute("DELETE FROM weather_days WHERE search_id = ?", (search_id,))
    conn.execute("DELETE FROM events WHERE search_id = ?", (search_id,))
    conn.execute("DELETE FROM searches WHERE id = ?", (search_id,))
    conn.commit()
    conn.close()


def save_debug_log(search_id: int, log: dict):
    """Save pipeline debug log as JSON."""
    conn = get_connection()
    conn.execute(
        "UPDATE searches SET debug_log = ? WHERE id = ?",
        (json.dumps(log, default=str), search_id),
    )
    conn.commit()
    conn.close()


def get_debug_log(search_id: int) -> dict:
    """Retrieve the debug log for a search."""
    conn = get_connection()
    row = conn.execute(
        "SELECT debug_log FROM searches WHERE id = ?", (search_id,)
    ).fetchone()
    conn.close()
    if row and row["debug_log"]:
        try:
            return json.loads(row["debug_log"])
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def get_events_for_search(search_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM events WHERE search_id = ? ORDER BY date, time", (search_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_weather_for_search(search_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM weather_days WHERE search_id = ? ORDER BY date", (search_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
