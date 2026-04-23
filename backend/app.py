import os

from flask import Flask
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

    start_scheduler(app)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
