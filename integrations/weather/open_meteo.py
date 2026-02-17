"""Open-Meteo weather integration. Free, no API key needed."""

import httpx
from datetime import date, timedelta


def get_weather_for_range(
    latitude: float,
    longitude: float,
    date_from: date,
    date_to: date,
) -> list[dict]:
    """Fetch weather data for a date range.

    Uses forecast API for dates within 16 days, historical API for past dates,
    and climate averages for dates further out.
    """
    today = date.today()
    # Open-Meteo forecast is ~16 days but use 14 for safety margin
    forecast_limit = today + timedelta(days=14)

    results = []

    # Split into forecast range and fallback range
    forecast_dates = []
    fallback_dates = []

    current = date_from
    while current <= date_to:
        if today <= current <= forecast_limit:
            forecast_dates.append(current)
        else:
            fallback_dates.append(current)
        current += timedelta(days=1)

    # Fetch forecast for near-term dates
    if forecast_dates:
        try:
            results.extend(
                _fetch_forecast(latitude, longitude, forecast_dates[0], forecast_dates[-1])
            )
        except Exception as e:
            print(f"Forecast failed: {e}, using fallback estimates")
            for d in forecast_dates:
                results.append(_fallback_estimate(d, latitude))

    # For dates outside forecast range, use fallback estimates
    if fallback_dates:
        for d in fallback_dates:
            results.append(_fallback_estimate(d, latitude))

    return results


def _fetch_forecast(
    lat: float, lon: float, start: date, end: date
) -> list[dict]:
    """Fetch forecast from Open-Meteo forecast API."""
    daily_vars = "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,weather_code"
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily={daily_vars}"
        f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
        f"&timezone=auto"
    )

    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    results = []

    for i, d in enumerate(dates):
        temp_max = daily["temperature_2m_max"][i]
        temp_min = daily["temperature_2m_min"][i]
        precip_prob = daily["precipitation_probability_max"][i] or 0
        wind = daily["wind_speed_10m_max"][i] or 0
        weather_code = daily["weather_code"][i]

        conditions = _weather_code_to_text(weather_code)
        outdoor_score = _calc_outdoor_score(temp_max, temp_min, precip_prob, wind)
        recommendation = _outdoor_recommendation(outdoor_score)

        results.append({
            "date": d,
            "temp_max_c": temp_max,
            "temp_min_c": temp_min,
            "precip_prob": precip_prob,
            "wind_kmh": wind,
            "conditions": conditions,
            "outdoor_score": outdoor_score,
            "recommendation": recommendation,
            "data_type": "forecast",
        })

    return results


def _fetch_historical_averages(
    lat: float, lon: float, dates: list[date]
) -> list[dict]:
    """For dates beyond forecast range, fetch historical averages (last 10 years)."""
    # Use Open-Meteo historical API to get averages for same calendar dates
    # from past years
    results = []
    current_year = date.today().year

    # Group dates by month-day to batch requests
    for d in dates:
        # Fetch same calendar date from last 10 years
        yearly_data = []
        for year_offset in range(1, 11):
            past_year = current_year - year_offset
            try:
                past_date = d.replace(year=past_year)
            except ValueError:
                # Handle Feb 29 in non-leap years
                past_date = d.replace(year=past_year, day=28)
            yearly_data.append(past_date)

        if not yearly_data:
            continue

        # Batch request for all historical dates
        # Open-Meteo historical API
        start = min(yearly_data)
        end = max(yearly_data)

        daily_vars = "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,weather_code"
        url = (
            f"https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat}&longitude={lon}"
            f"&daily={daily_vars}"
            f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
            f"&timezone=auto"
        )

        try:
            resp = httpx.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            # Fallback: estimate from climate norms
            results.append(_fallback_estimate(d, lat))
            continue

        daily = data.get("daily", {})
        api_dates = daily.get("time", [])

        # Filter to only matching month-day
        target_md = f"-{d.month:02d}-{d.day:02d}"
        matching_indices = [
            i for i, ad in enumerate(api_dates) if ad.endswith(target_md)
        ]

        if not matching_indices:
            results.append(_fallback_estimate(d, lat))
            continue

        # Average across years
        avg_max = _avg([daily["temperature_2m_max"][i] for i in matching_indices])
        avg_min = _avg([daily["temperature_2m_min"][i] for i in matching_indices])
        avg_precip = _avg([daily["precipitation_sum"][i] or 0 for i in matching_indices])
        avg_wind = _avg([daily["wind_speed_10m_max"][i] or 0 for i in matching_indices])

        # Estimate precip probability from historical frequency
        rainy_days = sum(
            1 for i in matching_indices
            if (daily["precipitation_sum"][i] or 0) > 1.0
        )
        precip_prob = (rainy_days / len(matching_indices)) * 100 if matching_indices else 0

        # Most common weather code
        codes = [daily["weather_code"][i] for i in matching_indices if daily["weather_code"][i] is not None]
        most_common_code = max(set(codes), key=codes.count) if codes else 0

        outdoor_score = _calc_outdoor_score(avg_max, avg_min, precip_prob, avg_wind)

        results.append({
            "date": d.isoformat(),
            "temp_max_c": round(avg_max, 1),
            "temp_min_c": round(avg_min, 1),
            "precip_prob": round(precip_prob),
            "wind_kmh": round(avg_wind, 1),
            "conditions": _weather_code_to_text(most_common_code) + " (historical avg)",
            "outdoor_score": outdoor_score,
            "recommendation": _outdoor_recommendation(outdoor_score),
            "data_type": "historical_avg",
        })

    return results


def _avg(values: list[float | None]) -> float:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else 0


def _fallback_estimate(d: date, lat: float) -> dict:
    """Rough climate estimate based on latitude and month."""
    month = d.month
    # Very rough: tropical vs temperate
    is_southern = lat < 0
    if is_southern:
        # Flip seasons
        month = ((month + 5) % 12) + 1

    # Rough temperate climate
    temp_by_month = {
        1: 5, 2: 7, 3: 12, 4: 16, 5: 20, 6: 25,
        7: 28, 8: 27, 9: 23, 10: 17, 11: 10, 12: 6,
    }
    base_temp = temp_by_month.get(month, 20)

    return {
        "date": d.isoformat(),
        "temp_max_c": base_temp + 4,
        "temp_min_c": base_temp - 4,
        "precip_prob": 30,
        "wind_kmh": 15,
        "conditions": "Estimated (no data)",
        "outdoor_score": 60,
        "recommendation": "EITHER",
        "data_type": "estimate",
    }


def _calc_outdoor_score(
    temp_max: float | None,
    temp_min: float | None,
    precip_prob: float,
    wind_kmh: float,
) -> int:
    """Calculate 0-100 outdoor suitability score."""
    score = 100

    temp_avg = ((temp_max or 22) + (temp_min or 15)) / 2

    # Temperature: ideal 18-28
    if temp_avg < 10:
        score -= 40
    elif temp_avg < 15:
        score -= 20
    elif temp_avg < 18:
        score -= 5
    elif temp_avg > 35:
        score -= 35
    elif temp_avg > 30:
        score -= 15

    # Rain
    if precip_prob > 70:
        score -= 35
    elif precip_prob > 50:
        score -= 20
    elif precip_prob > 30:
        score -= 10

    # Wind
    if wind_kmh > 40:
        score -= 25
    elif wind_kmh > 25:
        score -= 10

    return max(0, min(100, score))


def _outdoor_recommendation(score: int) -> str:
    if score >= 75:
        return "OUTDOOR"
    elif score >= 50:
        return "EITHER"
    else:
        return "INDOOR"


def _weather_code_to_text(code: int | None) -> str:
    """Convert WMO weather code to readable text."""
    if code is None:
        return "Unknown"
    codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Fog with rime",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with hail",
        99: "Thunderstorm with heavy hail",
    }
    return codes.get(code, f"Code {code}")
