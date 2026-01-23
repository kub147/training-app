from __future__ import annotations

from datetime import date, datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    onboarding_completed = db.Column(db.Boolean, default=False, nullable=False)

    profile = db.relationship("UserProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    state_entries = db.relationship("UserState", backref="user", cascade="all, delete-orphan")
    activities = db.relationship("Activity", backref="user", cascade="all, delete-orphan")
    workout_plans = db.relationship("WorkoutPlan", backref="user", cascade="all, delete-orphan")
    chat_messages = db.relationship("ChatMessage", backref="user", cascade="all, delete-orphan")
    generated_plans = db.relationship("GeneratedPlan", backref="user", cascade="all, delete-orphan")
    checkins = db.relationship("TrainingCheckin", backref="user", cascade="all, delete-orphan")


class UserProfile(db.Model):
    """Facts + goals. Things that are usually stable or explicitly edited by the user."""

    __tablename__ = "user_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False, index=True)

    # Open-ish answers (the UI can still use numeric inputs, but the model stores them as plain fields)
    primary_sports = db.Column(db.String(200))        # e.g. "run, gym"
    weekly_time_hours = db.Column(db.Float)           # time available per week
    weekly_distance_km = db.Column(db.Float)          # declared distance per week
    days_per_week = db.Column(db.Integer)             # training days per week
    experience_text = db.Column(db.Text)              # free-form: experience background

    goals_text = db.Column(db.Text)                   # free-form main goal
    target_event = db.Column(db.String(200))          # e.g. "Half marathon"
    target_date = db.Column(db.Date)

    preferences_text = db.Column(db.Text)             # likes/dislikes
    constraints_text = db.Column(db.Text)             # time / equipment / schedule constraints

    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class UserState(db.Model):
    """Time-sensitive state. MUST be timestamped and can expire."""

    __tablename__ = "user_state"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    kind = db.Column(db.String(50), nullable=False)  # injury, fatigue, stress, sleep, other
    summary = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    severity = db.Column(db.Integer)  # 1-5

    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Activity(db.Model):
    __tablename__ = "activities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    activity_type = db.Column(db.String(50))
    start_time = db.Column(db.DateTime)
    duration = db.Column(db.Integer)  # seconds
    distance = db.Column(db.Float)    # meters
    avg_hr = db.Column(db.Integer)
    notes = db.Column(db.Text)

    exercises = db.relationship("Exercise", backref="activity", cascade="all, delete-orphan")


class Exercise(db.Model):
    __tablename__ = "exercises"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False, index=True)

    name = db.Column(db.String(100))
    sets = db.Column(db.Integer)
    reps = db.Column(db.Integer)
    weight = db.Column(db.Float)


class WorkoutPlan(db.Model):
    __tablename__ = "workout_plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    name = db.Column(db.String(100))
    exercises = db.relationship("PlanExercise", backref="plan", cascade="all, delete-orphan")


class PlanExercise(db.Model):
    __tablename__ = "plan_exercises"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("workout_plans.id"), nullable=False, index=True)

    name = db.Column(db.String(100))
    default_sets = db.Column(db.Integer)
    default_reps = db.Column(db.Integer)


class GeneratedPlan(db.Model):
    """Saved AI-generated short-term plan shown on the dashboard."""

    __tablename__ = "generated_plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    start_date = db.Column(db.Date, default=date.today)
    horizon_days = db.Column(db.Integer, default=4)

    html_content = db.Column(db.Text, nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    sender = db.Column(db.String(10))  # 'user' lub 'ai'
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class TrainingCheckin(db.Model):
    """User-provided check-in after a workout: screenshot + short note.

    This is intentionally lightweight. Later you can connect it to a specific Activity via activity_id.
    """

    __tablename__ = "training_checkins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    notes = db.Column(db.Text)
    image_path = db.Column(db.String(500))
