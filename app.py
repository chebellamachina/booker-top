"""BookerTop — Streamlit App."""

import os
import streamlit as st
import json
from datetime import date, timedelta, datetime
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

# Streamlit Cloud: read secrets as env vars if not already set
for key in ("SERPER_API_KEY", "OPENAI_API_KEY", "OWN_BRAND_KEYWORDS"):
    if not os.getenv(key):
        try:
            os.environ[key] = st.secrets[key]
        except (KeyError, FileNotFoundError):
            pass

from db.database import init_db, seed_cities, get_all_cities, get_city_by_id
from core.search_orchestrator import run_search, get_results_by_date

# ── Page Config ──────────────────────────────────────────────

st.set_page_config(
    page_title="BookerTop",
    page_icon="🎵",
    layout="wide",
)

# Initialize DB
init_db()
seed_cities()

# ── Styles ───────────────────────────────────────────────────

st.markdown("""
<style>
    .competition-none { color: #22c55e; font-weight: bold; }
    .competition-low { color: #84cc16; font-weight: bold; }
    .competition-medium { color: #f59e0b; font-weight: bold; }
    .competition-high { color: #ef4444; font-weight: bold; }
    .outdoor-badge { background: #dbeafe; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; }
    .indoor-badge { background: #fef3c7; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; }
    .either-badge { background: #e5e7eb; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; }
    .cal-cell {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 6px 8px;
        min-height: 70px;
        font-size: 0.85em;
    }
    .cal-none { background: #f0fdf4; }
    .cal-low { background: #fefce8; }
    .cal-medium { background: #fff7ed; }
    .cal-high { background: #fef2f2; }
    .own-event-badge {
        background: #8b5cf6; color: white;
        padding: 2px 8px; border-radius: 12px;
        font-size: 0.8em; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


# ── Header ───────────────────────────────────────────────────

st.title("🎵 BookerTop")
st.caption("Competitive landscape analysis for event planning")

# ── Sidebar: Search Form ─────────────────────────────────────

with st.sidebar:
    st.header("🔍 New Search")

    cities = get_all_cities()
    city_options = {c["name"]: c["id"] for c in cities}
    selected_city_name = st.selectbox("City", options=list(city_options.keys()))
    selected_city_id = city_options[selected_city_name]

    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input("From", value=date.today() + timedelta(days=7))
    with col2:
        date_to = st.date_input("To", value=date.today() + timedelta(days=37))

    segment_options = [
        "electronic", "urban/hip-hop", "pop/commercial",
        "latin/reggaeton", "rock/indie", "live-music", "festival",
    ]
    segments = st.multiselect(
        "Segments of interest",
        options=segment_options,
        default=["electronic"],
        help="Filter for specific event types. Leave empty for all.",
    )

    city = get_city_by_id(selected_city_id)
    radius = st.slider("Search radius (km)", 5, 50, city["radius_km"] if city else 20)

    search_clicked = st.button("🚀 Run Search", type="primary", use_container_width=True)

    st.divider()
    st.caption("Powered by Open-Meteo · Serper.dev · OpenAI")


# ── Helper Functions ──────────────────────────────────────────


def _render_date_card(day_data: dict):
    """Render a single date card with events, weather, and competition info."""
    d = day_data["date"]
    day_name = day_data["day_name"]
    events = day_data["events"]
    weather = day_data.get("weather")
    competition = day_data["competition_level"]
    segment_counts = day_data["segment_counts"]
    has_own = day_data.get("has_own_event", False)

    # Competition color
    comp_colors = {
        "none": "🟢", "low": "🟡", "medium": "🟠", "high": "🔴"
    }
    comp_emoji = comp_colors.get(competition, "⚪")

    # Weather info
    if weather:
        temp = f"{weather.get('temp_min_c', '?')}–{weather.get('temp_max_c', '?')}°C"
        precip = f"{weather.get('precip_prob', '?')}% rain"
        conditions = weather.get("conditions", "")
        recommendation = weather.get("recommendation", "EITHER")
        outdoor_score = weather.get("outdoor_score", 50)

        weather_emoji = "☀️" if outdoor_score >= 75 else "⛅" if outdoor_score >= 50 else "🌧️"
        rec_badge = {
            "OUTDOOR": "🌿 Outdoor OK",
            "INDOOR": "🏠 Indoor recommended",
            "EITHER": "🔄 Indoor/Outdoor",
        }.get(recommendation, "")
    else:
        temp = precip = conditions = rec_badge = weather_emoji = ""

    # Header
    is_weekend = day_name in ("Friday", "Saturday", "Sunday")
    weekend_marker = " ⭐" if is_weekend else ""
    own_marker = ""
    if has_own:
        own_marker = ' <span class="own-event-badge">🏠 OWN EVENT</span>'

    with st.container(border=True):
        # Title row
        header_col, weather_col, comp_col = st.columns([3, 2, 2])

        with header_col:
            st.markdown(
                f"### {day_name}, {d}{weekend_marker}{own_marker}",
                unsafe_allow_html=True,
            )

        with weather_col:
            if weather:
                st.markdown(f"{weather_emoji} **{temp}** · {precip}")
                st.caption(f"{conditions} — {rec_badge}")

        with comp_col:
            event_count = len(events)
            st.markdown(f"{comp_emoji} **{competition.upper()}** competition")
            st.caption(f"{event_count} event{'s' if event_count != 1 else ''}")

        # Events
        if events:
            for event in events:
                _render_event_row(event)
        else:
            st.success("No competing events found — potential opportunity!")

        # Segment summary
        if segment_counts:
            seg_text = " · ".join(
                f"**{count}** {seg}" for seg, count in segment_counts.items()
            )
            st.caption(f"By segment: {seg_text}")


def _render_event_row(event: dict):
    """Render a single event within a date card."""
    name = event.get("name", "Unknown Event")
    venue = event.get("venue_name") or ""
    time = event.get("time") or ""
    segment = event.get("segment") or "other"
    target = event.get("target_audience") or ""
    capacity = event.get("estimated_capacity")
    source = event.get("source_platform") or "Web"
    url = event.get("source_url") or ""
    price = event.get("price_range") or ""
    is_own = event.get("is_own_event", False)

    # Segment emoji
    seg_emoji = {
        "electronic": "🎧",
        "urban/hip-hop": "🎤",
        "pop/commercial": "🎵",
        "latin/reggaeton": "💃",
        "rock/indie": "🎸",
        "live-music": "🎺",
        "festival": "🎪",
    }.get(segment, "🎵")

    if is_own:
        seg_emoji = "🏠"

    # Build info line
    parts = []
    if time:
        parts.append(time)
    if venue:
        parts.append(venue)
    if capacity:
        parts.append(f"~{capacity} cap")
    if target:
        parts.append(target)
    if price:
        parts.append(price)

    info = " · ".join(parts)

    col1, col2 = st.columns([5, 1])
    with col1:
        own_tag = ' <span class="own-event-badge">OWN</span>' if is_own else ""
        if url:
            st.markdown(
                f"{seg_emoji} **[{name}]({url})** — {segment}{own_tag}",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"{seg_emoji} **{name}** — {segment}{own_tag}",
                unsafe_allow_html=True,
            )
        if info:
            st.caption(info)
    with col2:
        st.caption(f"via {source}")


def _render_calendar(results: dict):
    """Render a calendar grid view of the search results."""
    if not results:
        return

    sorted_dates = sorted(results.keys())
    first = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
    last = datetime.strptime(sorted_dates[-1], "%Y-%m-%d")

    st.subheader("📅 Calendar View")

    # Day headers
    day_headers = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cols = st.columns(7)
    for i, dh in enumerate(day_headers):
        cols[i].markdown(f"**{dh}**")

    # Walk week by week
    current = first - timedelta(days=first.weekday())  # start from Monday
    while current <= last + timedelta(days=(6 - last.weekday())):
        cols = st.columns(7)
        for i in range(7):
            d = current + timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            with cols[i]:
                if d_str in results:
                    r = results[d_str]
                    comp = r["competition_level"]
                    n_events = r["event_count"]
                    has_own = r.get("has_own_event", False)

                    comp_emoji = {"none": "🟢", "low": "🟡", "medium": "🟠", "high": "🔴"}.get(comp, "⚪")
                    bg = {"none": "cal-none", "low": "cal-low", "medium": "cal-medium", "high": "cal-high"}.get(comp, "")

                    own_dot = " 🏠" if has_own else ""
                    is_wknd = d.weekday() >= 4  # Fri, Sat, Sun

                    weather = r.get("weather")
                    w_icon = ""
                    if weather:
                        score = weather.get("outdoor_score", 50)
                        w_icon = " ☀️" if score >= 75 else " ⛅" if score >= 50 else " 🌧️"

                    day_num = d.day
                    st.markdown(
                        f'<div class="cal-cell {bg}">'
                        f'<strong>{"" if not is_wknd else "⭐"}{day_num}</strong>{own_dot}{w_icon}<br>'
                        f'{comp_emoji} {n_events}ev'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                elif first <= d <= last:
                    st.markdown(
                        f'<div class="cal-cell" style="opacity:0.4">'
                        f'<strong>{d.day}</strong><br>—'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div class="cal-cell" style="opacity:0.15">'
                        f'{d.day}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        current += timedelta(days=7)

    # Legend
    st.caption(
        "🟢 No competition · 🟡 Low · 🟠 Medium · 🔴 High · "
        "🏠 Own event scheduled · ⭐ Weekend · ☀️⛅🌧️ Weather"
    )


def _render_insights(results: dict, city_name: str):
    """Render insights and recommendations section."""
    if not results:
        return

    st.subheader("💡 Insights & Recommendations")

    sorted_dates = sorted(results.keys())
    all_events = []
    weekend_dates = []
    low_comp_weekends = []
    own_event_dates = []
    outdoor_ok_dates = []

    for d_str in sorted_dates:
        r = results[d_str]
        events = r["events"]
        all_events.extend(events)
        is_weekend = r["day_name"] in ("Friday", "Saturday", "Sunday")

        if is_weekend:
            weekend_dates.append(d_str)
            if r["competition_level"] in ("none", "low"):
                low_comp_weekends.append(d_str)

        if r.get("has_own_event"):
            own_event_dates.append(d_str)

        w = r.get("weather")
        if w and w.get("outdoor_score", 0) >= 70:
            outdoor_ok_dates.append(d_str)

    total_events = len(all_events)
    total_days = len(sorted_dates)

    # ── Top recommended dates ──
    scored_dates = []
    for d_str in sorted_dates:
        r = results[d_str]
        score = 0
        # Weekend bonus
        if r["day_name"] in ("Friday", "Saturday"):
            score += 30
        elif r["day_name"] == "Sunday":
            score += 15
        # Low competition bonus
        comp_bonus = {"none": 40, "low": 25, "medium": 5, "high": -10}
        score += comp_bonus.get(r["competition_level"], 0)
        # Weather bonus
        w = r.get("weather")
        if w:
            score += min(w.get("outdoor_score", 50), 100) * 0.3
        # Own event penalty (already have something there)
        if r.get("has_own_event"):
            score -= 50

        scored_dates.append((d_str, r, score))

    scored_dates.sort(key=lambda x: -x[2])
    top_5 = scored_dates[:5]

    # ── Layout ──
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### 🏆 Top 5 Recommended Dates")
        for rank, (d_str, r, score) in enumerate(top_5, 1):
            w = r.get("weather")
            weather_str = ""
            if w:
                weather_str = f" · {w.get('temp_max_c', '?')}°C"
                if w.get("outdoor_score", 0) >= 70:
                    weather_str += " ☀️"
            comp = r["competition_level"]
            comp_e = {"none": "🟢", "low": "🟡", "medium": "🟠", "high": "🔴"}.get(comp, "⚪")
            own_tag = " 🏠" if r.get("has_own_event") else ""
            st.markdown(
                f"**{rank}.** {r['day_name']}, **{d_str}** — "
                f"{comp_e} {comp} ({r['event_count']} events)"
                f"{weather_str}{own_tag}"
            )
        st.caption("Score based on: weekend, low competition, good weather, no own event conflict.")

    with col_right:
        st.markdown("#### 📊 Quick Stats")
        st.markdown(f"- **{total_events}** total competing events in **{total_days}** days")
        avg = total_events / total_days if total_days else 0
        st.markdown(f"- **{avg:.1f}** events/day average")
        st.markdown(f"- **{len(weekend_dates)}** weekend days, **{len(low_comp_weekends)}** with low/no competition")
        if outdoor_ok_dates:
            st.markdown(f"- **{len(outdoor_ok_dates)}** days with good outdoor weather")
        if own_event_dates:
            st.markdown(f"- 🏠 **{len(own_event_dates)}** day(s) with own events already scheduled:")
            for od in own_event_dates:
                own_events = [
                    e for e in results[od]["events"] if e.get("is_own_event")
                ]
                names = ", ".join(e.get("name", "?") for e in own_events)
                st.markdown(f"  - {od}: {names}")

    # ── Segment breakdown ──
    st.markdown("#### 🎭 Competition by Segment")
    seg_counter = Counter()
    for e in all_events:
        seg_counter[e.get("segment") or "other"] += 1

    if seg_counter:
        seg_data = sorted(seg_counter.items(), key=lambda x: -x[1])
        seg_cols = st.columns(min(len(seg_data), 6))
        for i, (seg, count) in enumerate(seg_data[:6]):
            seg_emoji = {
                "electronic": "🎧", "urban/hip-hop": "🎤",
                "pop/commercial": "🎵", "latin/reggaeton": "💃",
                "rock/indie": "🎸", "live-music": "🎺",
                "festival": "🎪",
            }.get(seg, "🎵")
            with seg_cols[i]:
                st.metric(f"{seg_emoji} {seg}", count)

    # ── Day-of-week heatmap ──
    st.markdown("#### 📆 Events by Day of Week")
    dow_counts = Counter()
    for d_str in sorted_dates:
        r = results[d_str]
        dow_counts[r["day_name"]] += r["event_count"]

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dow_cols = st.columns(7)
    for i, day in enumerate(day_order):
        count = dow_counts.get(day, 0)
        bar = "█" * min(count, 20)
        with dow_cols[i]:
            st.markdown(f"**{day[:3]}**")
            st.markdown(f"{count}")
            if bar:
                st.caption(bar)

    # ── Source platforms ──
    platform_counter = Counter()
    for e in all_events:
        platform_counter[e.get("source_platform") or "Web"] += 1

    if platform_counter:
        st.markdown("#### 🌐 Event Sources")
        source_text = " · ".join(
            f"**{name}** ({count})"
            for name, count in platform_counter.most_common()
        )
        st.markdown(source_text)


# ── Main: Run Search & Show Results ──────────────────────────

if search_clicked:
    if date_from >= date_to:
        st.error("'From' date must be before 'To' date.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(message: str, progress: float):
            status_text.text(message)
            progress_bar.progress(progress)

        with st.spinner("Running search..."):
            try:
                search_id = run_search(
                    city_id=selected_city_id,
                    date_from=date_from.isoformat(),
                    date_to=date_to.isoformat(),
                    segments=segments,
                    radius_km=radius,
                    progress_callback=update_progress,
                )
                st.session_state["last_search_id"] = search_id
                st.session_state["last_city"] = selected_city_name
                progress_bar.empty()
                status_text.empty()
                st.success(f"Search complete! Found results for {selected_city_name}.")
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"Search failed: {e}")

# ── Show Results ─────────────────────────────────────────────

if "last_search_id" in st.session_state:
    search_id = st.session_state["last_search_id"]
    city_name = st.session_state.get("last_city", "")

    results = get_results_by_date(search_id)

    if not results:
        st.info("No results found. Try broadening your search or date range.")
    else:
        # Summary metrics
        total_events = sum(r["event_count"] for r in results.values())
        dates_with_events = sum(1 for r in results.values() if r["event_count"] > 0)
        low_competition_dates = sum(
            1 for r in results.values()
            if r["competition_level"] in ("none", "low")
        )
        own_event_count = sum(1 for r in results.values() if r.get("has_own_event"))

        st.header(f"📊 Results for {city_name}")

        m_cols = st.columns(5)
        m_cols[0].metric("Total Events", total_events)
        m_cols[1].metric("Days Analyzed", len(results))
        m_cols[2].metric("Days with Events", dates_with_events)
        m_cols[3].metric("Low Competition", low_competition_dates)
        m_cols[4].metric("🏠 Own Events", own_event_count)

        st.divider()

        # ── Tabs: Calendar / Timeline / Insights ──
        tab_cal, tab_timeline, tab_insights = st.tabs([
            "📅 Calendar", "📋 Timeline", "💡 Insights"
        ])

        with tab_cal:
            _render_calendar(results)

        with tab_timeline:
            # Segment filter
            all_segments = set()
            for r in results.values():
                all_segments.update(r["segment_counts"].keys())

            if all_segments:
                filter_segment = st.multiselect(
                    "Filter by segment",
                    options=sorted(all_segments),
                    default=[],
                    help="Show only dates with events in these segments",
                    key="timeline_segment_filter",
                )
            else:
                filter_segment = []

            # Date timeline
            for date_str in sorted(results.keys()):
                day_data = results[date_str]

                # Apply segment filter
                if filter_segment:
                    matching = any(
                        e.get("segment") in filter_segment
                        for e in day_data["events"]
                    )
                    if not matching and day_data["event_count"] > 0:
                        continue

                _render_date_card(day_data)

        with tab_insights:
            _render_insights(results, city_name)


# ── Empty state ──────────────────────────────────────────────

if "last_search_id" not in st.session_state:
    st.markdown("""
    ### How to use

    1. **Select a city** from the sidebar (Buenos Aires, Ibiza, Madrid, or Miami)
    2. **Choose a date range** you're considering for an event
    3. **Pick segments** that are relevant (electronic, urban, etc.)
    4. **Hit Run Search** and wait for results

    The tool will:
    - 🔍 Search Google for events in that city/date range
    - 📄 Scrape event pages from multiple sources (RA, Fever, Fourvenues, etc.)
    - 🤖 Use AI to extract and classify events
    - 🌤️ Fetch weather data (forecast or historical averages)
    - 📅 Present a calendar view with competition heatmap
    - 💡 Generate insights and top date recommendations
    - 🏠 Flag your own events if detected

    ---

    **Setup required:**
    - `SERPER_API_KEY` — Free at [serper.dev](https://serper.dev) (2500 searches/month)
    - `OPENAI_API_KEY` — For AI event parsing ([platform.openai.com](https://platform.openai.com))

    Without API keys, the tool will use fallback methods (less accurate).
    """)
