from flask import Flask
from flask_cors import CORS
from config import Config
from models import db
from scheduler import start_scheduler

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app, origins=[app.config["FRONTEND_URL"]], supports_credentials=True)
    db.init_app(app)

    with app.app_context():
        db.create_all()

    from auth import auth_bp
    app.register_blueprint(auth_bp)

    start_scheduler(app)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
