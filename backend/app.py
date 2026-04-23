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

        forwarded_for = request.headers.get("X-Forwarded-For", request.remote_addr or "")
        client_ip = forwarded_for.split(",")[0].strip()

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

    from auth import auth_bp
    app.register_blueprint(auth_bp)

    start_scheduler(app)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
