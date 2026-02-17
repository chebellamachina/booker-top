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

init_db()
seed_cities()

# ── Responsive CSS ───────────────────────────────────────────

st.markdown("""
<style>
    /* ── Base reset for mobile ── */
    .block-container { padding: 1rem 1rem 3rem 1rem; }

    /* ── Competition colors ── */
    .comp-none { color: #22c55e; font-weight: 700; }
    .comp-low { color: #84cc16; font-weight: 700; }
    .comp-medium { color: #f59e0b; font-weight: 700; }
    .comp-high { color: #ef4444; font-weight: 700; }

    /* ── Own event badge ── */
    .own-badge {
        background: #8b5cf6; color: white;
        padding: 2px 8px; border-radius: 12px;
        font-size: 0.78em; font-weight: 700;
        white-space: nowrap;
    }

    /* ── Calendar cells ── */
    .cal-cell {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 4px 6px;
        min-height: 56px;
        font-size: 0.82em;
        line-height: 1.35;
    }
    .cal-none { background: #f0fdf4; }
    .cal-low  { background: #fefce8; }
    .cal-med  { background: #fff7ed; }
    .cal-high { background: #fef2f2; }

    /* ── Event card ── */
    .ev-card {
        background: #fafafa;
        border-left: 3px solid #e5e7eb;
        padding: 6px 10px;
        margin: 4px 0;
        border-radius: 0 6px 6px 0;
        font-size: 0.9em;
    }
    .ev-card.ev-own { border-left-color: #8b5cf6; background: #f5f3ff; }
    .ev-meta { color: #6b7280; font-size: 0.82em; }
    .ev-name { font-weight: 600; }
    .ev-name a { color: inherit; text-decoration: none; }
    .ev-name a:hover { text-decoration: underline; }

    /* ── Day header in timeline ── */
    .day-hdr {
        display: flex; flex-wrap: wrap; align-items: baseline;
        gap: 8px; margin-bottom: 2px;
    }
    .day-hdr h3 { margin: 0; font-size: 1.15em; }

    /* ── Metric cards responsive ── */
    [data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 10px 14px;
    }

    /* ── Mobile tweaks ── */
    @media (max-width: 768px) {
        .block-container { padding: 0.5rem 0.5rem 2rem 0.5rem; }
        .cal-cell { min-height: 44px; padding: 3px 4px; font-size: 0.75em; }
        [data-testid="stMetric"] { padding: 8px 10px; }
        /* Stack columns on mobile */
        [data-testid="column"] { min-width: 100% !important; }
    }

    /* ── Hide hamburger on mobile for cleaner look ── */
    @media (max-width: 768px) {
        header[data-testid="stHeader"] { padding: 0.5rem; }
    }
</style>
""", unsafe_allow_html=True)


# ── Header ───────────────────────────────────────────────────

st.title("🎵 BookerTop")
st.caption("Competitive landscape analysis for event planning")

# ── Sidebar ─────────────────────────────────────────────

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
        "Segments",
        options=segment_options,
        default=["electronic"],
        help="Filter for specific event types.",
    )

    city = get_city_by_id(selected_city_id)
    radius = st.slider("Radius (km)", 5, 50, city["radius_km"] if city else 20)

    search_clicked = st.button("🚀 Run Search", type="primary", use_container_width=True)

    st.divider()
    st.caption("Open-Meteo · Serper.dev · OpenAI")


# ═══════════════════════════════════════════════════════════════
#  Helper renderers
# ═══════════════════════════════════════════════════════════════


def _render_date_card(day_data: dict):
    """Mobile-friendly date card."""
    d = day_data["date"]
    day_name = day_data["day_name"]
    events = day_data["events"]
    weather = day_data.get("weather")
    competition = day_data["competition_level"]
    segment_counts = day_data["segment_counts"]
    has_own = day_data.get("has_own_event", False)

    comp_emoji = {"none": "🟢", "low": "🟡", "medium": "🟠", "high": "🔴"}.get(competition, "⚪")
    is_weekend = day_name in ("Friday", "Saturday", "Sunday")
    wknd = " ⭐" if is_weekend else ""
    own_html = ' <span class="own-badge">🏠 OWN EVENT</span>' if has_own else ""

    # Weather line
    w_line = ""
    if weather:
        temp = f"{weather.get('temp_min_c', '?')}–{weather.get('temp_max_c', '?')}°C"
        precip = f"{weather.get('precip_prob', '?')}%💧"
        score = weather.get("outdoor_score", 50)
        w_emoji = "☀️" if score >= 75 else "⛅" if score >= 50 else "🌧️"
        rec = {"OUTDOOR": "Outdoor OK", "INDOOR": "Indoor rec.", "EITHER": "Either"}.get(
            weather.get("recommendation", ""), ""
        )
        w_line = f"{w_emoji} {temp} · {precip} · {rec}"

    with st.container(border=True):
        # Header — single line that wraps well on mobile
        st.markdown(
            f'<div class="day-hdr">'
            f'<h3>{day_name[:3]}, {d}{wknd}</h3>'
            f'<span>{comp_emoji} <strong>{competition.upper()}</strong> · {len(events)} ev</span>'
            f'{own_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        if w_line:
            st.caption(w_line)

        # Events
        if events:
            for event in events:
                _render_event_card(event)
        else:
            st.success("✅ No competing events — potential opportunity!")

        # Segment summary
        if segment_counts:
            seg_text = " · ".join(f"**{c}** {s}" for s, c in segment_counts.items())
            st.caption(seg_text)


def _render_event_card(event: dict):
    """Single event as a compact card (works on mobile)."""
    name = event.get("name", "Unknown")
    venue = event.get("venue_name") or ""
    time_str = event.get("time") or ""
    segment = event.get("segment") or "other"
    source = event.get("source_platform") or "Web"
    url = event.get("source_url") or ""
    price = event.get("price_range") or ""
    capacity = event.get("estimated_capacity")
    is_own = event.get("is_own_event", False)

    seg_e = {
        "electronic": "🎧", "urban/hip-hop": "🎤", "pop/commercial": "🎵",
        "latin/reggaeton": "💃", "rock/indie": "🎸", "live-music": "🎺",
        "festival": "🎪",
    }.get(segment, "🎵")
    if is_own:
        seg_e = "🏠"

    own_cls = " ev-own" if is_own else ""
    own_tag = ' <span class="own-badge">OWN</span>' if is_own else ""

    name_html = f'<a href="{url}" target="_blank">{name}</a>' if url else name

    meta_parts = [p for p in [time_str, venue, f"~{capacity}" if capacity else "", price, source] if p]
    meta = " · ".join(meta_parts)

    st.markdown(
        f'<div class="ev-card{own_cls}">'
        f'<span class="ev-name">{seg_e} {name_html}</span> — {segment}{own_tag}<br>'
        f'<span class="ev-meta">{meta}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_calendar(results: dict):
    """Calendar grid — responsive."""
    if not results:
        return

    sorted_dates = sorted(results.keys())
    first = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
    last = datetime.strptime(sorted_dates[-1], "%Y-%m-%d")

    # Day headers
    cols = st.columns(7)
    for i, dh in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
        cols[i].markdown(f"**{dh}**")

    current = first - timedelta(days=first.weekday())
    while current <= last + timedelta(days=(6 - last.weekday())):
        cols = st.columns(7)
        for i in range(7):
            d = current + timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            with cols[i]:
                if d_str in results:
                    r = results[d_str]
                    comp = r["competition_level"]
                    n_ev = r["event_count"]
                    has_own = r.get("has_own_event", False)
                    ce = {"none": "🟢", "low": "🟡", "medium": "🟠", "high": "🔴"}.get(comp, "⚪")
                    bg = {"none": "cal-none", "low": "cal-low", "medium": "cal-med", "high": "cal-high"}.get(comp, "")
                    own_dot = " 🏠" if has_own else ""
                    is_wknd = d.weekday() >= 4
                    w = r.get("weather")
                    wi = ""
                    if w:
                        s = w.get("outdoor_score", 50)
                        wi = " ☀️" if s >= 75 else " ⛅" if s >= 50 else " 🌧️"
                    st.markdown(
                        f'<div class="cal-cell {bg}">'
                        f'<strong>{"⭐" if is_wknd else ""}{d.day}</strong>{own_dot}{wi}<br>'
                        f'{ce} {n_ev}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                elif first <= d <= last:
                    st.markdown(
                        f'<div class="cal-cell" style="opacity:0.35">'
                        f'<strong>{d.day}</strong><br>—</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div class="cal-cell" style="opacity:0.12">{d.day}</div>',
                        unsafe_allow_html=True,
                    )
        current += timedelta(days=7)

    st.caption(
        "🟢 None · 🟡 Low · 🟠 Med · 🔴 High · "
        "🏠 Own event · ⭐ Weekend · ☀️⛅🌧️ Weather"
    )


def _render_insights(results: dict, city_name: str):
    """Insights — stacks on mobile."""
    if not results:
        return

    sorted_dates = sorted(results.keys())
    all_events = []
    weekend_dates = []
    low_comp_weekends = []
    own_event_dates = []
    outdoor_ok_dates = []

    for d_str in sorted_dates:
        r = results[d_str]
        all_events.extend(r["events"])
        is_wknd = r["day_name"] in ("Friday", "Saturday", "Sunday")
        if is_wknd:
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

    # Score dates
    scored = []
    for d_str in sorted_dates:
        r = results[d_str]
        sc = 0
        if r["day_name"] in ("Friday", "Saturday"):
            sc += 30
        elif r["day_name"] == "Sunday":
            sc += 15
        sc += {"none": 40, "low": 25, "medium": 5, "high": -10}.get(r["competition_level"], 0)
        w = r.get("weather")
        if w:
            sc += min(w.get("outdoor_score", 50), 100) * 0.3
        if r.get("has_own_event"):
            sc -= 50
        scored.append((d_str, r, sc))
    scored.sort(key=lambda x: -x[2])

    # ── Top recommended ──
    st.markdown("#### 🏆 Top 5 Recommended Dates")
    for rank, (d_str, r, sc) in enumerate(scored[:5], 1):
        w = r.get("weather")
        ws = ""
        if w:
            ws = f" · {w.get('temp_max_c', '?')}°C"
            if w.get("outdoor_score", 0) >= 70:
                ws += " ☀️"
        ce = {"none": "🟢", "low": "🟡", "medium": "🟠", "high": "🔴"}.get(r["competition_level"], "⚪")
        ot = " 🏠" if r.get("has_own_event") else ""
        st.markdown(
            f"**{rank}.** {r['day_name'][:3]} **{d_str}** — "
            f"{ce} {r['competition_level']} ({r['event_count']} ev){ws}{ot}"
        )
    st.caption("Weekend + low competition + good weather − own event conflict")

    st.divider()

    # ── Quick stats ──
    st.markdown("#### 📊 Quick Stats")
    avg = total_events / total_days if total_days else 0
    stat_cols = st.columns(2)
    with stat_cols[0]:
        st.markdown(f"- **{total_events}** events in **{total_days}** days")
        st.markdown(f"- **{avg:.1f}** events/day avg")
        st.markdown(f"- **{len(weekend_dates)}** weekends, **{len(low_comp_weekends)}** low comp")
    with stat_cols[1]:
        if outdoor_ok_dates:
            st.markdown(f"- **{len(outdoor_ok_dates)}** good outdoor days")
        if own_event_dates:
            st.markdown(f"- 🏠 **{len(own_event_dates)}** own event(s):")
            for od in own_event_dates:
                names = ", ".join(
                    e.get("name", "?") for e in results[od]["events"] if e.get("is_own_event")
                )
                st.caption(f"  {od}: {names}")

    st.divider()

    # ── Segments ──
    seg_counter = Counter(e.get("segment") or "other" for e in all_events)
    if seg_counter:
        st.markdown("#### 🎭 By Segment")
        seg_data = sorted(seg_counter.items(), key=lambda x: -x[1])
        # Use 3 cols for mobile friendliness, up to 6 for desktop
        n_cols = min(len(seg_data), 3)
        for row_start in range(0, len(seg_data[:6]), n_cols):
            row = seg_data[row_start:row_start + n_cols]
            cols = st.columns(n_cols)
            for i, (seg, count) in enumerate(row):
                se = {
                    "electronic": "🎧", "urban/hip-hop": "🎤", "pop/commercial": "🎵",
                    "latin/reggaeton": "💃", "rock/indie": "🎸", "live-music": "🎺",
                    "festival": "🎪",
                }.get(seg, "🎵")
                with cols[i]:
                    st.metric(f"{se} {seg}", count)

    # ── Day of week ──
    dow_counts = Counter()
    for d_str in sorted_dates:
        r = results[d_str]
        dow_counts[r["day_name"]] += r["event_count"]

    if any(dow_counts.values()):
        st.markdown("#### 📆 By Day of Week")
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        full = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        cols = st.columns(7)
        max_c = max(dow_counts.values()) if dow_counts.values() else 1
        for i, (short, full_name) in enumerate(zip(days, full)):
            c = dow_counts.get(full_name, 0)
            bar_len = int((c / max_c) * 8) if max_c else 0
            with cols[i]:
                st.markdown(f"**{short}**")
                st.markdown(f"{'█' * bar_len} {c}" if c else "·")

    # ── Sources ──
    plat_counter = Counter(e.get("source_platform") or "Web" for e in all_events)
    if plat_counter:
        st.markdown("#### 🌐 Sources")
        st.markdown(
            " · ".join(f"**{n}** ({c})" for n, c in plat_counter.most_common())
        )


# ═══════════════════════════════════════════════════════════════
#  Main flow
# ═══════════════════════════════════════════════════════════════

if search_clicked:
    if date_from >= date_to:
        st.error("'From' date must be before 'To' date.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(msg: str, pct: float):
            status_text.text(msg)
            progress_bar.progress(pct)

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
                st.success(f"✅ Search complete for {selected_city_name}!")
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"Search failed: {e}")


# ═══════════════════════════════════════════════════════════════
#  Results display
# ═══════════════════════════════════════════════════════════════

if "last_search_id" in st.session_state:
    search_id = st.session_state["last_search_id"]
    city_name = st.session_state.get("last_city", "")
    results = get_results_by_date(search_id)

    if not results:
        st.info("No results found. Try broadening your search or date range.")
    else:
        total_events = sum(r["event_count"] for r in results.values())
        dates_w_events = sum(1 for r in results.values() if r["event_count"] > 0)
        low_comp = sum(1 for r in results.values() if r["competition_level"] in ("none", "low"))
        own_count = sum(1 for r in results.values() if r.get("has_own_event"))

        st.header(f"📊 {city_name}")

        # Metrics — 2 rows on mobile (2+2+1), single row on desktop
        r1 = st.columns([1, 1, 1, 1, 1])
        r1[0].metric("Events", total_events)
        r1[1].metric("Days", len(results))
        r1[2].metric("Active", dates_w_events)
        r1[3].metric("Low Comp", low_comp)
        r1[4].metric("🏠 Own", own_count)

        st.divider()

        tab_cal, tab_tl, tab_ins = st.tabs(["📅 Calendar", "📋 Timeline", "💡 Insights"])

        with tab_cal:
            _render_calendar(results)

        with tab_tl:
            all_segs = set()
            for r in results.values():
                all_segs.update(r["segment_counts"].keys())
            filter_seg = []
            if all_segs:
                filter_seg = st.multiselect(
                    "Filter segment", sorted(all_segs), default=[],
                    key="tl_seg_filter",
                )
            for ds in sorted(results.keys()):
                dd = results[ds]
                if filter_seg:
                    if not any(e.get("segment") in filter_seg for e in dd["events"]) and dd["event_count"] > 0:
                        continue
                _render_date_card(dd)

        with tab_ins:
            _render_insights(results, city_name)


# ═══════════════════════════════════════════════════════════════
#  Empty state
# ═══════════════════════════════════════════════════════════════

if "last_search_id" not in st.session_state:
    st.markdown("""
### 👋 Welcome

1. **Pick a city** in the sidebar
2. **Set your date range**
3. **Choose segments** (electronic, urban, etc.)
4. **Run Search** → get results in seconds

**What you'll get:**
- 📅 Calendar heatmap of competition
- 📋 Timeline with every event found
- 💡 Top date recommendations + insights
- 🏠 Your own events flagged automatically

---
*Needs `SERPER_API_KEY` + `OPENAI_API_KEY` in Settings → Secrets*
    """)
