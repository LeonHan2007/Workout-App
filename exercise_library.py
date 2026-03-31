# exercise_library.py
# Single source of truth for all exercises and their PPL category.
# Used by the "Add Workout" UI (searchable dropdown) and the scheduler
# (deterministic classification — no keyword guessing needed).

from dataclasses import dataclass


@dataclass(frozen=True)
class Exercise:
    name: str
    category: str   # "push" | "pull" | "legs" | "core"


# fmt: off
EXERCISES: list[Exercise] = [
    # ── PUSH ──────────────────────────────────────────────────────────
    # Chest — barbell
    Exercise("Barbell Bench Press",             "push"),
    Exercise("Barbell Incline Bench Press",      "push"),
    Exercise("Barbell Decline Bench Press",      "push"),
    Exercise("Close-Grip Bench Press",           "push"),
    Exercise("Floor Press",                      "push"),
    # Chest — dumbbell
    Exercise("Dumbbell Bench Press",             "push"),
    Exercise("Dumbbell Incline Press",           "push"),
    Exercise("Dumbbell Decline Press",           "push"),
    Exercise("Dumbbell Fly",                     "push"),
    Exercise("Dumbbell Incline Fly",             "push"),
    Exercise("Dumbbell Pullover",                "push"),
    # Chest — machine / cable
    Exercise("Cable Fly",                        "push"),
    Exercise("Cable Crossover",                  "push"),
    Exercise("Low Cable Fly",                    "push"),
    Exercise("High Cable Fly",                   "push"),
    Exercise("Machine Chest Press",              "push"),
    Exercise("Pec Deck",                         "push"),
    Exercise("Smith Machine Bench Press",        "push"),
    # Chest — bodyweight
    Exercise("Push-Up",                          "push"),
    Exercise("Wide-Grip Push-Up",                "push"),
    Exercise("Diamond Push-Up",                  "push"),
    Exercise("Decline Push-Up",                  "push"),
    Exercise("Incline Push-Up",                  "push"),
    Exercise("Dip",                              "push"),
    # Shoulders — barbell
    Exercise("Overhead Press (Barbell)",         "push"),
    Exercise("Seated Overhead Press",            "push"),
    Exercise("Push Press",                       "push"),
    Exercise("Z-Press",                          "push"),
    # Shoulders — dumbbell
    Exercise("Dumbbell Shoulder Press",          "push"),
    Exercise("Arnold Press",                     "push"),
    Exercise("Dumbbell Lateral Raise",           "push"),
    Exercise("Dumbbell Front Raise",             "push"),
    Exercise("Dumbbell Rear Lateral Raise",      "push"),
    # Shoulders — cable / machine
    Exercise("Cable Lateral Raise",              "push"),
    Exercise("Cable Front Raise",                "push"),
    Exercise("Machine Shoulder Press",           "push"),
    Exercise("Machine Lateral Raise",            "push"),
    # Triceps — barbell / EZ-bar
    Exercise("Skull Crusher (Barbell)",          "push"),
    Exercise("Skull Crusher (EZ-Bar)",           "push"),
    Exercise("Overhead Tricep Extension (Bar)",  "push"),
    # Triceps — dumbbell
    Exercise("Dumbbell Tricep Kickback",         "push"),
    Exercise("Overhead Tricep Extension (DB)",   "push"),
    # Triceps — cable / machine
    Exercise("Tricep Pushdown (Rope)",           "push"),
    Exercise("Tricep Pushdown (Bar)",            "push"),
    Exercise("Overhead Cable Tricep Extension",  "push"),
    Exercise("Machine Tricep Extension",         "push"),

    # ── PULL ──────────────────────────────────────────────────────────
    # Back — barbell
    Exercise("Deadlift",                         "pull"),
    Exercise("Conventional Deadlift",            "pull"),
    Exercise("Sumo Deadlift",                    "pull"),
    Exercise("Romanian Deadlift",                "pull"),
    Exercise("Barbell Row",                      "pull"),
    Exercise("Pendlay Row",                      "pull"),
    Exercise("Rack Pull",                        "pull"),
    Exercise("T-Bar Row",                        "pull"),
    # Back — dumbbell
    Exercise("Dumbbell Row",                     "pull"),
    Exercise("Chest-Supported Row (DB)",         "pull"),
    # Back — cable / machine
    Exercise("Seated Cable Row",                 "pull"),
    Exercise("Wide-Grip Cable Row",              "pull"),
    Exercise("Lat Pulldown",                     "pull"),
    Exercise("Wide-Grip Lat Pulldown",           "pull"),
    Exercise("Close-Grip Lat Pulldown",          "pull"),
    Exercise("Single-Arm Lat Pulldown",          "pull"),
    Exercise("Machine Row",                      "pull"),
    Exercise("Chest-Supported Row (Machine)",    "pull"),
    Exercise("Face Pull",                        "pull"),
    # Back — bodyweight
    Exercise("Pull-Up",                          "pull"),
    Exercise("Wide-Grip Pull-Up",                "pull"),
    Exercise("Chin-Up",                          "pull"),
    Exercise("Neutral-Grip Pull-Up",             "pull"),
    Exercise("Inverted Row",                     "pull"),
    # Rear delt
    Exercise("Dumbbell Rear Delt Fly",           "pull"),
    Exercise("Cable Rear Delt Fly",              "pull"),
    Exercise("Reverse Pec Deck",                 "pull"),
    # Traps
    Exercise("Barbell Shrug",                    "pull"),
    Exercise("Dumbbell Shrug",                   "pull"),
    Exercise("Cable Shrug",                      "pull"),
    # Biceps — barbell / EZ-bar
    Exercise("Barbell Curl",                     "pull"),
    Exercise("EZ-Bar Curl",                      "pull"),
    Exercise("Preacher Curl (Barbell)",          "pull"),
    Exercise("Preacher Curl (EZ-Bar)",           "pull"),
    Exercise("21s",                              "pull"),
    # Biceps — dumbbell
    Exercise("Dumbbell Curl",                    "pull"),
    Exercise("Hammer Curl",                      "pull"),
    Exercise("Incline Dumbbell Curl",            "pull"),
    Exercise("Concentration Curl",               "pull"),
    Exercise("Zottman Curl",                     "pull"),
    # Biceps — cable / machine
    Exercise("Cable Curl",                       "pull"),
    Exercise("Cable Hammer Curl",                "pull"),
    Exercise("Machine Curl",                     "pull"),

    # ── LEGS ──────────────────────────────────────────────────────────
    # Quads — barbell
    Exercise("Barbell Back Squat",               "legs"),
    Exercise("Barbell Front Squat",              "legs"),
    Exercise("Barbell Hack Squat",               "legs"),
    Exercise("Barbell Lunge",                    "legs"),
    Exercise("Barbell Step-Up",                  "legs"),
    Exercise("Barbell Bulgarian Split Squat",    "legs"),
    Exercise("Barbell Box Squat",                "legs"),
    Exercise("Zercher Squat",                    "legs"),
    Exercise("Pause Squat",                      "legs"),
    # Quads — machine
    Exercise("Leg Press",                        "legs"),
    Exercise("Hack Squat (Machine)",             "legs"),
    Exercise("Leg Extension",                    "legs"),
    Exercise("Smith Machine Squat",              "legs"),
    # Quads — dumbbell / bodyweight
    Exercise("Dumbbell Lunge",                   "legs"),
    Exercise("Dumbbell Step-Up",                 "legs"),
    Exercise("Dumbbell Bulgarian Split Squat",   "legs"),
    Exercise("Goblet Squat",                     "legs"),
    Exercise("Bodyweight Squat",                 "legs"),
    Exercise("Jump Squat",                       "legs"),
    Exercise("Wall Sit",                         "legs"),
    Exercise("Pistol Squat",                     "legs"),
    # Hamstrings / glutes
    Exercise("Romanian Deadlift (DB)",           "legs"),
    Exercise("Leg Curl (Lying)",                 "legs"),
    Exercise("Leg Curl (Seated)",                "legs"),
    Exercise("Nordic Hamstring Curl",            "legs"),
    Exercise("Good Morning",                     "legs"),
    Exercise("Hip Thrust (Barbell)",             "legs"),
    Exercise("Hip Thrust (Machine)",             "legs"),
    Exercise("Glute Bridge",                     "legs"),
    Exercise("Cable Kickback",                   "legs"),
    Exercise("Cable Pull-Through",               "legs"),
    Exercise("Sumo Squat",                       "legs"),
    Exercise("Single-Leg Romanian Deadlift",     "legs"),
    # Calves
    Exercise("Standing Calf Raise",              "legs"),
    Exercise("Seated Calf Raise",                "legs"),
    Exercise("Leg Press Calf Raise",             "legs"),
    Exercise("Single-Leg Calf Raise",            "legs"),
    Exercise("Donkey Calf Raise",                "legs"),

    # ── CORE ──────────────────────────────────────────────────────────
    Exercise("Plank",                            "core"),
    Exercise("Side Plank",                       "core"),
    Exercise("Ab Wheel Rollout",                 "core"),
    Exercise("Cable Crunch",                     "core"),
    Exercise("Hanging Leg Raise",                "core"),
    Exercise("Hanging Knee Raise",               "core"),
    Exercise("Decline Sit-Up",                   "core"),
    Exercise("Crunch",                           "core"),
    Exercise("Bicycle Crunch",                   "core"),
    Exercise("Russian Twist",                    "core"),
    Exercise("Dead Bug",                         "core"),
    Exercise("Hollow Body Hold",                 "core"),
    Exercise("Pallof Press",                     "core"),
    Exercise("Landmine Twist",                   "core"),
    Exercise("Dragon Flag",                      "core"),
    Exercise("Toes-to-Bar",                      "core"),
    Exercise("L-Sit",                            "core"),
]
# fmt: on

# ── Lookup helpers ────────────────────────────────────────────────────

# Sorted name list for the UI dropdown
EXERCISE_NAMES: list[str] = sorted(e.name for e in EXERCISES)

# name → category dict for O(1) classification
_CATEGORY_MAP: dict[str, str] = {e.name: e.category for e in EXERCISES}

# Grouped by category for display / split building
EXERCISES_BY_CATEGORY: dict[str, list[Exercise]] = {}
for _ex in EXERCISES:
    EXERCISES_BY_CATEGORY.setdefault(_ex.category, []).append(_ex)


def get_category(exercise_name: str) -> str:
    """
    Return the PPL category for a known exercise name.
    Falls back to '' for custom/user-typed names not in the library.
    """
    return _CATEGORY_MAP.get(exercise_name, "")
