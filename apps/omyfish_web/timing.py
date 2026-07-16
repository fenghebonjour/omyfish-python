"""Timing tab — fish-activity forecast, ported from omyfish-java's /timing page.

The bite-score domain lives only in the shared omyfish-ai service, so this
module is a thin HTTP client plus Streamlit rendering. Conventions mirror
the java frontend: activity bands High >=70 / Medium 40-69 / Low <40,
daily score = mean of the 04:00-20:00 hours, Major/Minor times and the
current-conditions alert come from the service as-is.
"""

from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import requests
import streamlit as st

from shared.config import settings

FACTORS = ["pressure", "temperature", "wind", "water", "solunar", "sky"]
DAY_START_HOUR, DAY_END_HOUR = 4, 20
BAND_HIGH, BAND_MEDIUM = 70, 40

_REVERSE_GEOCODE_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"


# ── Data access ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=900, show_spinner=False)
def fetch_forecast(lat: float, lon: float, species: str = "general", hours: int = 336) -> dict:
    resp = requests.get(
        f"{settings.bite_service_url}/bite-score/forecast",
        params={"lat": lat, "lon": lon, "species": species, "hours": hours},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=86400, show_spinner=False)
def reverse_geocode(lat: float, lon: float) -> str | None:
    try:
        resp = requests.get(
            _REVERSE_GEOCODE_URL,
            params={"latitude": lat, "longitude": lon, "localityLanguage": "en"},
            timeout=5,
        )
        data = resp.json()
        return data.get("city") or data.get("locality") or None
    except Exception:
        return None


# ── Score helpers (same conventions as the java frontend) ────────────────────

def activity_band(score: float) -> str:
    if score >= BAND_HIGH:
        return "High"
    if score >= BAND_MEDIUM:
        return "Medium"
    return "Low"


def gauge_label(factor_tab: str, score: float | None) -> str:
    if score is None:
        return "No data for this day"
    band = activity_band(score)
    if factor_tab == "Overall":
        return f"{band} fish activity"
    quality = {"High": "Favorable", "Medium": "Fair", "Low": "Poor"}[band]
    return f"{quality} {factor_tab.lower()} conditions"


def day_window_mean(day_hours: list[dict], value_of) -> float | None:
    in_window = [h for h in day_hours
                 if DAY_START_HOUR <= datetime.fromisoformat(h["timestamp"]).hour <= DAY_END_HOUR]
    if not in_window:
        return None
    return sum(value_of(h) for h in in_window) / len(in_window)


def safety_ranges(day_hours: list[dict]) -> list[dict]:
    """Group consecutive flagged hours into {message, start, end} ranges."""
    ranges: list[dict] = []
    open_range = None
    for h in day_hours:
        start = datetime.fromisoformat(h["timestamp"])
        flag = h.get("safety_flag")
        if flag and open_range and open_range["message"] == flag and open_range["end"] == start:
            open_range["end"] = start + timedelta(hours=1)
        else:
            if open_range:
                ranges.append(open_range)
            open_range = {"message": flag, "start": start, "end": start + timedelta(hours=1)} if flag else None
    if open_range:
        ranges.append(open_range)
    return ranges


# ── Formatting ────────────────────────────────────────────────────────────────

def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _fmt_window(w: dict) -> str:
    start, end = datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"])
    s, e = _fmt_time(start), _fmt_time(end)
    if s[-2:] == e[-2:]:  # same AM/PM — show it once
        return f"{s[:-3]}–{e}"
    return f"{s} – {e}"


def _windows_for_day(windows: list[dict], day: str) -> list[dict]:
    day_start = datetime.fromisoformat(f"{day}T00:00:00")
    day_end = day_start + timedelta(days=1)
    return [w for w in windows
            if datetime.fromisoformat(w["start"]) < day_end
            and datetime.fromisoformat(w["end"]) > day_start]


def _hour_of_day(iso: str, day: str) -> float:
    return (datetime.fromisoformat(iso)
            - datetime.fromisoformat(f"{day}T00:00:00")).total_seconds() / 3600


def _gauge_svg(score: float | None, label: str) -> str:
    import math
    radius, circ = 62, 2 * math.pi * 62
    fraction = 0.0 if score is None else max(0.0, min(100.0, score)) / 100
    text = "–" if score is None else str(round(score))
    return f"""
    <div style="display:flex;flex-direction:column;align-items:center;gap:4px">
      <svg width="160" height="160" viewBox="0 0 160 160">
        <circle cx="80" cy="80" r="{radius}" fill="none" stroke="#dbeafe" stroke-width="12"/>
        <circle cx="80" cy="80" r="{radius}" fill="none" stroke="#2563eb" stroke-width="12"
                stroke-linecap="round" stroke-dasharray="{fraction * circ:.1f} {circ:.1f}"
                transform="rotate(-90 80 80)"/>
        <text x="80" y="78" text-anchor="middle" font-size="36" font-weight="700" fill="#111827">{text}</text>
        <text x="80" y="100" text-anchor="middle" font-size="13" fill="#9ca3af">/ 100</text>
      </svg>
      <p style="margin:0;font-size:14px;font-weight:500;color:#1d4ed8">{label}</p>
    </div>
    """


# ── Chart ─────────────────────────────────────────────────────────────────────

def _activity_chart(points: pd.DataFrame, major_ranges: list[dict],
                    minor_ranges: list[dict], sun_marks: list[dict]) -> alt.LayerChart:
    x_axis = alt.X(
        "hour:Q", title=None, scale=alt.Scale(domain=[0, 24]),
        axis=alt.Axis(
            values=[0, 4, 8, 12, 16, 20, 24], grid=False,
            labelExpr=("datum.value == 0 || datum.value == 24 ? '12 AM' : "
                       "datum.value == 12 ? '12 PM' : "
                       "datum.value < 12 ? datum.value + ' AM' : (datum.value - 12) + ' PM'"),
        ),
    )
    y_axis = alt.Y(
        "value:Q", title=None, scale=alt.Scale(domain=[0, 100]),
        axis=alt.Axis(
            values=[20, 55, 85], grid=False,
            labelExpr="datum.value == 85 ? 'High' : datum.value == 55 ? 'Medium' : 'Low'",
        ),
    )

    bands = alt.Chart(pd.DataFrame([
        {"y1": 0, "y2": BAND_MEDIUM, "color": "#f8fafc"},
        {"y1": BAND_MEDIUM, "y2": BAND_HIGH, "color": "#eff6ff"},
        {"y1": BAND_HIGH, "y2": 100, "color": "#dbeafe"},
    ])).mark_rect(opacity=0.8).encode(
        y=alt.Y("y1:Q", scale=alt.Scale(domain=[0, 100])), y2="y2:Q",
        color=alt.Color("color:N", scale=None),
    )

    layers: list[alt.Chart] = [bands]
    for ranges, color, opacity in ((minor_ranges, "#60a5fa", 0.15), (major_ranges, "#2563eb", 0.2)):
        if ranges:
            layers.append(
                alt.Chart(pd.DataFrame(ranges)).mark_rect(color=color, opacity=opacity)
                .encode(x=alt.X("x1:Q", scale=alt.Scale(domain=[0, 24])), x2="x2:Q")
            )
    if sun_marks:
        sun_df = pd.DataFrame(sun_marks)
        layers.append(alt.Chart(sun_df).mark_rule(color="#f59e0b", strokeDash=[3, 3])
                      .encode(x="x:Q"))
        layers.append(alt.Chart(sun_df).mark_text(color="#d97706", fontSize=10, dy=-6, baseline="bottom")
                      .encode(x="x:Q", y=alt.value(0), text="label:N"))

    base = alt.Chart(points)
    nearest = alt.selection_point(nearest=True, on="pointermove", fields=["hour"], empty=False)
    layers += [
        base.mark_line(color="#2563eb", strokeWidth=2.5, interpolate="monotone").encode(x=x_axis, y=y_axis),
        base.mark_point(size=200, opacity=0).encode(
            x=x_axis, y=y_axis,
            tooltip=[alt.Tooltip("time:N", title="Time"), alt.Tooltip("value:Q", title="Score", format=".0f")],
        ).add_params(nearest),
        base.mark_rule(color="#2563eb", strokeDash=[4, 2]).encode(x=x_axis).transform_filter(nearest),
        base.mark_point(color="#2563eb", filled=True, size=80).encode(x=x_axis, y=y_axis)
            .transform_filter(nearest),
    ]
    return alt.layer(*layers).properties(height=260)


# ── Tab renderer ──────────────────────────────────────────────────────────────

def render_timing_tab():
    st.caption("Fish-activity forecast for your fishing spot — driven by the shared Bite Score engine.")

    col_lat, col_lon = st.columns(2)
    lat = col_lat.number_input("Latitude", value=0.0, format="%.4f", key="timing_lat")
    lon = col_lon.number_input("Longitude", value=0.0, format="%.4f", key="timing_lon")

    if lat == 0.0 and lon == 0.0:
        st.info("Enter your coordinates above to see the 14-day fish-activity forecast.")
        return

    try:
        with st.spinner("Loading 14-day forecast…"):
            forecast = fetch_forecast(lat, lon)
    except requests.RequestException as e:
        st.error(f"Bite-score service unavailable ({e}). Is omyfish-ai running at "
                 f"{settings.bite_service_url}?")
        return

    hourly = forecast["hourly"]
    if not hourly:
        st.warning("No forecast data returned for this location.")
        return

    location = reverse_geocode(round(lat, 3), round(lon, 3))
    st.subheader(f"📍 {location or f'{lat:.2f}, {lon:.2f}'}")

    # Live "right now" alert from the nowcast
    current = forecast.get("current")
    if current and (current["is_storm"] or current["is_heavy_precip"]):
        st.error("⚠️ " + ("Storm at your location right now — do not fish through lightning."
                           if current["is_storm"]
                           else "Heavy rain at your location right now — fishing is not recommended."))

    # 14 days of data: the day strip shows 7, the calendar popover all 14
    days: list[str] = []
    hours_by_day: dict[str, list[dict]] = {}
    for h in hourly:
        d = h["timestamp"][:10]
        if d not in hours_by_day:
            if len(days) == 14:
                break
            days.append(d)
            hours_by_day[d] = []
        hours_by_day[d].append(h)

    daily_scores = {d: day_window_mean(hours_by_day[d], lambda h: h["score"]) for d in days}

    sel_key = "timing_selected_day"
    if st.session_state.get(sel_key) not in days:
        st.session_state[sel_key] = days[0]

    def _day_button(col, day: str, label_top: str, key_prefix: str):
        date = datetime.fromisoformat(day)
        score = daily_scores.get(day)
        pct = "–" if score is None else f"{round(score)}%"
        selected = st.session_state[sel_key] == day
        if col.button(f"{label_top} {date.day} · {pct}", key=f"{key_prefix}_{day}",
                      type="primary" if selected else "secondary", use_container_width=True):
            st.session_state[sel_key] = day
            st.rerun()

    strip_days = days[:7]
    for col, day in zip(st.columns(len(strip_days)), strip_days):
        label = "Today" if day == days[0] else datetime.fromisoformat(day).strftime("%a")
        _day_button(col, day, label, "timing_strip")

    with st.popover("📅 Next 14 days"):
        for row in (days[:7], days[7:]):
            if row:
                for col, day in zip(st.columns(7), row):
                    _day_button(col, day, datetime.fromisoformat(day).strftime("%a"), "timing_cal")

    selected_day = st.session_state[sel_key]
    day_hours = hours_by_day[selected_day]

    # Flagged-hour alerts for the selected day
    for r in safety_ranges(day_hours):
        st.error(f"⚠️ **{_fmt_time(r['start'])}–{_fmt_time(r['end'])}:** {r['message']}")

    factor_tab = st.radio("Factor", ["Overall"] + [f.capitalize() for f in FACTORS],
                          horizontal=True, label_visibility="collapsed", key="timing_factor")
    value_of = ((lambda h: h["score"]) if factor_tab == "Overall"
                else (lambda h: h["breakdown"].get(factor_tab.lower(), 0.0)))

    st.markdown(f"**{datetime.fromisoformat(selected_day).strftime('%A, %B %-d')}**")
    gauge_score = day_window_mean(day_hours, value_of)
    st.html(_gauge_svg(gauge_score, gauge_label(factor_tab, gauge_score)))

    points = pd.DataFrame([{
        "hour": datetime.fromisoformat(h["timestamp"]).hour,
        "time": _fmt_time(datetime.fromisoformat(h["timestamp"])),
        "value": value_of(h),
    } for h in day_hours])

    majors = _windows_for_day(forecast["major_windows"], selected_day)
    minors = _windows_for_day(forecast["minor_windows"], selected_day)
    to_range = lambda w: {"x1": max(0.0, _hour_of_day(w["start"], selected_day)),
                          "x2": min(24.0, _hour_of_day(w["end"], selected_day))}

    sun_today = next((s for s in forecast["sun_times"] if s["date"] == selected_day), None)
    sun_marks = []
    if sun_today:
        for key in ("sunrise", "sunset"):
            x = _hour_of_day(sun_today[key], selected_day)
            if 0 <= x <= 24:
                sun_marks.append({"x": x, "label": f"☀ {_fmt_time(datetime.fromisoformat(sun_today[key]))}"})

    st.altair_chart(
        _activity_chart(points, [to_range(w) for w in majors], [to_range(w) for w in minors], sun_marks),
        use_container_width=True,
    )

    col_major, col_minor = st.columns(2)
    for col, title, windows in ((col_major, "Major times", majors), (col_minor, "Minor times", minors)):
        with col, st.container(border=True):
            st.markdown(f"**{title}**")
            if not windows:
                st.caption("None this day")
            for w in windows:
                st.markdown(f"🕐 {_fmt_window(w)}")
