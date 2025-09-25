from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
from passlib.context import CryptContext

engine = create_engine("sqlite:///workouts.db")  
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

#Tables

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    workouts = relationship("Workout", back_populates="user")

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

Base.metadata.create_all(engine)

#CRUD

def create_user(username, email, password):
    if existing_user(username, email):
        # Username already exists
        return None
    hashed = hash_password(password)
    user = User(username=username, email=email, hashed_password=hashed)
    session.add(user)
    session.commit()
    return user

def existing_user(username, email):
    return session.query(User).filter(
        (User.username == username) | (User.email == email)).first() is not None

def authenticate_user(username, password):
    user = session.query(User).filter_by(username=username).first()
    if user and verify_password(password, user.hashed_password):
        return user
    return None

def insert_workout(user_id, data):
    w = Workout(user_id=user_id, **data)
    session.add(w)
    session.commit()
    return w

def get_all_workouts(user_id):
    return session.query(Workout).filter_by(user_id=user_id).order_by(Workout.id).all()     

def update_workout(user_id, workout_id, data):
    w = session.query(Workout).filter_by(id=workout_id, user_id=user_id).first()
    for key, val in data.items():
        setattr(w, key, val)
    session.commit()
    return w
    
def delete_workout(user_id, workout_id):
    w = session.query(Workout).filter_by(id=workout_id, user_id=user_id).first()
    if w:
        session.delete(w)
        session.commit()

def workout_exists(user_id, exercise):
    query = session.query(Workout).filter_by(
        user_id=user_id,
        exercise=exercise,
    )
    return session.query(query.exists()).scalar()
