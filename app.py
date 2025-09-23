import random
import streamlit as st
from yt_extractor import get_video_info
import database_service as dbs


@st.cache_data()
def get_workouts():
    return dbs.get_all_workouts() 

def get_duration_text(duration):
    minutes, seconds = divmod(duration, 60)
    return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

def fetch_video_info():
    video_url = st.session_state.video_url_input
    if video_url:
        video_info = get_video_info(video_url)
        if video_info is None:
            st.session_state.video_info_preview = None
            st.error("Could not retrieve video info")
        else:
            st.session_state.video_info_preview = video_info
st.title("Workout App")

menu_options = ["Today's Workout", "All Workouts", "Add Workout"]
selection = st.sidebar.selectbox("Menu", menu_options)

if selection == "Today's Workout":
    st.header("Today's Workout")
    workout_today = get_workouts()
    if not workout_today:   
        st.text("No workouts available. Please add some workouts.")
    else:
        wo = dbs.get_workout_today()
        if not wo:
            workouts = get_workouts()
            n = len(workouts)
            idx = random.randint(0, n - 1)
            workout = workouts[idx]
            dbs.update_workout_today(workout, insert=True)
        else:
            workout = wo[0] 
            st.text(workout['title'])
            st.text(f"{workout['channel']} - {get_duration_text(workout['duration'])}")
            url = f"https://www.youtube.com/watch?v={workout['video_id']}"
            st.video(url)
elif selection == "All Workouts":
    st.header("All Workouts")
    workouts = get_workouts()
    for workout in workouts:
        url = f"https://www.youtube.com/watch?v={workout['video_id']}"
        st.text(workout['title'])
        st.text(f"{workout['channel']} - {get_duration_text(workout['duration'])}")
        st.video(url)
        if st.button("Delete Workout", key=f"delete_{workout['video_id']}"):
            dbs.delete_workout(workout['video_id'])
            st.cache_data.clear()
            st.experimental_rerun()
else:
    st.header("Add Workout")
    if "video_info_preview" not in st.session_state:
        st.session_state.video_info_preview = None
    video_url = st.text_input(
        "Enter YouTube Video URL",
        key="video_url_input",
        on_change=fetch_video_info
    )
    if st.session_state.video_info_preview:
        preview = st.session_state.video_info_preview
        st.text(preview['title'])
        st.text(f"{preview['channel']} - {get_duration_text(preview['duration'])}")
        st.video(f"https://www.youtube.com/watch?v={preview['video_id']}")
        if st.button("Add Workout to Database"):
            if not dbs.workout_exists(preview['video_id']):
                dbs.insert_workout(preview)
                st.cache_data.clear()
                st.success("Workout added successfully!")
                st.experimental_rerun()  
            else:
                st.warning("This workout already exists in the database!")   


