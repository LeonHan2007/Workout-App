import datetime
from contextlib import contextmanager

import streamlit as st
from passlib.context import CryptContext
from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, create_engine, exists
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
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


engine  = get_engine()
# expire_on_commit=False prevents DetachedInstanceError when ORM objects
# are accessed after their session has been closed.
Session = sessionmaker(bind=engine, expire_on_commit=False)
Base    = declarative_base()

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

    workouts = relationship("Workout", back_populates="user", cascade="all, delete-orphan")


class Workout(Base):
    __tablename__ = "workouts"

    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    exercise     = Column(String, nullable=False)
    sets         = Column(Integer, nullable=False)
    reps         = Column(Integer, nullable=False)
    weight       = Column(Float, nullable=True)
    weight_unit  = Column(String, nullable=True)
    workout_date = Column(Date, default=datetime.date.today)

    user = relationship("User", back_populates="workouts")


Base.metadata.create_all(engine)

# ─────────────────────────── session context manager ─────────────────

@contextmanager
def _session():
    """Yield a session and handle commit/rollback/close automatically."""
    s = Session()
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
    """Create a new user. Returns the User object, or None if username/email is taken."""
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
        return user


def authenticate_user(username: str, password: str) -> User | None:
    """Return the User if credentials are valid, otherwise None."""
    with _session() as s:
        user = s.query(User).filter_by(username=username).first()
        if user and verify_password(password, user.hashed_password):
            return user
        return None

# ─────────────────────────── workout CRUD ────────────────────────────

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