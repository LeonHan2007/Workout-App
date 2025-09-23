import harperdb

url = "https://cloud-1-leonhan.harperdbcloud.com"
username = "leon"
password = "5u55yb4k4"
db = harperdb.HarperDB(url=url, username=username, password=password)

SCHEMA = "workout_repo"
TABLE = "workouts"
TABLE_TODAY = "workout_today"

def insert_workout(workout_data):
    res = db.insert(SCHEMA, TABLE, [workout_data])
    return res

def delete_workout(video_id):
    res = db.delete(SCHEMA, TABLE, [video_id])
    return res

def get_all_workouts():
    res = db.sql(f"SELECT video_id, channel, title, duration FROM {SCHEMA}.{TABLE}")
    return res

def get_workout_today():
    res = db.sql(f"SELECT * FROM {SCHEMA}.{TABLE_TODAY} LIMIT 1")
    return res

def update_workout_today(workout_today, insert=True):
    existing = get_workout_today() 
    if existing:
        workout_today['video_id'] = existing[0]['video_id']
        res = db.update(SCHEMA, TABLE_TODAY, [workout_today])
    else:
        res = db.insert(SCHEMA, TABLE_TODAY, [workout_today])
    
    return res

def workout_exists(video_id):
    res = db.sql(f"SELECT video_id FROM {SCHEMA}.{TABLE} WHERE video_id = '{video_id}'")
    return len(res) > 0

