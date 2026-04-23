from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.Text, unique=True, nullable=False)
    email = db.Column(db.Text, nullable=False)
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    city = db.Column(db.Text)
    country = db.Column(db.Text)
    event_duration_min = db.Column(db.Integer, default=5)
    reminders_enabled = db.Column(db.Boolean, default=True)
    calendar_id = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    events = db.relationship("PrayerEvent", backref="user", lazy=True)

class PrayerEvent(db.Model):
    __tablename__ = "prayer_events"
    __table_args__ = (
        db.UniqueConstraint("user_id", "prayer_name", "event_date", name="uq_prayer_event_per_day"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    prayer_name = db.Column(db.Text, nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    gcal_event_id = db.Column(db.Text)
    scheduled_time = db.Column(db.DateTime)
