import os

from flask import Flask, request
from flask_cors import CORS
from config import Config
from models import db
from scheduler import start_scheduler

def create_app():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, instance_path=base_dir)
    app.config.from_object(Config)
    CORS(app, origins=[app.config["FRONTEND_URL"]], supports_credentials=True)
    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    @app.get("/api/detect-city")
    def detect_city():
        from prayer_service import detect_city_from_ip

        forwarded_for = request.headers.get("X-Forwarded-For", "")
        client_ip = (
            forwarded_for.split(",")[0].strip()
            or request.headers.get("X-Real-IP", "").strip()
            or request.headers.get("CF-Connecting-IP", "").strip()
            or (request.remote_addr or "").strip()
        )

        try:
            location = detect_city_from_ip(client_ip)
            return location, 200
        except ValueError:
            return {"error": "Could not detect city"}, 502

    @app.get("/api/prayer-times")
    def prayer_times():
        from auth import get_current_user
        from prayer_service import get_week_prayer_times

        user = get_current_user()
        if not user:
            return {"error": "not authenticated"}, 401

        city = request.args.get("city") or user.city
        country = request.args.get("country") or user.country

        if not city or not country:
            return {"error": "City not set. Update your settings first."}, 400

        try:
            week_times = get_week_prayer_times(city, country)
        except ValueError as exc:
            return {"error": str(exc)}, 502

        return [
            {
                "date": day["date"].isoformat(),
                "times": day["times"],
            }
            for day in week_times
        ], 200

    @app.post("/api/sync")
    def sync():
        from auth import get_current_user
        from scheduler import sync_user

        user = get_current_user()
        if not user:
            return {"error": "not authenticated"}, 401
        if not user.city:
            return {"error": "City not set. Please update your settings first."}, 400

        sync_user(user)
        return {"status": "synced"}, 200

    @app.post("/api/disconnect")
    def disconnect():
        from auth import get_current_user
        from calendar_service import build_service, delete_all_user_events
        from models import PrayerEvent

        user = get_current_user()
        if not user:
            return {"error": "not authenticated"}, 401

        if user.calendar_id:
            try:
                service = build_service(user)
                delete_all_user_events(service, user, user.calendar_id)
            except Exception:
                PrayerEvent.query.filter_by(user_id=user.id).delete()
                db.session.commit()
        else:
            PrayerEvent.query.filter_by(user_id=user.id).delete()
            db.session.commit()

        user.calendar_id = None
        db.session.commit()
        from flask import session
        session.clear()
        return {"status": "disconnected"}, 200

    @app.patch("/api/settings")
    def settings():
        from auth import get_current_user

        user = get_current_user()
        if not user:
            return {"error": "not authenticated"}, 401

        data = request.get_json(silent=True) or {}
        allowed = {"city", "country", "timezone", "event_duration_min", "reminders_enabled"}

        for key in allowed:
            if key not in data:
                continue
            if key == "event_duration_min":
                val = data[key]
                if not isinstance(val, int) or not (1 <= val <= 60):
                    return {"error": "event_duration_min must be between 1 and 60"}, 400
            setattr(user, key, data[key])

        db.session.commit()
        return {
            "city": user.city,
            "country": user.country,
            "timezone": user.timezone,
            "event_duration_min": user.event_duration_min,
            "reminders_enabled": user.reminders_enabled,
        }, 200

    from auth import auth_bp
    app.register_blueprint(auth_bp)

    start_scheduler(app)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
