import datetime
import streamlit as st
from streamlit_dimensions import st_dimensions
from streamlit_cookies_manager import EncryptedCookieManager
from database_service import (
    create_user, authenticate_user, get_user_by_id, insert_workout,
    get_all_workouts, update_workout, delete_workout, workout_exists,
    start_session, delete_session,
    log_exercises_bulk,
    get_dashboard_stats, get_recent_sessions_with_logs, get_personal_records,
)
from exercise_library import EXERCISE_NAMES, get_category
from scheduler import scheduler_page
from plan import create_plan_page

# ─────────────────────────── page config ────────────────────────────

st.title("SkibFit")

# ─────────────────────────── cookie manager ─────────────────────────

_cookies = EncryptedCookieManager(
    prefix="skibfit_",
    password=st.secrets["COOKIE_SECRET"],
)
if not _cookies.ready():
    st.stop()   # wait for the cookie manager JS to load

# ─────────────────────────── session defaults ────────────────────────

def _init_session():
    defaults = {
        "user": None,
        "refresh": False,
        "edit_id": None,
        "screen_width": 1200,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

_init_session()

# Re-hydrate user from cookie if session_state was wiped by a refresh
if st.session_state.user is None:
    saved_id = _cookies.get("user_id")
    if saved_id:
        try:
            user = get_user_by_id(int(saved_id))
            if user:
                st.session_state.user = user
        except Exception:
            _cookies["user_id"] = ""
            _cookies.save()

# ─────────────────────────── responsive layout ───────────────────────

dims = st_dimensions()
st.session_state.screen_width = dims.get("width", 1200) if dims else 1200
is_mobile = st.session_state.screen_width < 600

# ─────────────────────────── helpers ────────────────────────────────

def format_weight(workout) -> str:
    """Return a display string for a workout's weight field."""
    if workout.weight:
        return f"{workout.weight:.1f} {workout.weight_unit}"
    return "Bodyweight"


def _validate_exercise_name(name: str) -> str | None:
    """Return an error message, or None if valid."""
    if not name.strip():
        return "Exercise name cannot be empty."
    return None

# ─────────────────────────── auth pages ─────────────────────────────

def login_page():
    st.subheader("Login")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login"):
        if not username.strip():
            st.warning("Please enter a username.")
        elif not password:
            st.warning("Please enter a password.")
        else:
            user = authenticate_user(username.strip(), password)
            if user:
                st.session_state.user = user
                _cookies["user_id"] = str(user.id)
                _cookies.save()
                st.success(f"Welcome back, {user.username}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")


def signup_page():
    st.subheader("Sign Up")
    new_username = st.text_input("Choose a username", key="signup_username")
    new_email = st.text_input("Email address", key="signup_email")
    new_password = st.text_input("Choose a password", type="password", key="signup_password")
    confirm_password = st.text_input("Confirm password", type="password", key="signup_confirm_password")

    if st.button("Sign Up"):
        if not new_username.strip():
            st.warning("Username cannot be empty.")
        elif not new_email.strip() or "@" not in new_email or "." not in new_email:
            st.warning("Please enter a valid email address.")
        elif len(new_password) < 8:
            st.warning("Password must be at least 8 characters long.")
        elif new_password != confirm_password:
            st.warning("Passwords do not match.")
        else:
            user = create_user(new_username.strip(), new_email.strip(), new_password)
            if user:
                st.success("Account created! Please log in.")
            else:
                st.error("Username or email already exists.")


def logout():
    st.session_state.user = None
    st.session_state.pop("google_token", None)
    st.session_state.pop("workout_plan", None)
    _cookies["user_id"] = ""
    _cookies.save()
    st.rerun()

# ─────────────────────────── auth gate ──────────────────────────────

if st.session_state.user is None:
    login_page()
    st.markdown("---")
    signup_page()
    st.stop()

# ─────────────────────────── sidebar ────────────────────────────────

st.sidebar.write(f"Logged in as: **{st.session_state.user.username}**")
if st.sidebar.button("Logout"):
    logout()

menu = ["Dashboard", "Log Workout", "My Programme", "Create Plan", "Schedule Workouts"]
choice = st.sidebar.selectbox("Menu", menu)

user_id = st.session_state.user.id

# ─────────────────────────── add workout ────────────────────────────

_CUSTOM_OPTION = "✏️  Enter a custom exercise..."
_DROPDOWN_OPTIONS = EXERCISE_NAMES + [_CUSTOM_OPTION]
_CATEGORY_BADGES = {"push": "🔴 Push", "pull": "🔵 Pull", "legs": "🟢 Legs", "core": "🟡 Core"}


def add_workout_page():
    st.subheader("Add a new workout")

    selected = st.selectbox(
        "Exercise",
        options=_DROPDOWN_OPTIONS,
        index=None,
        placeholder="Search or pick an exercise…",
    )

    if selected == _CUSTOM_OPTION:
        exercise = st.text_input("Custom exercise name").strip()
    elif selected:
        exercise = selected
        category = get_category(exercise)
        st.caption(f"Category: {_CATEGORY_BADGES.get(category, '⚪ Uncategorised')}")
    else:
        exercise = ""

    col_sets, col_reps = st.columns([1, 1])
    sets = col_sets.number_input("Sets", min_value=1, step=1)
    reps = col_reps.number_input("Reps", min_value=1, step=1)

    col_weight, col_unit = st.columns([6, 1])
    weight = col_weight.number_input("Weight", min_value=0.0, step=0.5, format="%.1f")
    unit = col_unit.selectbox("", ["lbs", "kg"], index=0)

    if st.button("Add Workout"):
        err = _validate_exercise_name(exercise)
        if err:
            st.warning(err)
        elif workout_exists(user_id, exercise):
            st.error(f"'{exercise}' is already in your workout list.")
        else:
            insert_workout(user_id, {
                "exercise": exercise,
                "sets": sets,
                "reps": reps,
                "weight": weight if weight > 0 else None,
                "weight_unit": unit if weight > 0 else None,
            })
            st.success(f"Added '{exercise}'!")

# ─────────────────────────── edit form (shared) ──────────────────────

def _exercise_selectbox_index(current_name: str) -> int:
    """Return the index of current_name in _DROPDOWN_OPTIONS, or last item (custom) if not found."""
    try:
        return _DROPDOWN_OPTIONS.index(current_name)
    except ValueError:
        return len(_DROPDOWN_OPTIONS) - 1  # fall back to custom option


def _render_edit_form(w):
    """Inline edit form rendered below a workout row. Shared by mobile and desktop."""
    st.markdown("---")

    # ── Exercise dropdown (same options as Add page) ──────────────────
    selected = st.selectbox(
        "Exercise",
        options=_DROPDOWN_OPTIONS,
        index=_exercise_selectbox_index(w.exercise),
        key=f"exercise_select_{w.id}",
    )

    if selected == _CUSTOM_OPTION:
        exercise = st.text_input(
            "Custom exercise name",
            value=w.exercise if w.exercise not in EXERCISE_NAMES else "",
            key=f"exercise_custom_{w.id}",
        ).strip()
    else:
        exercise = selected
        category = get_category(exercise)
        st.caption(f"Category: {_CATEGORY_BADGES.get(category, '⚪ Uncategorised')}")

    # ── Sets / Reps / Weight — stacked on mobile, columns on desktop ──
    if is_mobile:
        sets   = st.number_input("Sets",   min_value=1,   step=1,   value=w.sets,              key=f"sets_{w.id}")
        reps   = st.number_input("Reps",   min_value=1,   step=1,   value=w.reps,              key=f"reps_{w.id}")
        weight = st.number_input("Weight", min_value=0.0, step=0.5, value=w.weight or 0.0,
                                 format="%.1f",                                                 key=f"weight_{w.id}")
        unit   = st.selectbox("Unit", ["lbs", "kg"],
                              index=0 if (w.weight_unit or "lbs") == "lbs" else 1,             key=f"unit_{w.id}")
        confirm_btn = st.button("Confirm", key=f"submit_{w.id}", use_container_width=True)
    else:
        col_s, col_r, col_w, col_u, col_sub = st.columns([1, 1, 2, 1, 1])
        sets   = col_s.number_input("Sets",   min_value=1,   step=1,   value=w.sets,           key=f"sets_{w.id}")
        reps   = col_r.number_input("Reps",   min_value=1,   step=1,   value=w.reps,           key=f"reps_{w.id}")
        weight = col_w.number_input("Weight", min_value=0.0, step=0.5, value=w.weight or 0.0,
                                    format="%.1f",                                              key=f"weight_{w.id}")
        unit   = col_u.selectbox("", ["lbs", "kg"],
                                 index=0 if (w.weight_unit or "lbs") == "lbs" else 1,          key=f"unit_{w.id}")
        col_sub.write("")
        col_sub.write("")
        confirm_btn = col_sub.button("Confirm", key=f"submit_{w.id}")

    if confirm_btn:
        clean_name = exercise.strip()
        err = _validate_exercise_name(clean_name)
        if err:
            st.warning(err)
            return
        # Duplicate check: only block if the name changed AND it already exists elsewhere
        if clean_name.lower() != w.exercise.lower() and workout_exists(user_id, clean_name):
            st.error(f"An exercise named '{clean_name}' already exists.")
            return
        update_workout(user_id, w.id, {
            "exercise": clean_name,
            "sets": sets,
            "reps": reps,
            "weight": weight if weight > 0 else None,
            "weight_unit": unit if weight > 0 else None,
        })
        st.session_state.edit_id = None
        st.rerun()

# ─────────────────────────── view workouts ──────────────────────────

def view_workouts_page():
    st.subheader("All Workouts")
    workouts = get_all_workouts(user_id)

    if not workouts:
        st.info("No workouts logged yet.")
        return

    if is_mobile:
        _render_mobile_list(workouts)
    else:
        _render_desktop_table(workouts)


def _render_mobile_list(workouts):
    for w in workouts:
        with st.container():
            st.markdown(f"### {w.exercise}")
            st.write(f"**Sets:** {w.sets}")
            st.write(f"**Reps:** {w.reps}")
            st.write(f"**Weight:** {format_weight(w)}")

            col1, col2 = st.columns(2)
            if col1.button("Update", key=f"update_mobile_{w.id}"):
                # Toggle: close if already open, open otherwise
                st.session_state.edit_id = None if st.session_state.edit_id == w.id else w.id
                st.rerun()
            if col2.button("Delete", key=f"delete_mobile_{w.id}"):
                delete_workout(user_id, w.id)
                st.session_state.edit_id = None
                st.rerun()

            # Edit form rendered in the mobile path too
            if st.session_state.edit_id == w.id:
                _render_edit_form(w)

            st.markdown("---")


def _render_desktop_table(workouts):
    col_ex, col_sets, col_reps, col_weight, col_update, col_delete = st.columns([3, 1, 1, 2, 1.5, 1.5])
    col_ex.markdown("**Exercise**")
    col_sets.markdown("**Sets**")
    col_reps.markdown("**Reps**")
    col_weight.markdown("**Weight**")

    for w in workouts:
        col_ex, col_sets, col_reps, col_weight, col_update, col_delete = st.columns([3, 1, 1, 2, 1.5, 1.5])
        col_ex.write(w.exercise)
        col_sets.write(str(w.sets))
        col_reps.write(str(w.reps))
        col_weight.write(format_weight(w))

        if col_update.button("Update", key=f"update_{w.id}"):
            st.session_state.edit_id = None if st.session_state.edit_id == w.id else w.id
            st.rerun()

        if col_delete.button("Delete", key=f"delete_{w.id}"):
            delete_workout(user_id, w.id)
            st.session_state.edit_id = None
            st.rerun()

        if st.session_state.edit_id == w.id:
            _render_edit_form(w)


# ─────────────────────────── dashboard ──────────────────────────────

def dashboard_page():
    st.subheader(f"Welcome back, {st.session_state.user.username} 👋")

    stats = get_dashboard_stats(user_id)

    # ── Stat cards ────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total sessions",    stats.total_sessions)
    c2.metric("This week",         stats.sessions_this_week)
    c3.metric("Current streak",    f"{stats.current_streak} day{'s' if stats.current_streak != 1 else ''}")
    c4.metric("Exercises logged",  stats.total_exercises)

    if stats.favourite_day:
        st.caption(f"Your most frequent day: **{stats.favourite_day}**")

    st.markdown("---")

    # ── Personal records ──────────────────────────────────────────────
    prs = get_personal_records(user_id)
    if prs:
        st.markdown("#### Personal records")
        pr_cols = st.columns(min(len(prs), 3))
        for i, pr in enumerate(prs):
            col = pr_cols[i % 3]
            col.metric(
                label=pr.exercise,
                value=f"{pr.weight:.1f} {pr.weight_unit}",
                help=f"{pr.reps} reps — {pr.date.strftime('%b %d, %Y')}",
            )
        st.markdown("---")

    # ── Recent sessions ───────────────────────────────────────────────
    recent = get_recent_sessions_with_logs(user_id, limit=5)
    if recent:
        st.markdown("#### Recent sessions")
        for sess, logs in recent:
            day_label = f" · {sess.ppl_day}" if sess.ppl_day else ""
            header    = f"{sess.date.strftime('%A, %b %d')}{day_label}"
            with st.expander(header, expanded=False):
                if logs:
                    for log in logs:
                        weight_str = f" @ {log.weight:.1f} {log.weight_unit}" if log.weight else ""
                        st.write(f"• {log.exercise} — {log.sets}×{log.reps}{weight_str}")
                else:
                    st.caption("No exercises recorded for this session.")
                if st.button("Delete session", key=f"del_sess_{sess.id}", type="secondary"):
                    delete_session(user_id, sess.id)
                    st.rerun()
    else:
        st.info("No sessions logged yet. Head to **Log Workout** to record your first session.")

# ─────────────────────────── log workout ────────────────────────────

def log_workout_page():
    st.subheader("Log a workout")

    # ── Session metadata ──────────────────────────────────────────────
    col_date, col_day = st.columns([1, 1])
    session_date = col_date.date_input("Date", value=datetime.date.today())
    ppl_day      = col_day.selectbox("Day type", ["", "Push", "Pull", "Legs"], index=0,
                                     format_func=lambda x: x or "— select —")

    notes = st.text_area("Notes (optional)", height=68, placeholder="How did it feel? Any PRs?")

    st.markdown("---")
    st.markdown("#### Exercises")

    # ── Build exercise rows from the user's programme as a starting point
    template = get_all_workouts(user_id)

    # Determine how many rows to show — persisted in session state
    key_rows = f"log_row_count_{user_id}"
    if key_rows not in st.session_state:
        st.session_state[key_rows] = max(len(template), 1)
    n_rows = st.session_state[key_rows]

    rows: list[dict] = []
    for i in range(n_rows):
        tmpl = template[i] if i < len(template) else None
        c_ex, c_s, c_r, c_w, c_u = (
            st.columns([3, 1, 1, 2, 1]) if not is_mobile
            else st.columns([1, 1])     # mobile: exercise full-width, then 2-col numbers
        )

        if is_mobile:
            # On mobile split into two rows for readability
            ex_sel = st.selectbox(
                f"Exercise {i+1}",
                options=_DROPDOWN_OPTIONS,
                index=_DROPDOWN_OPTIONS.index(tmpl.exercise) if tmpl and tmpl.exercise in _DROPDOWN_OPTIONS else len(_DROPDOWN_OPTIONS) - 1,
                key=f"log_ex_{i}",
            )
            if ex_sel == _CUSTOM_OPTION:
                exercise = st.text_input("Custom name", value=tmpl.exercise if tmpl and tmpl.exercise not in EXERCISE_NAMES else "", key=f"log_ex_custom_{i}").strip()
            else:
                exercise = ex_sel
            mc1, mc2, mc3, mc4 = st.columns(4)
            sets   = mc1.number_input("Sets",   min_value=1,   step=1,   value=tmpl.sets   if tmpl else 3,        key=f"log_s_{i}")
            reps   = mc2.number_input("Reps",   min_value=1,   step=1,   value=tmpl.reps   if tmpl else 10,       key=f"log_r_{i}")
            weight = mc3.number_input("Weight", min_value=0.0, step=0.5, value=tmpl.weight or 0.0 if tmpl else 0.0, format="%.1f", key=f"log_w_{i}")
            unit   = mc4.selectbox("Unit", ["lbs", "kg"], index=0 if not tmpl or (tmpl.weight_unit or "lbs") == "lbs" else 1, key=f"log_u_{i}")
        else:
            ex_sel = c_ex.selectbox(
                "Exercise" if i == 0 else "",
                options=_DROPDOWN_OPTIONS,
                index=_DROPDOWN_OPTIONS.index(tmpl.exercise) if tmpl and tmpl.exercise in _DROPDOWN_OPTIONS else len(_DROPDOWN_OPTIONS) - 1,
                key=f"log_ex_{i}",
                label_visibility="visible" if i == 0 else "collapsed",
            )
            if ex_sel == _CUSTOM_OPTION:
                exercise = st.text_input("Custom", value=tmpl.exercise if tmpl and tmpl.exercise not in EXERCISE_NAMES else "", key=f"log_ex_custom_{i}").strip()
            else:
                exercise = ex_sel
            sets   = c_s.number_input("Sets"   if i == 0 else "", min_value=1,   step=1,   value=tmpl.sets   if tmpl else 3,        key=f"log_s_{i}", label_visibility="visible" if i == 0 else "collapsed")
            reps   = c_r.number_input("Reps"   if i == 0 else "", min_value=1,   step=1,   value=tmpl.reps   if tmpl else 10,       key=f"log_r_{i}", label_visibility="visible" if i == 0 else "collapsed")
            weight = c_w.number_input("Weight" if i == 0 else "", min_value=0.0, step=0.5, value=tmpl.weight or 0.0 if tmpl else 0.0, format="%.1f", key=f"log_w_{i}", label_visibility="visible" if i == 0 else "collapsed")
            unit   = c_u.selectbox("Unit" if i == 0 else "", ["lbs", "kg"], index=0 if not tmpl or (tmpl.weight_unit or "lbs") == "lbs" else 1, key=f"log_u_{i}", label_visibility="visible" if i == 0 else "collapsed")

        rows.append({
            "exercise": exercise,
            "sets":     sets,
            "reps":     reps,
            "weight":   weight if weight > 0 else None,
            "weight_unit": unit if weight > 0 else None,
        })

        if is_mobile:
            st.markdown("---")

    # ── Add / remove row buttons ──────────────────────────────────────
    btn_add, btn_rem = st.columns(2)
    if btn_add.button("＋ Add exercise", use_container_width=True):
        st.session_state[key_rows] += 1
        st.rerun()
    if btn_rem.button("－ Remove last", use_container_width=True) and n_rows > 1:
        st.session_state[key_rows] -= 1
        st.rerun()

    st.markdown("---")

    # ── Save ──────────────────────────────────────────────────────────
    if st.button("Save session", type="primary", use_container_width=True):
        valid_rows = [r for r in rows if r["exercise"] and r["exercise"] != _CUSTOM_OPTION]
        if not valid_rows:
            st.warning("Add at least one exercise before saving.")
        else:
            ws = start_session(
                user_id=user_id,
                ppl_day=ppl_day or None,
                notes=notes.strip() or None,
                date=session_date,
            )
            log_exercises_bulk(ws.id, user_id, valid_rows)
            st.session_state[key_rows] = max(len(template), 1)  # reset row count
            st.success(f"Session saved — {len(valid_rows)} exercise(s) logged!")
            st.rerun()

# ─────────────────────────── router ─────────────────────────────────

if choice == "Dashboard":
    dashboard_page()
elif choice == "Log Workout":
    log_workout_page()
elif choice == "My Programme":
    st.subheader("My Programme")
    tab_view, tab_add = st.tabs(["View / Edit", "Add Exercise"])
    with tab_view:
        view_workouts_page()
    with tab_add:
        add_workout_page()
elif choice == "Create Plan":
    create_plan_page(user_id)
elif choice == "Schedule Workouts":
    workouts = get_all_workouts(user_id)
    scheduler_page(user_id, workouts)