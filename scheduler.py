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


def generate_workout_plan(
    events: list,
    workout_days: int,
    workouts: list,
    split: dict[str, list],
) -> list[dict]:
    """Call the LLM and return a parsed list of workout session dicts."""
    today      = datetime.date.today()
    week_dates = [
        (today + datetime.timedelta(days=i)).strftime("%A %Y-%m-%d")
        for i in range(7)
    ]

    prompt = f"""You are a fitness scheduling assistant. Your job is to pick dates and times for a pre-determined push/pull/legs workout split.

Today is {today.strftime("%A %Y-%m-%d")}.
The next 7 days are: {", ".join(week_dates)}.

The user's existing calendar events (do NOT schedule workouts during these times):
{_format_events_for_prompt(events)}

The workout split to schedule (exercises are already decided — do not change them):
{_format_split_for_prompt(split)}

Rules:
- Schedule exactly {workout_days} sessions, one per split day listed above, in order.
- Pick the {workout_days} days with the most free time, avoiding event conflicts.
- Each session is 60 minutes; set end_time = start_time + 60 min.
- Prefer morning (07:00–09:00) or evening (17:00–19:00) slots when free.
- The "description" field must list every exercise exactly as given, one per line,
  in the format: "Exercise name: X sets x Y reps" (add weight if present).
- Return ONLY a raw JSON array — no markdown, no explanation, no code fences:
[
  {{
    "date": "YYYY-MM-DD",
    "start_time": "HH:MM",
    "end_time": "HH:MM",
    "title": "SkibFit — Push",
    "description": "Bench Press: 4 sets x 8 reps @ 185 lbs\\nOverhead Press: 3 sets x 10 reps"
  }}
]"""

    response = _groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = response.choices[0].message.content.strip()

    # Strip markdown fences defensively
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
    raw = raw.rstrip("`").strip()

    return json.loads(raw)

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
    workout_days = st.slider("Days per week to work out", 1, 7, 3)
    days_ahead   = st.selectbox(
        "Schedule how far ahead?", [7, 14],
        format_func=lambda x: f"{x} days",
    )

    # Build and preview the PPL split before the user generates a plan
    split = build_ppl_split(workouts, workout_days)
    _render_split_preview(split)

    if st.button("Generate Workout Schedule"):
        with st.spinner("Fetching your calendar events..."):
            try:
                events = get_calendar_events(st.session_state.google_token, days_ahead)
            except Exception as exc:
                st.error(f"Failed to fetch calendar: {exc}")
                return

        with st.spinner("AI is scheduling your sessions..."):
            try:
                plan = generate_workout_plan(events, workout_days, workouts, split)
            except json.JSONDecodeError:
                st.error("The AI returned an unexpected format. Please try again.")
                return
            except Exception as exc:
                st.error(f"Failed to generate plan: {exc}")
                return

        st.session_state.workout_plan = plan
        st.success(f"Scheduled {len(plan)} session(s)!")

    _render_plan()


def _render_split_preview(split: dict[str, list]):
    """Show the user how their exercises were classified before generating."""
    st.markdown("#### Push/Pull/Legs split")
    cols = st.columns(len(split))
    for col, (day_label, exercises) in zip(cols, split.items()):
        col.markdown(f"**{day_label}**")
        if exercises:
            for w in exercises:
                col.write(f"• {w.exercise}")
        else:
            col.caption("No exercises classified here yet.")


def _render_plan():
    """Display the cached plan and let the user push it to Google Calendar."""
    plan = st.session_state.get("workout_plan")
    if not plan:
        return

    st.markdown("### Your Workout Plan")
    for session in plan:
        label = f"{session['title']} — {session['date']} at {session['start_time']}"
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