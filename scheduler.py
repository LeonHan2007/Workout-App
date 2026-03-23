import streamlit as st
import datetime
import json
from urllib.parse import urlencode
import requests
from groq import Groq

GOOGLE_CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
REDIRECT_URI = "https://skibfit.streamlit.app"

SCOPES = "https://www.googleapis.com/auth/calendar"

groq_client = Groq(api_key=GROQ_API_KEY)


def get_google_auth_url():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def exchange_code_for_token(code: str) -> dict:
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    return resp.json()


def get_calendar_events(access_token: str, days_ahead: int = 7) -> list:
    now = datetime.datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + datetime.timedelta(days=days_ahead)).isoformat() + "Z"

    resp = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": True,
            "orderBy": "startTime",
        }
    )
    data = resp.json()
    return data.get("items", [])


def format_events_for_ai(events: list) -> str:
    if not events:
        return "No existing events."
    lines = []
    for e in events:
        title = e.get("summary", "Busy")
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", "")
        end = e.get("end", {}).get("dateTime") or e.get("end", {}).get("date", "")
        lines.append(f"- {title}: {start} to {end}")
    return "\n".join(lines)


def generate_workout_plan(events: list, workout_days: int, workouts: list) -> str:
    events_str = format_events_for_ai(events)
    workout_list = "\n".join([f"- {w.exercise} ({w.sets} sets x {w.reps} reps{f', {w.weight} {w.weight_unit}' if w.weight else ''})" for w in workouts])
    today = datetime.date.today()
    week_dates = [(today + datetime.timedelta(days=i)).strftime("%A %Y-%m-%d") for i in range(7)]

    prompt = f"""You are a fitness scheduling assistant. Given a user's Google Calendar events for the next 7 days and their saved exercises, create a workout schedule.

Today is {today.strftime("%A %Y-%m-%d")}.
The next 7 days are: {", ".join(week_dates)}.

The user wants to work out {workout_days} days this week.

Their existing calendar events (avoid scheduling workouts during these):
{events_str}

Their saved exercises:
{workout_list}

Instructions:
- Pick {workout_days} days from the next 7 days that have the most free time
- For each workout day, suggest a start time that avoids conflicts
- Split their exercises across the workout days sensibly (push/pull/legs style if possible)
- Each session should be 45-75 minutes
- Return a JSON array like this (no markdown, just raw JSON):
[
  {{
    "date": "YYYY-MM-DD",
    "start_time": "HH:MM",
    "end_time": "HH:MM",
    "title": "SkibFit Workout - Day Name",
    "description": "Exercise 1: X sets x Y reps\\nExercise 2: ..."
  }}
]"""

    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content


def add_event_to_calendar(access_token: str, event: dict):
    start_dt = f"{event['date']}T{event['start_time']}:00"
    end_dt = f"{event['date']}T{event['end_time']}:00"

    body = {
        "summary": event["title"],
        "description": event["description"],
        "start": {"dateTime": start_dt, "timeZone": "America/New_York"},
        "end": {"dateTime": end_dt, "timeZone": "America/New_York"},
    }

    resp = requests.post(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(body),
    )
    return resp.json()


def scheduler_page(user_id, workouts):
    st.subheader("📅 Workout Scheduler")

    # Handle OAuth callback
    params = st.query_params
    if "code" in params and "google_token" not in st.session_state:
        with st.spinner("Connecting to Google Calendar..."):
            token_data = exchange_code_for_token(params["code"])
            if "access_token" in token_data:
                st.session_state.google_token = token_data["access_token"]
                st.query_params.clear()
                st.rerun()
            else:
                st.error("Failed to connect Google Calendar. Please try again.")
                st.query_params.clear()
                return

    # Not connected yet
    if "google_token" not in st.session_state:
        st.write("Connect your Google Calendar to automatically schedule workouts around your existing events.")
        auth_url = get_google_auth_url()
        st.link_button("🔗 Connect Google Calendar", auth_url)
        return

    # Connected
    st.success("✅ Google Calendar connected!")

    if st.button("Disconnect Google Calendar"):
        del st.session_state.google_token
        st.rerun()

    if not workouts:
        st.warning("You have no saved exercises yet. Add some in the 'Add New Workout' menu first.")
        return

    st.markdown("---")
    workout_days = st.slider("How many days per week do you want to work out?", 1, 7, 3)
    days_ahead = st.selectbox("Schedule how far ahead?", [7, 14], format_func=lambda x: f"{x} days")

    if st.button("🤖 Generate Workout Schedule"):
        with st.spinner("Fetching your calendar events..."):
            try:
                events = get_calendar_events(st.session_state.google_token, days_ahead)
            except Exception as e:
                st.error(f"Failed to fetch calendar: {e}")
                return

        with st.spinner("AI is generating your workout plan..."):
            try:
                raw = generate_workout_plan(events, workout_days, workouts)
                # Strip markdown fences if present
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = "\n".join(raw.split("\n")[:-1])
                plan = json.loads(raw.strip())
            except Exception as e:
                st.error(f"Failed to generate plan: {e}")
                st.code(raw if 'raw' in locals() else "No response")
                return

        st.session_state.workout_plan = plan
        st.success(f"Generated {len(plan)} workout sessions!")

    if "workout_plan" in st.session_state and st.session_state.workout_plan:
        plan = st.session_state.workout_plan
        st.markdown("### Your Workout Plan")

        for i, session in enumerate(plan):
            with st.expander(f"📆 {session['title']} — {session['date']} at {session['start_time']}"):
                st.write(session["description"])

        st.markdown("---")
        if st.button("➕ Add All to Google Calendar"):
            success = 0
            for session in plan:
                try:
                    add_event_to_calendar(st.session_state.google_token, session)
                    success += 1
                except Exception as e:
                    st.error(f"Failed to add {session['title']}: {e}")
            if success:
                st.success(f"Added {success} workout sessions to your Google Calendar!")
                del st.session_state.workout_plan
