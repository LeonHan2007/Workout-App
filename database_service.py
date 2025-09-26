import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext
from dotenv import load_dotenv

# ---------------- Load environment ----------------
load_dotenv()
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ---------------- SQLAlchemy setup ----------------
engine = create_engine(DATABASE_URL, echo=True)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

# ---------------- Password hashing ----------------
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# ---------------- Models ----------------
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

# ---------------- CRUD ----------------
def create_user(username: str, email: str, password: str):
    if existing_user(username, email):
        return None
    user = User(username=username, email=email, hashed_password=hash_password(password))
    session.add(user)
    session.commit()
    return user

def existing_user(username: str, email: str) -> bool:
    return session.query(User).filter((User.username == username) | (User.email == email)).first() is not None

def authenticate_user(username: str, password: str):
    user = session.query(User).filter_by(username=username).first()
    if user and verify_password(password, user.hashed_password):
        return user
    return None

def insert_workout(user_id: int, data: dict):
    w = Workout(user_id=user_id, **data)
    session.add(w)
    session.commit()
    return w

def get_all_workouts(user_id: int):
    return session.query(Workout).filter_by(user_id=user_id).order_by(Workout.id).all()

def update_workout(user_id: int, workout_id: int, data: dict):
    w = session.query(Workout).filter_by(id=workout_id, user_id=user_id).first()
    if not w:
        return None
    for key, val in data.items():
        setattr(w, key, val)
    session.commit()
    return w

def delete_workout(user_id: int, workout_id: int):
    w = session.query(Workout).filter_by(id=workout_id, user_id=user_id).first()
    if w:
        session.delete(w)
        session.commit()
        return True
    return False

def workout_exists(user_id: int, exercise: str) -> bool:
    query = session.query(Workout).filter_by(user_id=user_id, exercise=exercise)
    return session.query(query.exists()).scalar()

# ---------------- Utility ----------------
def reset_users_table():
    """Drops and recreates all tables"""
    Base.metadata.drop_all(engine)  # drops all tables
    Base.metadata.create_all(engine)  # recreates all tables
