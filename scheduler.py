import datetime
import json
from urllib.parse import urlencode

import requests
import streamlit as st
from groq import Groq

# ─────────────────────────── config ──────────────────────────────────

GOOGLE_CLIENT_ID     = st.secrets["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
GROQ_API_KEY         = st.secrets["GROQ_API_KEY"]
REDIRECT_URI         = "https://skibfit.streamlit.app"
SCOPES               = "https://www.googleapis.com/auth/calendar"

_groq_client = Groq(api_key=GROQ_API_KEY)

# ─────────────────────────── Google OAuth ────────────────────────────

def get_google_auth_url() -> str:
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def exchange_code_for_token(code: str) -> dict:
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

# ─────────────────────────── Google Calendar ─────────────────────────

def get_calendar_events(access_token: str, days_ahead: int = 7) -> list:
    now      = datetime.datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + datetime.timedelta(days=days_ahead)).isoformat() + "Z"

    resp = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "timeMin":      time_min,
            "timeMax":      time_max,
            "singleEvents": True,
            "orderBy":      "startTime",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def add_event_to_calendar(access_token: str, event: dict) -> dict:
    start_dt = f"{event['date']}T{event['start_time']}:00"
    end_dt   = f"{event['date']}T{event['end_time']}:00"

    body = {
        "summary":     event["title"],
        "description": event["description"],
        "start":       {"dateTime": start_dt, "timeZone": "America/New_York"},
        "end":         {"dateTime": end_dt,   "timeZone": "America/New_York"},
    }

    resp = requests.post(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        },
        data=json.dumps(body),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

# ─────────────────────────── PPL classification ──────────────────────

from exercise_library import get_category

_FALLBACK_CYCLE = ("push", "pull", "legs")


def build_ppl_split(workouts: list, workout_days: int) -> dict[str, list]:
    """
    Return a dict mapping day-label ('Push', 'Pull', 'Legs', 'Push 2', …)
    to the list of workout objects for that session.

    Strategy:
    - Classify every exercise into push/pull/legs.
    - Unrecognised exercises are distributed evenly across the three buckets.
    - Repeat the Push/Pull/Legs cycle until workout_days sessions are filled.
    """
    buckets: dict[str, list] = {"push": [], "pull": [], "legs": []}
    unclassified = []

    for w in workouts:
        cat = get_category(w.exercise)
        if cat in buckets:
            # push / pull / legs go straight into their bucket
            buckets[cat].append(w)
        else:
            # core and any unrecognised custom exercises go to round-robin
            unclassified.append(w)

    # Distribute unclassified/core exercises round-robin across the three buckets
    for i, w in enumerate(unclassified):
        buckets[_FALLBACK_CYCLE[i % 3]].append(w)

    # Build the session list by cycling Push → Pull → Legs
    sessions: dict[str, list] = {}
    counts: dict[str, int] = {"push": 0, "pull": 0, "legs": 0}

    for i in range(workout_days):
        cat = _FALLBACK_CYCLE[i % 3]
        counts[cat] += 1
        label = cat.capitalize() if counts[cat] == 1 else f"{cat.capitalize()} {counts[cat]}"
        sessions[label] = buckets[cat]

    return sessions


# ─────────────────────────── prompt helpers ──────────────────────────

def _format_events_for_prompt(events: list) -> str:
    if not events:
        return "No existing events."
    lines = []
    for e in events:
        title = e.get("summary", "Busy")
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", "")
        end   = e.get("end",   {}).get("dateTime") or e.get("end",   {}).get("date", "")
        lines.append(f"- {title}: {start} to {end}")
    return "\n".join(lines)


def _format_split_for_prompt(split: dict[str, list]) -> str:
    lines = []
    for day_label, exercises in split.items():
        lines.append(f"{day_label} day:")
        for w in exercises:
            weight_str = f", {w.weight} {w.weight_unit}" if w.weight else ""
            lines.append(f"  - {w.exercise} ({w.sets} sets x {w.reps} reps{weight_str})")
    return "\n".join(lines)


# ─────────────────────────── scheduling logic ────────────────────────

_TIME_WINDOWS = {
    "Morning (6:00–9:00)":     (datetime.time(6, 0),  datetime.time(9, 0)),
    "Afternoon (12:00–15:00)": (datetime.time(12, 0), datetime.time(15, 0)),
    "Evening (17:00–20:00)":   (datetime.time(17, 0), datetime.time(20, 0)),
}


def _parse_event_times(event: dict) -> tuple[datetime.datetime, datetime.datetime] | None:
    """Return (start, end) as naive datetimes, or None for all-day / unparseable events."""
    try:
        raw_start = event.get("start", {}).get("dateTime")
        raw_end   = event.get("end",   {}).get("dateTime")
        if not raw_start or not raw_end:
            return None   # all-day event — skip
        # Strip timezone suffix for naive comparison
        start = datetime.datetime.fromisoformat(raw_start[:19])
        end   = datetime.datetime.fromisoformat(raw_end[:19])
        return start, end
    except Exception:
        return None


WORKOUT_DURATION_MINUTES = 60
BUFFER_MINUTES = 15
_TOTAL_BLOCK_MINUTES = BUFFER_MINUTES + WORKOUT_DURATION_MINUTES + BUFFER_MINUTES  # 90


def _slot_is_free(
    date: datetime.date,
    start_time: datetime.time,
    busy_intervals: list[tuple[datetime.datetime, datetime.datetime]],
) -> bool:
    """
    Return True if the full 90-minute block (15-min buffer + 60-min workout +
    15-min buffer) starting at start_time has no overlap with any busy interval.
    start_time is the intended workout start — buffers are applied internally.
    """
    block_start = datetime.datetime.combine(date, start_time) - datetime.timedelta(minutes=BUFFER_MINUTES)
    block_end   = block_start + datetime.timedelta(minutes=_TOTAL_BLOCK_MINUTES)
    for busy_start, busy_end in busy_intervals:
        if block_start < busy_end and block_end > busy_start:
            return False
    return True


def _find_free_slot(
    date: datetime.date,
    preferred_start: datetime.time,
    preferred_end: datetime.time,
    busy_intervals: list[tuple[datetime.datetime, datetime.datetime]],
) -> datetime.time | None:
    """
    Try every 30-min slot within the preferred window first, then fall back to
    the full day (7:00–21:00). Each candidate is the workout start time;
    the 15-min pre-buffer is factored into the free-slot check.
    Returns the workout start time of the first free slot, or None if fully blocked.
    """
    def _candidates(t_start: datetime.time, t_end: datetime.time):
        # Earliest candidate must leave room for the pre-buffer
        earliest = (datetime.datetime.combine(datetime.date.today(), t_start)
                    + datetime.timedelta(minutes=BUFFER_MINUTES))
        end = datetime.datetime.combine(datetime.date.today(), t_end)
        cur = earliest
        while cur + datetime.timedelta(minutes=WORKOUT_DURATION_MINUTES + BUFFER_MINUTES) <= end:
            yield cur.time()
            cur += datetime.timedelta(minutes=30)

    # Preferred window first
    for slot in _candidates(preferred_start, preferred_end):
        if _slot_is_free(date, slot, busy_intervals):
            return slot

    # Full-day fallback
    for slot in _candidates(datetime.time(7, 0), datetime.time(21, 0)):
        if _slot_is_free(date, slot, busy_intervals):
            return slot

    return None   # day is fully blocked


def _pick_distributed_dates(
    candidate_dates: list[datetime.date],
    n: int,
    busy_intervals: list[tuple[datetime.datetime, datetime.datetime]],
    preferred_start: datetime.time,
    preferred_end: datetime.time,
) -> list[tuple[datetime.date, datetime.time]]:
    """
    Pick n dates from candidate_dates such that:
      1. Every date has a free slot (preferred window or fallback).
      2. No two sessions are on consecutive days (at least 1 rest day between).
      3. Sessions are spread as evenly as possible across the window — greedy
         pick the earliest date that is >= (last_picked + ideal_gap) and not
         the day after the last pick. If no such date exists before the window
         runs out, fall back to the next available date with at least 1 rest day.
    Returns a list of (date, start_time) tuples in chronological order.
    """
    # Build list of free (date, slot) pairs
    free: list[tuple[datetime.date, datetime.time]] = []
    for d in candidate_dates:
        slot = _find_free_slot(d, preferred_start, preferred_end, busy_intervals)
        if slot is not None:
            free.append((d, slot))

    if len(free) < n:
        raise ValueError(
            f"Not enough free days found ({len(free)}) to schedule {n} sessions. "
            "Try a longer scheduling window or fewer workout days."
        )

    if n == 1:
        return [free[0]]

    total_span = (free[-1][0] - free[0][0]).days
    ideal_gap  = total_span / (n - 1) if n > 1 else 2

    # Only enforce the minimum-rest-day rule if it's geometrically possible.
    # With n sessions in `total_span` days, you need at least (n-1) gap days.
    # If ideal_gap >= 2 there's room for a rest day between every session.
    min_gap = 2 if ideal_gap >= 2 else 1   # 1 = just "not the same day"

    chosen = [free[0]]

    for k in range(1, n):
        last_date = chosen[-1][0]
        target    = chosen[0][0] + datetime.timedelta(days=round(ideal_gap * k))

        eligible = [f for f in free if f[0] >= last_date + datetime.timedelta(days=min_gap)]
        if not eligible:
            # Last resort: just take the next available date after the last pick
            eligible = [f for f in free if f[0] > last_date]
        if not eligible:
            break

        best = min(eligible, key=lambda f: abs((f[0] - target).days))
        chosen.append(best)

    return chosen


def generate_workout_plan(
    events: list,
    workout_days: int,
    workouts: list,
    split: dict[str, list],
    preferred_time: str = "Evening (17:00–20:00)",
) -> list[dict]:
    """
    Deterministically schedule workout_days sessions using Python logic, then
    use the LLM only to format the description strings.
    """
    today = datetime.date.today()
    days_ahead = st.session_state.get("_scheduler_days_ahead", 30)
    candidate_dates = [
        today + datetime.timedelta(days=i)
        for i in range(1, days_ahead + 1)
    ]

    pref_start, pref_end = _TIME_WINDOWS.get(
        preferred_time, (datetime.time(17, 0), datetime.time(20, 0))
    )

    # Parse all calendar events into busy intervals once
    busy_intervals = [t for e in events if (t := _parse_event_times(e)) is not None]

    # Pick evenly-spaced dates with free slots
    chosen = _pick_distributed_dates(
        candidate_dates, workout_days, busy_intervals, pref_start, pref_end
    )

    # Build the plan — use LLM only for exercise description formatting
    plan = []
    for (date, start_time), (day_label, exercises) in zip(chosen, split.items()):
        end_time = (
            datetime.datetime.combine(date, start_time) + datetime.timedelta(minutes=WORKOUT_DURATION_MINUTES)
        ).time()

        description_lines = []
        for w in exercises:
            weight_str = f" @ {w.weight:.1f} {w.weight_unit}" if w.weight else ""
            description_lines.append(f"{w.exercise}: {w.sets} sets x {w.reps} reps{weight_str}")

        plan.append({
            "date":        date.isoformat(),
            "start_time":  start_time.strftime("%H:%M"),
            "end_time":    end_time.strftime("%H:%M"),
            "title":       f"SkibFit — {day_label}",
            "description": "\n".join(description_lines),
        })

    return plan

# ─────────────────────────── Streamlit page ──────────────────────────

def _handle_oauth_callback():
    """Exchange the OAuth code for a token and store it in session state."""
    params = st.query_params
    if "code" not in params or "google_token" in st.session_state:
        return
    with st.spinner("Connecting to Google Calendar..."):
        try:
            token_data = exchange_code_for_token(params["code"])
        except Exception as exc:
            st.error(f"OAuth error: {exc}")
            st.query_params.clear()
            return
        if "access_token" not in token_data:
            st.error("Failed to connect Google Calendar. Please try again.")
            st.query_params.clear()
            return
        st.session_state.google_token = token_data["access_token"]
        st.query_params.clear()
        st.rerun()


def _connect_section():
    """Shown when the user hasn't linked Google Calendar yet."""
    st.write(
        "Connect your Google Calendar to automatically schedule workouts "
        "around your existing events."
    )
    st.link_button("Connect Google Calendar", get_google_auth_url())


def _plan_section(workouts: list):
    """Shown when the user is connected and has saved exercises."""
    st.success("Google Calendar connected!")
    if st.button("Disconnect Google Calendar"):
        st.session_state.pop("google_token", None)
        st.session_state.pop("workout_plan", None)
        st.rerun()

    st.markdown("---")
    days_ahead = st.selectbox(
        "Schedule how far ahead?", [7, 14, 30, 60],
        format_func=lambda x: f"{x} days",
    )
    st.session_state["_scheduler_days_ahead"] = days_ahead

    preferred_time = st.selectbox(
        "When do you prefer to work out?",
        ["Morning (6:00–9:00)", "Afternoon (12:00–15:00)", "Evening (17:00–20:00)"],
    )

    # Derive workout_days from the number of distinct plan days; default to 3
    distinct_days = len(set(w.plan_day for w in workouts if w.plan_day)) or 3
    split = build_ppl_split(workouts, distinct_days)
    workout_days = len(split)
    if st.button("Generate Workout Schedule"):
        with st.spinner("Fetching your calendar events..."):
            try:
                events = get_calendar_events(st.session_state.google_token, days_ahead)
            except Exception as exc:
                st.error(f"Failed to fetch calendar: {exc}")
                return

        with st.spinner("AI is scheduling your sessions..."):
            try:
                plan = generate_workout_plan(events, workout_days, workouts, split, preferred_time)
            except json.JSONDecodeError:
                st.error("The AI returned an unexpected format. Please try again.")
                return
            except Exception as exc:
                st.error(f"Failed to generate plan: {exc}")
                return

        st.session_state.workout_plan = plan
        st.success(f"Scheduled {len(plan)} session(s)!")

    _render_plan()



def _color_for_title(title: str) -> str:
    t = title.lower()
    if "push" in t:  return "#ef4444"   # red
    if "pull" in t:  return "#3b82f6"   # blue
    if "leg"  in t:  return "#22c55e"   # green
    return "#a855f7"                     # purple fallback


def _render_plan():
    """Display the cached plan as a navigable weekly calendar grid."""
    plan = st.session_state.get("workout_plan")
    if not plan:
        return

    from collections import defaultdict

    st.markdown("### Your Workout Schedule")

    # ── Build week index ──────────────────────────────────────────────
    # Anchor all weeks to the Monday of the first session's week
    first_date   = datetime.date.fromisoformat(plan[0]["date"])
    first_monday = first_date - datetime.timedelta(days=first_date.weekday())

    # Group sessions by which Monday their week starts on
    weeks_map: dict[datetime.date, list] = defaultdict(list)
    for session in plan:
        d      = datetime.date.fromisoformat(session["date"])
        monday = d - datetime.timedelta(days=d.weekday())
        weeks_map[monday].append(session)

    all_mondays = sorted(weeks_map.keys())

    # Also include any weeks between first and last that have NO sessions
    # so the arrows can browse empty weeks too
    if all_mondays:
        span_monday = all_mondays[0]
        last_monday = all_mondays[-1]
        while span_monday <= last_monday:
            if span_monday not in weeks_map:
                weeks_map[span_monday] = []   # empty week placeholder
            span_monday += datetime.timedelta(weeks=1)
        all_mondays = sorted(weeks_map.keys())

    total_weeks = len(all_mondays)

    # ── Week navigation state ─────────────────────────────────────────
    if "cal_week_idx" not in st.session_state or st.session_state.get("_cal_plan_id") != id(plan):
        st.session_state.cal_week_idx  = 0
        st.session_state._cal_plan_id  = id(plan)

    idx = st.session_state.cal_week_idx
    idx = max(0, min(idx, total_weeks - 1))   # clamp

    # ── Navigation arrows ─────────────────────────────────────────────
    nav_l, nav_mid, nav_r = st.columns([1, 6, 1])
    if nav_l.button("←", disabled=(idx == 0), key="cal_prev"):
        st.session_state.cal_week_idx = idx - 1
        st.rerun()
    if nav_r.button("→", disabled=(idx == total_weeks - 1), key="cal_next"):
        st.session_state.cal_week_idx = idx + 1
        st.rerun()

    week_monday      = all_mondays[idx]
    sessions_in_week = weeks_map[week_monday]
    nav_mid.markdown(
        f"<div style='text-align:center;font-weight:600;padding-top:6px;'>"
        f"Week of {week_monday.strftime('%B %d, %Y')}</div>",
        unsafe_allow_html=True,
    )

    # ── Calendar grid ─────────────────────────────────────────────────
    DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    day_map: dict[int, dict] = {}
    for sess in sessions_in_week:
        d = datetime.date.fromisoformat(sess["date"])
        day_map[d.weekday()] = sess

    if not sessions_in_week:
        st.caption("No workouts scheduled this week.")
    else:
        cols = st.columns(7)
        for i, (col, day_label) in enumerate(zip(cols, DAY_LABELS)):
            date_for_col = week_monday + datetime.timedelta(days=i)
            sess         = day_map.get(i)

            if sess:
                color        = _color_for_title(sess["title"])
                session_type = sess["title"].replace("SkibFit — ", "").replace("SkibFit - ", "")
                col.markdown(
                    f"""<div style="background:{color};border-radius:8px;padding:6px 4px;text-align:center;color:white;">
                    <div style="font-size:0.65rem;opacity:0.85;">{day_label}</div>
                    <div style="font-size:0.7rem;font-weight:700;">{date_for_col.day}</div>
                    <div style="font-size:0.6rem;margin-top:2px;">{session_type}</div>
                    <div style="font-size:0.55rem;opacity:0.85;">{sess["start_time"]}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            else:
                is_today = date_for_col == datetime.date.today()
                border   = "2px solid #6366f1" if is_today else "1px solid #e5e7eb"
                bg       = "#f0f0ff"           if is_today else "#f9fafb"
                col.markdown(
                    f"""<div style="border:{border};background:{bg};border-radius:8px;padding:6px 4px;text-align:center;color:#9ca3af;">
                    <div style="font-size:0.65rem;">{day_label}</div>
                    <div style="font-size:0.7rem;font-weight:600;color:#374151;">{date_for_col.day}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

    # ── Legend ────────────────────────────────────────────────────────
    st.markdown(
        """<div style="display:flex;gap:12px;flex-wrap:wrap;margin:8px 0 12px;">
        <span style="display:flex;align-items:center;gap:4px;font-size:0.75rem;">
            <span style="width:12px;height:12px;background:#ef4444;border-radius:3px;display:inline-block;"></span> Push
        </span>
        <span style="display:flex;align-items:center;gap:4px;font-size:0.75rem;">
            <span style="width:12px;height:12px;background:#3b82f6;border-radius:3px;display:inline-block;"></span> Pull
        </span>
        <span style="display:flex;align-items:center;gap:4px;font-size:0.75rem;">
            <span style="width:12px;height:12px;background:#22c55e;border-radius:3px;display:inline-block;"></span> Legs
        </span>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Session detail expanders (all sessions, not just current week) ─
    st.markdown("#### Session details")
    for session in plan:
        d     = datetime.date.fromisoformat(session["date"])
        label = f"{session['title']} — {d.strftime('%A, %b %d')} at {session['start_time']}"
        with st.expander(label):
            st.write(session["description"])

    st.markdown("---")
    if st.button("Add All to Google Calendar"):
        success = 0
        for session in plan:
            try:
                add_event_to_calendar(st.session_state.google_token, session)
                success += 1
            except Exception as exc:
                st.error(f"Failed to add '{session['title']}': {exc}")
        if success:
            st.success(f"Added {success} workout session(s) to your Google Calendar!")
            st.session_state.pop("workout_plan", None)


def scheduler_page(user_id: int, workouts: list):
    st.subheader("Workout Scheduler")

    _handle_oauth_callback()

    if "google_token" not in st.session_state:
        _connect_section()
        return

    if not workouts:
        st.warning("No saved exercises yet. Add some in 'Add New Workout' first.")
        return

    _plan_section(workouts)