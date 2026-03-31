"""
plan.py — "Create Plan" page.

Flow:
  1. If user has no profile → onboarding wizard (goal, experience, days, equipment, focus)
  2. Offer: "Generate with AI" or "Build manually"
  3. AI path  → call Groq, parse JSON, show preview, let user edit before saving
  4. Manual   → day tabs with searchable exercise multi-selects, inline sets/reps/weight
  5. Save     → write to DB via save_plan(), set has_plan = True
"""

import json

import streamlit as st
from groq import Groq

from database_service import (
    get_profile, save_profile, has_active_plan,
    save_plan, get_plan_by_day,
)
from exercise_library import EXERCISE_NAMES, get_category

# ─────────────────────────── constants ───────────────────────────────

GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
_groq        = Groq(api_key=GROQ_API_KEY)

GOALS = [
    "Hypertrophy / Appearance",
    "Strength",
    "Athletic Performance",
    "Weight Loss / Conditioning",
    "General Fitness",
]

EXPERIENCE_LEVELS = ["Beginner (< 1 year)", "Intermediate (1–3 years)", "Advanced (3+ years)"]

EQUIPMENT_OPTIONS = ["Full gym", "Dumbbells only", "Bodyweight only"]

FOCUS_OPTIONS = [
    "Chest", "Back", "Shoulders", "Arms", "Legs", "Glutes", "Core", "Cardio",
]

# split_type → ordered list of day labels
SPLIT_TEMPLATES: dict[str, list[str]] = {
    "Push / Pull / Legs (3-day)":  ["Push", "Pull", "Legs"],
    "Push / Pull / Legs (6-day)":  ["Push", "Pull", "Legs", "Push 2", "Pull 2", "Legs 2"],
    "Upper / Lower (4-day)":       ["Upper A", "Lower A", "Upper B", "Lower B"],
    "Full Body (3-day)":           ["Full Body A", "Full Body B", "Full Body C"],
    "Bro Split (5-day)":           ["Chest", "Back", "Shoulders", "Arms", "Legs"],
    "Custom":                      [],   # user defines day names
}

# ─────────────────────────── helpers ─────────────────────────────────

def _exercises_for_equipment(equipment: str) -> list[str]:
    """Filter library to equipment-appropriate exercises."""
    if equipment == "Bodyweight only":
        keywords = ("bodyweight", "push-up", "pull-up", "chin-up", "dip",
                    "inverted", "plank", "crunch", "lunge", "squat", "pistol",
                    "nordic", "dragon", "hollow", "toes", "l-sit", "dead bug",
                    "glute bridge", "wall sit", "jump", "bicycle", "russian")
        return [n for n in EXERCISE_NAMES if any(k in n.lower() for k in keywords)]
    if equipment == "Dumbbells only":
        blocked = ("barbell", "cable", "machine", "smith", "rack", "t-bar",
                   "ez-bar", "preacher", "leg press", "hack squat", "lat pulldown",
                   "seated cable", "pec deck", "pendlay", "zercher")
        return [n for n in EXERCISE_NAMES if not any(k in n.lower() for k in blocked)]
    return EXERCISE_NAMES   # full gym — everything


def _rep_range(goal: str, experience: str) -> tuple[int, int]:
    """Return (low, high) rep range appropriate for goal."""
    if "Strength" in goal:
        return (3, 6)
    if "Hypertrophy" in goal:
        return (8, 12) if "Beginner" not in experience else (10, 15)
    if "Athletic" in goal:
        return (5, 8)
    if "Weight Loss" in goal:
        return (12, 20)
    return (10, 15)   # General Fitness


def _sets(goal: str, experience: str) -> int:
    if "Beginner" in experience:
        return 3
    if "Strength" in goal:
        return 5
    if "Hypertrophy" in goal:
        return 4
    return 3

# ─────────────────────────── AI generation ───────────────────────────

def _build_ai_prompt(profile: dict, available_exercises: list[str]) -> str:
    reps_lo, reps_hi = _rep_range(profile["goal"], profile["experience"])
    sets_n            = _sets(profile["goal"], profile["experience"])
    split_days        = SPLIT_TEMPLATES.get(profile["split_type"], ["Day 1"])
    focus             = profile.get("focus_areas") or "No specific focus"

    ex_by_cat = {}
    for name in available_exercises:
        cat = get_category(name) or "other"
        ex_by_cat.setdefault(cat, []).append(name)

    ex_list_str = "\n".join(
        f"{cat.capitalize()}: {', '.join(names)}"
        for cat, names in ex_by_cat.items()
    )

    return f"""You are an expert strength and conditioning coach creating a personalised workout plan.

User profile:
- Goal: {profile["goal"]}
- Experience: {profile["experience"]}
- Training days per week: {profile["days_per_week"]}
- Equipment: {profile["equipment"]}
- Focus areas: {focus}
- Split: {profile["split_type"]}
- Days in split: {", ".join(split_days)}

Guidelines:
- Rep range for this goal/experience: {reps_lo}–{reps_hi} reps
- Default sets: {sets_n} sets per exercise
- 4–6 exercises per day for beginners, 5–8 for intermediate/advanced
- Prioritise compound movements first, isolation second
- Respect the split structure — push muscles on Push days, etc.
- Emphasise focus areas without neglecting balance
- Only use exercises from the provided library

Available exercises by category:
{ex_list_str}

Return ONLY a raw JSON array — no markdown, no explanation, no code fences.
Each object represents one exercise:
[
  {{
    "plan_day": "Push",
    "sort_order": 0,
    "exercise": "Barbell Bench Press",
    "sets": 4,
    "reps": 8,
    "weight": null,
    "weight_unit": "lbs"
  }}
]

Include every day: {", ".join(split_days)}.
"""


def generate_ai_plan(profile: dict, available_exercises: list[str]) -> list[dict]:
    prompt   = _build_ai_prompt(profile, available_exercises)
    response = _groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
    raw = raw.rstrip("`").strip()
    return json.loads(raw)

# ─────────────────────────── onboarding wizard ───────────────────────

def _onboarding_step() -> dict | None:
    """
    Multi-step onboarding form. Stores progress in session_state.
    Returns the completed profile dict when all steps are done, else None.
    """
    if "onboard_step" not in st.session_state:
        st.session_state.onboard_step = 1

    step = st.session_state.onboard_step
    total = 5

    st.progress(step / total, text=f"Step {step} of {total}")
    st.markdown("---")

    if step == 1:
        st.markdown("### What's your main training goal?")
        goal = st.radio("", GOALS, index=0, label_visibility="collapsed")
        if st.button("Next →", use_container_width=True):
            st.session_state.onboard_goal = goal
            st.session_state.onboard_step = 2
            st.rerun()

    elif step == 2:
        st.markdown("### What's your experience level?")
        exp = st.radio("", EXPERIENCE_LEVELS, index=0, label_visibility="collapsed")
        col_back, col_next = st.columns(2)
        if col_back.button("← Back", use_container_width=True):
            st.session_state.onboard_step = 1
            st.rerun()
        if col_next.button("Next →", use_container_width=True):
            st.session_state.onboard_experience = exp
            st.session_state.onboard_step = 3
            st.rerun()

    elif step == 3:
        st.markdown("### How many days per week can you train?")
        days = st.slider("", 2, 6, 3, label_visibility="collapsed")
        # Recommend a split based on days
        if days <= 3:
            rec = "Push / Pull / Legs (3-day)" if days == 3 else "Full Body (3-day)"
        elif days == 4:
            rec = "Upper / Lower (4-day)"
        elif days == 5:
            rec = "Bro Split (5-day)"
        else:
            rec = "Push / Pull / Legs (6-day)"
        st.info(f"Recommended split: **{rec}**")
        split = st.selectbox("Split", list(SPLIT_TEMPLATES.keys()),
                             index=list(SPLIT_TEMPLATES.keys()).index(rec))
        col_back, col_next = st.columns(2)
        if col_back.button("← Back", use_container_width=True):
            st.session_state.onboard_step = 2
            st.rerun()
        if col_next.button("Next →", use_container_width=True):
            st.session_state.onboard_days  = days
            st.session_state.onboard_split = split
            st.session_state.onboard_step  = 4
            st.rerun()

    elif step == 4:
        st.markdown("### What equipment do you have access to?")
        equip = st.radio("", EQUIPMENT_OPTIONS, index=0, label_visibility="collapsed")
        col_back, col_next = st.columns(2)
        if col_back.button("← Back", use_container_width=True):
            st.session_state.onboard_step = 3
            st.rerun()
        if col_next.button("Next →", use_container_width=True):
            st.session_state.onboard_equipment = equip
            st.session_state.onboard_step = 5
            st.rerun()

    elif step == 5:
        st.markdown("### Any areas you want to focus on? *(optional)*")
        focus = st.multiselect("", FOCUS_OPTIONS, label_visibility="collapsed")
        col_back, col_done = st.columns(2)
        if col_back.button("← Back", use_container_width=True):
            st.session_state.onboard_step = 4
            st.rerun()
        if col_done.button("Let's go →", use_container_width=True, type="primary"):
            profile = {
                "goal":          st.session_state.onboard_goal,
                "experience":    st.session_state.onboard_experience,
                "days_per_week": st.session_state.onboard_days,
                "split_type":    st.session_state.onboard_split,
                "equipment":     st.session_state.onboard_equipment,
                "focus_areas":   ", ".join(focus) if focus else None,
                "has_plan":      False,
            }
            # Clean up step state
            for k in ["onboard_step","onboard_goal","onboard_experience",
                      "onboard_days","onboard_split","onboard_equipment"]:
                st.session_state.pop(k, None)
            return profile

    return None

# ─────────────────────────── plan preview / editor ───────────────────

def _render_plan_editor(
    plan_exercises: list[dict],
    split_days: list[str],
    available_exercises: list[str],
    user_id: int,
) -> None:
    """
    Show the plan grouped by day. Each day is a tab.
    User can edit sets/reps/weight and add/remove exercises before saving.
    """
    # Group by plan_day preserving split order
    by_day: dict[str, list[dict]] = {day: [] for day in split_days}
    for ex in plan_exercises:
        day = ex.get("plan_day", split_days[0])
        if day not in by_day:
            day = split_days[0]
        by_day[day].append(ex)

    # Store editable state in session_state
    key = "plan_editor_state"
    if key not in st.session_state or st.session_state.get("plan_editor_reset"):
        st.session_state[key] = {
            day: [dict(ex) for ex in exs]
            for day, exs in by_day.items()
        }
        st.session_state.pop("plan_editor_reset", None)

    state: dict[str, list[dict]] = st.session_state[key]

    tabs = st.tabs(split_days)
    for tab, day in zip(tabs, split_days):
        with tab:
            day_exs = state.get(day, [])

            for i, ex in enumerate(day_exs):
                c_ex, c_s, c_r, c_w, c_u, c_del = st.columns([3, 1, 1, 1.5, 1, 0.5])
                ex["exercise"] = c_ex.selectbox(
                    "Exercise" if i == 0 else "",
                    available_exercises,
                    index=available_exercises.index(ex["exercise"])
                          if ex["exercise"] in available_exercises else 0,
                    key=f"pe_{day}_{i}_ex",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
                ex["sets"] = c_s.number_input(
                    "Sets" if i == 0 else "", min_value=1, step=1, value=ex.get("sets", 3),
                    key=f"pe_{day}_{i}_s",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
                ex["reps"] = c_r.number_input(
                    "Reps" if i == 0 else "", min_value=1, step=1, value=ex.get("reps", 10),
                    key=f"pe_{day}_{i}_r",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
                ex["weight"] = c_w.number_input(
                    "Weight" if i == 0 else "", min_value=0.0, step=2.5,
                    value=float(ex.get("weight") or 0.0), format="%.1f",
                    key=f"pe_{day}_{i}_w",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
                ex["weight_unit"] = c_u.selectbox(
                    "Unit" if i == 0 else "", ["lbs", "kg"],
                    index=0 if (ex.get("weight_unit") or "lbs") == "lbs" else 1,
                    key=f"pe_{day}_{i}_u",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
                c_del.write("" if i == 0 else "")
                if i == 0:
                    c_del.write("")
                if c_del.button("✕", key=f"pe_{day}_{i}_del", help="Remove"):
                    state[day].pop(i)
                    st.rerun()

            # Add exercise to this day
            new_ex = st.selectbox(
                f"Add exercise to {day}",
                ["— select —"] + available_exercises,
                key=f"pe_{day}_add_select",
            )
            if new_ex != "— select —":
                reps_lo, _ = _rep_range(
                    st.session_state.get("plan_profile", {}).get("goal", "General Fitness"),
                    st.session_state.get("plan_profile", {}).get("experience", "Beginner"),
                )
                state[day].append({
                    "plan_day":    day,
                    "sort_order":  len(state[day]),
                    "exercise":    new_ex,
                    "sets":        _sets(
                        st.session_state.get("plan_profile", {}).get("goal", "General Fitness"),
                        st.session_state.get("plan_profile", {}).get("experience", "Beginner"),
                    ),
                    "reps":        reps_lo,
                    "weight":      None,
                    "weight_unit": "lbs",
                })
                st.rerun()

    st.markdown("---")
    col_reset, col_save = st.columns([1, 2])
    if col_reset.button("↺ Reset to AI suggestion", use_container_width=True):
        st.session_state["plan_editor_reset"] = True
        st.rerun()

    if col_save.button("Save plan", type="primary", use_container_width=True):
        all_exercises = []
        for day, exs in state.items():
            for i, ex in enumerate(exs):
                all_exercises.append({
                    "exercise":    ex["exercise"],
                    "sets":        ex["sets"],
                    "reps":        ex["reps"],
                    "weight":      ex["weight"] if ex.get("weight", 0) else None,
                    "weight_unit": ex.get("weight_unit", "lbs"),
                    "plan_day":    day,
                    "sort_order":  i,
                })
        if not all_exercises:
            st.warning("Add at least one exercise before saving.")
            return
        save_plan(user_id, all_exercises)
        st.session_state.pop("plan_editor_state", None)
        st.session_state.pop("plan_profile", None)
        st.success("Plan saved! Head to **Log Workout** to start training.")
        st.rerun()

# ─────────────────────────── manual builder ──────────────────────────

def _manual_builder(split_days: list[str], available_exercises: list[str], user_id: int) -> None:
    """Empty plan editor — user builds from scratch."""
    empty_plan = [
        {"plan_day": day, "sort_order": 0, "exercise": available_exercises[0],
         "sets": 3, "reps": 10, "weight": None, "weight_unit": "lbs"}
        for day in split_days
    ]
    _render_plan_editor(empty_plan, split_days, available_exercises, user_id)

# ─────────────────────────── main page ───────────────────────────────

def create_plan_page(user_id: int) -> None:
    st.subheader("Create your plan")

    profile     = get_profile(user_id)
    active_plan = has_active_plan(user_id)

    # ── If user already has a plan, show it with an option to redo ────
    if active_plan and "recreate_plan" not in st.session_state:
        st.success("You have an active plan.")
        plan_by_day = get_plan_by_day(user_id)
        for day, exercises in plan_by_day.items():
            with st.expander(f"**{day}** — {len(exercises)} exercise(s)"):
                for ex in exercises:
                    w = f" @ {ex.weight:.1f} {ex.weight_unit}" if ex.weight else ""
                    st.write(f"• {ex.exercise} — {ex.sets}×{ex.reps}{w}")
        st.markdown("---")
        if st.button("Create a new plan", type="secondary"):
            st.session_state["recreate_plan"] = True
            st.rerun()
        return

    # ── Step 1: onboarding (if no profile yet or recreating) ──────────
    if not profile or "recreate_plan" in st.session_state:
        st.info("Answer a few quick questions and we'll build your plan.")
        completed = _onboarding_step()
        if completed is None:
            return  # wizard not finished yet
        # Save profile and move to plan generation step
        save_profile(user_id, completed)
        st.session_state["plan_profile"] = completed
        st.session_state.pop("recreate_plan", None)
        st.session_state["plan_method_step"] = True
        st.rerun()

    # ── Step 2: choose AI or manual ───────────────────────────────────
    if "plan_profile" not in st.session_state:
        # Profile exists but we're revisiting — reload it
        p = get_profile(user_id)
        st.session_state["plan_profile"] = {
            "goal":          p.goal,
            "experience":    p.experience,
            "days_per_week": p.days_per_week,
            "split_type":    p.split_type,
            "equipment":     p.equipment,
            "focus_areas":   p.focus_areas,
        }

    prof            = st.session_state["plan_profile"]
    split_days      = SPLIT_TEMPLATES.get(prof.get("split_type", ""), ["Day 1", "Day 2", "Day 3"])
    available_exs   = _exercises_for_equipment(prof.get("equipment", "Full gym"))

    if "plan_exercises" not in st.session_state:
        st.markdown(f"**Split:** {prof.get('split_type')}  ·  **Goal:** {prof.get('goal')}  ·  **Equipment:** {prof.get('equipment')}")
        st.markdown("---")
        st.markdown("### How do you want to build your plan?")
        col_ai, col_manual = st.columns(2)

        with col_ai:
            st.markdown("**🤖 Generate with AI**")
            st.caption("The AI picks exercises, sets, and reps tailored to your goal and experience.")
            if st.button("Generate my plan", type="primary", use_container_width=True):
                with st.spinner("Building your personalised plan..."):
                    try:
                        exercises = generate_ai_plan(prof, available_exs)
                        st.session_state["plan_exercises"] = exercises
                        st.rerun()
                    except Exception as exc:
                        st.error(f"AI generation failed: {exc}")

        with col_manual:
            st.markdown("**✏️ Build manually**")
            st.caption("Choose your own exercises for each day of the split.")
            if st.button("Build manually", use_container_width=True):
                st.session_state["plan_exercises"] = []   # signals manual mode
                st.rerun()
        return

    # ── Step 3: edit & save ───────────────────────────────────────────
    exercises = st.session_state["plan_exercises"]
    st.markdown("### Review and edit your plan")
    st.caption("Adjust exercises, sets, reps, and starting weights before saving.")

    if exercises:
        _render_plan_editor(exercises, split_days, available_exs, user_id)
    else:
        _manual_builder(split_days, available_exs, user_id)
