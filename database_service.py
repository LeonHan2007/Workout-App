import datetime
from contextlib import contextmanager
from dataclasses import dataclass

import streamlit as st
from passlib.context import CryptContext
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Boolean,
    ForeignKey, Text, create_engine, exists, func, desc,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from urllib.parse import quote_plus

# ─────────────────────────── connection ──────────────────────────────

def _build_database_url() -> str:
    host     = st.secrets["DB_HOST"]
    port     = int(st.secrets["DB_PORT"])
    name     = st.secrets["DB_NAME"]
    user     = st.secrets["DB_USER"]
    password = quote_plus(st.secrets["DB_PASSWORD"])
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}?sslmode=require"


@st.cache_resource
def get_engine():
    return create_engine(
        _build_database_url(),
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 10},
    )


Base = declarative_base()


def _get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)

# ─────────────────────────── password hashing ────────────────────────

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return _pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)

# ─────────────────────────── models ──────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True)
    username        = Column(String, unique=True, nullable=False)
    email           = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    workouts         = relationship("Workout",        back_populates="user", cascade="all, delete-orphan")
    workout_sessions = relationship("WorkoutSession", back_populates="user", cascade="all, delete-orphan")
    profile          = relationship("UserProfile",    back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserProfile(Base):
    """
    Stores onboarding answers and plan metadata for a user.
    One row per user (upserted on save).
    """
    __tablename__ = "user_profiles"

    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    goal          = Column(String, nullable=True)   # e.g. "Hypertrophy"
    experience    = Column(String, nullable=True)   # "Beginner" | "Intermediate" | "Advanced"
    days_per_week = Column(Integer, nullable=True)
    equipment     = Column(String, nullable=True)   # "Full gym" | "Dumbbells" | "Bodyweight"
    focus_areas   = Column(String, nullable=True)   # comma-separated, e.g. "Chest,Arms"
    split_type    = Column(String, nullable=True)   # "PPL" | "Upper/Lower" | "Full Body"
    has_plan      = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="profile", uselist=False)


class Workout(Base):
    """
    The user's programme template — what they *plan* to do each session.
    One row per exercise (e.g. Bench Press: 4x8 @ 185 lbs).
    plan_day links the exercise to a specific day in the split (e.g. "Push").
    sort_order controls display order within a day.
    NOT a history record; this is the source of truth for the scheduler.
    """
    __tablename__ = "workouts"

    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    exercise     = Column(String, nullable=False)
    sets         = Column(Integer, nullable=False)
    reps         = Column(Integer, nullable=False)
    weight       = Column(Float, nullable=True)
    weight_unit  = Column(String, nullable=True)
    plan_day     = Column(String, nullable=True)   # "Push" | "Pull" | "Legs" | "Day 1" etc.
    sort_order   = Column(Integer, default=0, nullable=False)
    workout_date = Column(Date, default=datetime.date.today)

    user = relationship("User", back_populates="workouts")


class WorkoutSession(Base):
    """
    One row per gym visit. Records the date, which PPL day it was,
    and optional free-text notes.
    """
    __tablename__ = "workout_sessions"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    date       = Column(Date, nullable=False, default=datetime.date.today)
    ppl_day    = Column(String, nullable=True)   # "Push" | "Pull" | "Legs" | None
    notes      = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="workout_sessions")
    logs = relationship("WorkoutLog", back_populates="session", cascade="all, delete-orphan")


class WorkoutLog(Base):
    """
    One row per exercise performed within a WorkoutSession.
    Records what the user *actually* did — sets/reps/weight may differ
    from the Workout template because performance varies day to day.
    """
    __tablename__ = "workout_logs"

    id          = Column(Integer, primary_key=True)
    session_id  = Column(Integer, ForeignKey("workout_sessions.id"), nullable=False)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    exercise    = Column(String, nullable=False)
    sets        = Column(Integer, nullable=False)
    reps        = Column(Integer, nullable=False)
    weight      = Column(Float, nullable=True)
    weight_unit = Column(String, nullable=True)

    session = relationship("WorkoutSession", back_populates="logs")


# ─────────────────────────── DB session context manager ──────────────

def _run_migrations(engine) -> None:
    """
    Idempotent column migrations for tables that already exist in production.
    create_all() never alters existing tables, so new columns must be added here.
    Each ALTER TABLE uses IF NOT EXISTS so it is safe to run on every startup.
    """
    from sqlalchemy import text
    migrations = [
        # workouts — columns added after initial deploy
        "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS plan_day VARCHAR",
        "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0",
        # workout_sessions — columns added after initial deploy
        "ALTER TABLE workout_sessions ADD COLUMN IF NOT EXISTS ppl_day VARCHAR",
        "ALTER TABLE workout_sessions ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE workout_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
    ]
    with engine.begin() as conn:
        for sql in migrations:
            conn.execute(text(sql))


@st.cache_resource
def _ensure_tables():
    """Create new tables and run column migrations, exactly once per process."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _run_migrations(engine)


@contextmanager
def _session():
    """Yield a DB session and handle commit / rollback / close automatically."""
    _ensure_tables()
    s = _get_session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

# ─────────────────────────── user CRUD ───────────────────────────────

def create_user(username: str, email: str, password: str) -> User | None:
    """Create a new user. Returns the User, or None if username/email is taken."""
    with _session() as s:
        already_exists = s.query(
            s.query(User)
            .filter((User.username == username) | (User.email == email))
            .exists()
        ).scalar()
        if already_exists:
            return None
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
        )
        s.add(user)
        s.flush()      # assign user.id before the session closes
        s.refresh(user)
        return user


def authenticate_user(username: str, password: str) -> User | None:
    """Return the User if credentials are valid, otherwise None."""
    with _session() as s:
        user = s.query(User).filter_by(username=username).first()
        if user and verify_password(password, user.hashed_password):
            return user
        return None


def get_user_by_id(user_id: int) -> User | None:
    """Return a User by primary key, or None if not found. Used for cookie re-hydration."""
    with _session() as s:
        return s.query(User).filter_by(id=user_id).first()

# ─────────────────────────── workout template CRUD ───────────────────

def insert_workout(user_id: int, data: dict) -> Workout:
    with _session() as s:
        w = Workout(user_id=user_id, **data)
        s.add(w)
        return w


def get_all_workouts(user_id: int) -> list[Workout]:
    with _session() as s:
        return (
            s.query(Workout)
            .filter_by(user_id=user_id)
            .order_by(Workout.id)
            .all()
        )


def update_workout(user_id: int, workout_id: int, data: dict) -> Workout | None:
    with _session() as s:
        w = s.query(Workout).filter_by(id=workout_id, user_id=user_id).first()
        if not w:
            return None
        for key, val in data.items():
            setattr(w, key, val)
        return w


def delete_workout(user_id: int, workout_id: int) -> bool:
    with _session() as s:
        w = s.query(Workout).filter_by(id=workout_id, user_id=user_id).first()
        if not w:
            return False
        s.delete(w)
        return True


def workout_exists(user_id: int, exercise: str) -> bool:
    with _session() as s:
        return s.query(
            exists().where(
                Workout.user_id == user_id,
                Workout.exercise == exercise,
            )
        ).scalar()

# ─────────────────────────── workout session CRUD ────────────────────

def start_session(
    user_id: int,
    ppl_day: str | None = None,
    notes: str | None = None,
    date: datetime.date | None = None,
) -> WorkoutSession:
    """Create a new workout session and return it."""
    with _session() as s:
        ws = WorkoutSession(
            user_id=user_id,
            date=date or datetime.date.today(),
            ppl_day=ppl_day,
            notes=notes,
        )
        s.add(ws)
        s.flush()      # assign ws.id before the session closes
        s.refresh(ws)
        return ws


def get_sessions(user_id: int, limit: int = 30) -> list[WorkoutSession]:
    """Return the most recent `limit` sessions, newest first."""
    with _session() as s:
        return (
            s.query(WorkoutSession)
            .filter_by(user_id=user_id)
            .order_by(desc(WorkoutSession.date), desc(WorkoutSession.created_at))
            .limit(limit)
            .all()
        )


def get_session_by_id(user_id: int, session_id: int) -> WorkoutSession | None:
    with _session() as s:
        return s.query(WorkoutSession).filter_by(id=session_id, user_id=user_id).first()


def delete_session(user_id: int, session_id: int) -> bool:
    """Delete a session and cascade-delete all its logs."""
    with _session() as s:
        ws = s.query(WorkoutSession).filter_by(id=session_id, user_id=user_id).first()
        if not ws:
            return False
        s.delete(ws)
        return True

# ─────────────────────────── workout log CRUD ────────────────────────

def log_exercise(session_id: int, user_id: int, data: dict) -> WorkoutLog:
    """Append one exercise entry to an existing session."""
    with _session() as s:
        entry = WorkoutLog(session_id=session_id, user_id=user_id, **data)
        s.add(entry)
        return entry


def log_exercises_bulk(session_id: int, user_id: int, entries: list[dict]) -> list[WorkoutLog]:
    """Insert multiple log entries for a session in one transaction."""
    with _session() as s:
        logs = [WorkoutLog(session_id=session_id, user_id=user_id, **d) for d in entries]
        s.add_all(logs)
        return logs


def get_logs_for_session(session_id: int, user_id: int) -> list[WorkoutLog]:
    with _session() as s:
        return (
            s.query(WorkoutLog)
            .filter_by(session_id=session_id, user_id=user_id)
            .order_by(WorkoutLog.id)
            .all()
        )


def update_log(user_id: int, log_id: int, data: dict) -> WorkoutLog | None:
    with _session() as s:
        entry = s.query(WorkoutLog).filter_by(id=log_id, user_id=user_id).first()
        if not entry:
            return None
        for key, val in data.items():
            setattr(entry, key, val)
        return entry


def delete_log(user_id: int, log_id: int) -> bool:
    with _session() as s:
        entry = s.query(WorkoutLog).filter_by(id=log_id, user_id=user_id).first()
        if not entry:
            return False
        s.delete(entry)
        return True


# ─────────────────────────── user profile CRUD ───────────────────────

def get_profile(user_id: int) -> "UserProfile | None":
    with _session() as s:
        return s.query(UserProfile).filter_by(user_id=user_id).first()


def save_profile(user_id: int, data: dict) -> "UserProfile":
    """Upsert the user's profile / onboarding answers."""
    with _session() as s:
        profile = s.query(UserProfile).filter_by(user_id=user_id).first()
        if profile:
            for key, val in data.items():
                setattr(profile, key, val)
        else:
            profile = UserProfile(user_id=user_id, **data)
            s.add(profile)
        return profile


def has_active_plan(user_id: int) -> bool:
    with _session() as s:
        profile = s.query(UserProfile).filter_by(user_id=user_id).first()
        return bool(profile and profile.has_plan)

# ─────────────────────────── plan CRUD ───────────────────────────────

def save_plan(user_id: int, exercises: list[dict]) -> None:
    """
    Replace the user's entire plan with a new set of exercises.
    Each dict must have: exercise, sets, reps, plan_day, sort_order,
    and optionally weight / weight_unit.
    Marks the user's profile has_plan = True.
    """
    with _session() as s:
        # Delete all existing template exercises for this user
        s.query(Workout).filter_by(user_id=user_id).delete()
        # Insert new plan
        for ex in exercises:
            s.add(Workout(user_id=user_id, **ex))
        # Mark profile as having a plan
        profile = s.query(UserProfile).filter_by(user_id=user_id).first()
        if profile:
            profile.has_plan = True
        else:
            s.add(UserProfile(user_id=user_id, has_plan=True))


def get_plan_by_day(user_id: int) -> dict[str, list]:
    """
    Return the user's plan grouped by plan_day, ordered by sort_order.
    Returns an empty dict if no plan exists.
    """
    with _session() as s:
        rows = (
            s.query(Workout)
            .filter_by(user_id=user_id)
            .order_by(Workout.plan_day, Workout.sort_order)
            .all()
        )
        grouped: dict[str, list] = {}
        for w in rows:
            day = w.plan_day or "Unassigned"
            grouped.setdefault(day, []).append(w)
        return grouped


def get_next_plan_day(user_id: int) -> str | None:
    """
    Infer the next PPL day based on the last logged session.
    Returns a plan_day label, or None if no plan exists.
    """
    with _session() as s:
        # Get all unique plan days in sort order
        days_rows = (
            s.query(Workout.plan_day)
            .filter(Workout.user_id == user_id, Workout.plan_day.isnot(None))
            .distinct()
            .order_by(Workout.plan_day)
            .all()
        )
        plan_days = [r[0] for r in days_rows]
        if not plan_days:
            return None

        # Find the last logged session with a ppl_day
        last = (
            s.query(WorkoutSession.ppl_day)
            .filter(
                WorkoutSession.user_id == user_id,
                WorkoutSession.ppl_day.isnot(None),
            )
            .order_by(desc(WorkoutSession.date), desc(WorkoutSession.created_at))
            .first()
        )
        if not last or last[0] not in plan_days:
            return plan_days[0]

        idx = plan_days.index(last[0])
        return plan_days[(idx + 1) % len(plan_days)]

# ─────────────────────────── analytics ───────────────────────────────

@dataclass
class ExercisePR:
    exercise:    str
    weight:      float
    weight_unit: str
    reps:        int
    date:        datetime.date


@dataclass
class VolumePoint:
    date:   datetime.date
    volume: float        # sets × reps × weight for that day


@dataclass
class DashboardStats:
    total_sessions:     int
    sessions_this_week: int
    current_streak:     int        # consecutive calendar days with a session
    total_exercises:    int        # distinct exercises ever logged
    favourite_day:      str | None # most frequently logged ppl_day


def get_personal_records(user_id: int) -> list[ExercisePR]:
    """
    Return the heaviest logged weight per exercise.
    When two logs tie on weight, the most recent one wins.
    Only includes logs where weight is not null.
    """
    with _session() as s:
        # Max weight per exercise
        subq = (
            s.query(
                WorkoutLog.exercise,
                func.max(WorkoutLog.weight).label("max_weight"),
            )
            .filter(WorkoutLog.user_id == user_id, WorkoutLog.weight.isnot(None))
            .group_by(WorkoutLog.exercise)
            .subquery()
        )

        rows = (
            s.query(WorkoutLog, WorkoutSession.date)
            .join(subq, (WorkoutLog.exercise == subq.c.exercise) &
                        (WorkoutLog.weight   == subq.c.max_weight))
            .join(WorkoutSession, WorkoutLog.session_id == WorkoutSession.id)
            .filter(WorkoutLog.user_id == user_id)
            .order_by(WorkoutLog.exercise, desc(WorkoutSession.date))
            .all()
        )

        # De-duplicate (take first/most-recent per exercise)
        seen: set[str] = set()
        prs: list[ExercisePR] = []
        for log, date in rows:
            if log.exercise not in seen:
                seen.add(log.exercise)
                prs.append(ExercisePR(
                    exercise=log.exercise,
                    weight=log.weight,
                    weight_unit=log.weight_unit or "lbs",
                    reps=log.reps,
                    date=date,
                ))
        return prs


def get_volume_over_time(user_id: int, exercise: str, days: int = 90) -> list[VolumePoint]:
    """
    Daily total volume (sets × reps × weight) for one exercise over the
    last `days` days. Rows with null weight are excluded.
    """
    since = datetime.date.today() - datetime.timedelta(days=days)
    with _session() as s:
        rows = (
            s.query(
                WorkoutSession.date,
                func.sum(WorkoutLog.sets * WorkoutLog.reps * WorkoutLog.weight).label("volume"),
            )
            .join(WorkoutLog, WorkoutSession.id == WorkoutLog.session_id)
            .filter(
                WorkoutLog.user_id  == user_id,
                WorkoutLog.exercise == exercise,
                WorkoutLog.weight.isnot(None),
                WorkoutSession.date >= since,
            )
            .group_by(WorkoutSession.date)
            .order_by(WorkoutSession.date)
            .all()
        )
        return [VolumePoint(date=r.date, volume=float(r.volume)) for r in rows]


def get_dashboard_stats(user_id: int) -> DashboardStats:
    """Compute all stats needed for the home dashboard in one call."""
    today      = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())  # Monday

    with _session() as s:
        total_sessions = (
            s.query(func.count(WorkoutSession.id))
            .filter_by(user_id=user_id)
            .scalar() or 0
        )

        sessions_this_week = (
            s.query(func.count(WorkoutSession.id))
            .filter(
                WorkoutSession.user_id == user_id,
                WorkoutSession.date   >= week_start,
            )
            .scalar() or 0
        )

        # All distinct session dates, newest first — for streak calculation
        all_dates: list[datetime.date] = [
            row[0] for row in (
                s.query(WorkoutSession.date)
                .filter_by(user_id=user_id)
                .distinct()
                .order_by(desc(WorkoutSession.date))
                .all()
            )
        ]
        current_streak = _calculate_streak(all_dates, today)

        total_exercises = (
            s.query(func.count(WorkoutLog.exercise.distinct()))
            .filter(WorkoutLog.user_id == user_id)
            .scalar() or 0
        )

        fav_row = (
            s.query(
                WorkoutSession.ppl_day,
                func.count(WorkoutSession.ppl_day).label("n"),
            )
            .filter(
                WorkoutSession.user_id  == user_id,
                WorkoutSession.ppl_day.isnot(None),
            )
            .group_by(WorkoutSession.ppl_day)
            .order_by(desc("n"))
            .first()
        )
        favourite_day = fav_row[0] if fav_row else None

        return DashboardStats(
            total_sessions=total_sessions,
            sessions_this_week=sessions_this_week,
            current_streak=current_streak,
            total_exercises=total_exercises,
            favourite_day=favourite_day,
        )


def get_recent_sessions_with_logs(
    user_id: int,
    limit: int = 5,
) -> list[tuple[WorkoutSession, list[WorkoutLog]]]:
    """Return the last `limit` sessions, each paired with its log entries."""
    with _session() as s:
        sessions = (
            s.query(WorkoutSession)
            .filter_by(user_id=user_id)
            .order_by(desc(WorkoutSession.date), desc(WorkoutSession.created_at))
            .limit(limit)
            .all()
        )
        return [
            (
                sess,
                s.query(WorkoutLog)
                 .filter_by(session_id=sess.id, user_id=user_id)
                 .order_by(WorkoutLog.id)
                 .all(),
            )
            for sess in sessions
        ]

# ─────────────────────────── streak helper ───────────────────────────

def _calculate_streak(dates: list[datetime.date], today: datetime.date) -> int:
    """
    Given distinct session dates sorted newest-first, return the current
    consecutive-day streak. The streak counts if the user worked out today
    OR yesterday (so logging later in the day doesn't break it).
    A gap of more than one calendar day resets it to zero.
    """
    if not dates:
        return 0

    # Anchor: streak must end on today or yesterday
    if dates[0] == today:
        anchor = today
    elif dates[0] == today - datetime.timedelta(days=1):
        anchor = today - datetime.timedelta(days=1)
    else:
        return 0

    streak = 1
    for i in range(1, len(dates)):
        if dates[i] == anchor - datetime.timedelta(days=i):
            streak += 1
        else:
            break
    return streak