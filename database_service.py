from sqlalchemy import create_engine, Column, Integer, String, Float, Date, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

engine = create_engine("sqlite:///workouts.db")  # change to your DB
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

class Workout(Base):
    __tablename__ = "workouts"
    id = Column(Integer, primary_key=True)
    exercise = Column(String, nullable=False)
    sets = Column(Integer, nullable=False)
    reps = Column(Integer, nullable=False)
    weight = Column(Float, nullable=True)          
    weight_unit = Column(String, nullable=True)    
    workout_date = Column(Date, default=datetime.date.today)

Base.metadata.create_all(engine)

# CRUD functions
def insert_workout(data):
    w = Workout(**data)
    session.add(w)
    session.commit()
    return w

def get_all_workouts():
    return session.query(Workout).order_by(Workout.id).all()

def update_workout(workout_id, data):
    w = session.query(Workout).filter_by(id=workout_id).first()
    for key, val in data.items():
        setattr(w, key, val)
    session.commit()
    return w

def delete_workout(workout_id):
    w = session.query(Workout).filter_by(id=workout_id).first()
    if w:
        session.delete(w)
        session.commit()

def workout_exists(exercise):
    query = session.query(Workout).filter_by(
        exercise=exercise,
    )
    return session.query(query.exists()).scalar()
