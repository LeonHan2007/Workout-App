import streamlit as st
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext

DB_HOST = st.secrets["DB_HOST"]
DB_PORT = st.secrets["DB_PORT"]
DB_NAME = st.secrets["DB_NAME"]
DB_USER = st.secrets["DB_USER"]
DB_PASSWORD = st.secrets["DB_PASSWORD"]

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL, echo=True)

engine = get_engine()
Session = sessionmaker(bind=engine)
Base = declarative_base()


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    workouts = relationship("Workout", back_populates="user", cascade="all, delete-orphan")

class Workout(Base):
    __tablename__ = "workouts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exercise = Column(String, nullable=False)
    sets = Column(Integer, nullable=False)
    reps = Column(Integer, nullable=False)
    weight = Column(Float, nullable=True)
    weight_unit = Column(String, nullable=True)
    workout_date = Column(Date, default=datetime.date.today)

    user = relationship("User", back_populates="workouts")

# CRUD
def create_user(username: str, email: str, password: str):
    session = Session()
    try:
        if session.query(User).filter((User.username == username) | (User.email == email)).first():
            return None
        user = User(username=username, email=email, hashed_password=hash_password(password))
        session.add(user)
        session.commit()
        return user
    finally:
        session.close()

def existing_user(username: str, email: str) -> bool:
    session = Session()
    try:
        return session.query(User).filter((User.username == username) | (User.email == email)).first() is not None
    finally:
        session.close()

def authenticate_user(username: str, password: str):
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if user and verify_password(password, user.hashed_password):
            return user
    finally:
        session.close()
    return None

def insert_workout(user_id: int, data: dict):
    session = Session()
    try:
        w = Workout(user_id=user_id, **data)
        session.add(w)
        session.commit()
        return w
    finally:
        session.close()

def get_all_workouts(user_id: int):
    session = Session()
    try:
        return session.query(Workout).filter_by(user_id=user_id).order_by(Workout.id).all()
    finally:
        session.close()

def update_workout(user_id: int, workout_id: int, data: dict):
    session = Session()
    try:
        w = session.query(Workout).filter_by(id=workout_id, user_id=user_id).first()
        if not w:
            return None
        for key, val in data.items():
            setattr(w, key, val)
        session.commit()
        return w
    finally:
        session.close()

def delete_workout(user_id: int, workout_id: int):
    session = Session()
    try:
        w = session.query(Workout).filter_by(id=workout_id, user_id=user_id).first()
        if w:
            session.delete(w)
            session.commit()
            return True
        return False
    finally:
        session.close()

def workout_exists(user_id: int, exercise: str) -> bool:
    session = Session()
    try:
        query = session.query(Workout).filter_by(user_id=user_id, exercise=exercise)
        return session.query(query.exists()).scalar()
    finally:
        session.close()

