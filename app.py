import streamlit as st
from database_service import insert_workout, get_all_workouts, update_workout, delete_workout, workout_exists

st.title("Workout Tracker")

if "refresh" not in st.session_state:
    st.session_state["refresh"] = False
if "edit_id" not in st.session_state:
    st.session_state.edit_id = None



# Sidebar menu
menu = ["View Workouts", "Add New Workout"]
choice = st.sidebar.selectbox("Menu", menu)

# ---------------- Add Workout ----------------
if choice == "Add New Workout":
    st.subheader("Add a new workout")
    exercise = st.text_input("Exercise name")
    col_sets, col_reps = st.columns([1,1])
    sets = col_sets.number_input("Sets", min_value=1, step=1)
    reps = col_reps.number_input("Reps", min_value=1, step=1)

    # Weight input + unit side by side
    col_weight, col_unit = st.columns([6, 1])
    weight = col_weight.number_input("Weight", min_value=0.0, step=0.5, format="%.1f")
    unit = col_unit.selectbox("", ["lbs", "kg"], index=0)

    if st.button("Add Workout"):
        if not exercise.strip():
            st.warning("Please enter an exercise name.")
        else:
            # Use workout_exists() from your database_service
            if workout_exists(exercise.strip()):
                st.error(f"Exercise '{exercise}' already exists.")
            else:
                insert_workout({
                    "exercise": exercise.strip(),
                    "sets": sets,
                    "reps": reps,
                    "weight": weight if weight > 0 else None,
                    "weight_unit": unit if weight > 0 else None
                })
                st.success(f"Exercise '{exercise}' added!")

# ---------------- View Workouts ----------------
elif choice == "View Workouts":
    st.subheader("All Workouts")
    workouts = get_all_workouts()
    if workouts:
        # Table headers
        col_ex, col_sets, col_reps, col_weight, col_update, col_delete = st.columns([3,1,1,2,1.5,1.5])
        col_ex.markdown("**Exercise**")
        col_sets.markdown("**Sets**")
        col_reps.markdown("**Reps**")
        col_weight.markdown("**Weight**")

        for w in workouts:
            # Display workout row
            col_ex, col_sets, col_reps, col_weight, col_update, col_delete = st.columns([3,1,1,2,1.5,1.5])
            col_ex.write(w.exercise)
            col_sets.write(str(w.sets))
            col_reps.write(str(w.reps))
            col_weight.write(f"{w.weight:.1f} {w.weight_unit}" if w.weight else "Bodyweight")

            # Update button
            if col_update.button("Update", key=f"edit_{w.id}"):
                st.session_state.edit_id = w.id

            # Delete button
            if col_delete.button("Delete", key=f"delete_{w.id}"):
                delete_workout(w.id)
                st.rerun()

            # Inline edit form for this row
            if st.session_state.edit_id == w.id:
                st.markdown("---")  # optional separator

                # Exercise name
                exercise = st.text_input("Exercise", value=w.exercise, key=f"exercise_{w.id}")

                # Sets | Reps | Weight | Unit in one row
                col_sets, col_reps, col_weight, col_unit, col_submit = st.columns([1,1,2,1,1])
                sets = col_sets.number_input("Sets", min_value=1, step=1, value=w.sets, key=f"sets_{w.id}")
                reps = col_reps.number_input("Reps", min_value=1, step=1, value=w.reps, key=f"reps_{w.id}")
                weight = col_weight.number_input("Weight", min_value=0.0, step=0.5, format="%.1f",
                                                value=w.weight if w.weight else 0.0, key=f"weight_{w.id}")
                unit = col_unit.selectbox("", ["lbs", "kg"], index=0 if w.weight_unit=="lbs" else 1, key=f"unit_{w.id}")

                col_submit.write("")        
                col_submit.write("")

                if col_submit.button("Submit", key=f"submit_{w.id}"):
                    update_workout(w.id, {
                        "exercise": exercise,
                        "sets": sets,
                        "reps": reps,
                        "weight": weight if weight > 0 else None,
                        "weight_unit": unit if weight > 0 else None
                    })
                    st.session_state.edit_id = None
                    st.rerun()

    else:
        st.info("No workouts logged yet.")