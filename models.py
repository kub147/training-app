from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    strava_id = db.Column(db.BigInteger, unique=True)
    activity_type = db.Column(db.String(50))
    start_time = db.Column(db.DateTime)
    duration = db.Column(db.Integer)
    distance = db.Column(db.Float)
    avg_hr = db.Column(db.Integer)
    notes = db.Column(db.Text)
    exercises = db.relationship('Exercise', backref='activity', cascade='all, delete-orphan')

class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'))
    name = db.Column(db.String(100))
    sets = db.Column(db.Integer)
    reps = db.Column(db.Integer)
    weight = db.Column(db.Float)

class UserData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    strava_access_token = db.Column(db.String(200))
    strava_refresh_token = db.Column(db.String(200))
    strava_expires_at = db.Column(db.Integer)
    goal = db.Column(db.String(500))
    target_date = db.Column(db.Date)

class WorkoutPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    exercises = db.relationship('PlanExercise', backref='plan', cascade='all, delete-orphan')

class PlanExercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('workout_plan.id'))
    name = db.Column(db.String(100))
    default_sets = db.Column(db.Integer)
    default_reps = db.Column(db.Integer)

# --- NOWOŚĆ: Tabela do Historii Czatu ---
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(10)) # 'user' lub 'ai'
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)