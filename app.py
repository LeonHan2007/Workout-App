import streamlit as st
from streamlit_dimensions import st_dimensions
from database_service import (
    create_user, authenticate_user, insert_workout,
    get_all_workouts, update_workout, delete_workout, workout_exists,
)
from exercise_library import EXERCISE_NAMES, get_category
from scheduler import scheduler_page

# ─────────────────────────── page config ────────────────────────────

st.title("SkibFit")

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
    # Use .pop() so missing keys never raise KeyError
    st.session_state.pop("google_token", None)
    st.session_state.pop("workout_plan", None)
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

menu = ["View Workouts", "Add New Workout", "Schedule Workouts"]
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

def _render_edit_form(w):
    """Inline edit form rendered below a workout row. Shared by mobile and desktop."""
    st.markdown("---")
    exercise = st.text_input("Exercise", value=w.exercise, key=f"exercise_{w.id}")

    col_s, col_r, col_w, col_u, col_sub = st.columns([1, 1, 2, 1, 1])
    sets   = col_s.number_input("Sets",   min_value=1,   step=1,   value=w.sets,                          key=f"sets_{w.id}")
    reps   = col_r.number_input("Reps",   min_value=1,   step=1,   value=w.reps,                          key=f"reps_{w.id}")
    weight = col_w.number_input("Weight", min_value=0.0, step=0.5, value=w.weight or 0.0, format="%.1f", key=f"weight_{w.id}")
    unit   = col_u.selectbox("", ["lbs", "kg"],
                             index=0 if (w.weight_unit or "lbs") == "lbs" else 1,
                             key=f"unit_{w.id}")

    col_sub.write("")
    col_sub.write("")
    if col_sub.button("Confirm", key=f"submit_{w.id}"):
        clean_name = exercise.strip()
        err = _validate_exercise_name(clean_name)
        if err:
            st.warning(err)
            return
        # Duplicate check: only block if the name changed AND it already exists
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

# ─────────────────────────── router ─────────────────────────────────

if choice == "Add New Workout":
    add_workout_page()
elif choice == "View Workouts":
    view_workouts_page()
elif choice == "Schedule Workouts":
    workouts = get_all_workouts(user_id)
    scheduler_page(user_id, workouts)