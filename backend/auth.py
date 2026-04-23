import os

import requests
from flask import Blueprint, current_app, redirect, request, session, url_for
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from models import User, db

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

if os.getenv("FLASK_ENV") == "development":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar",
]


def build_google_flow():
    client_config = {
        "web": {
            "client_id": current_app.config["GOOGLE_CLIENT_ID"],
            "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
        }
    }
    flow = Flow.from_client_config(client_config, scopes=GOOGLE_SCOPES)
    flow.redirect_uri = url_for("auth.callback", _external=True)
    return flow


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def refresh_user_token(user):
    credentials = Credentials(
        token=user.access_token,
        refresh_token=user.refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=current_app.config["GOOGLE_CLIENT_ID"],
        client_secret=current_app.config["GOOGLE_CLIENT_SECRET"],
        scopes=GOOGLE_SCOPES,
    )
    credentials.refresh(Request())
    user.access_token = credentials.token
    db.session.commit()
    return credentials


@auth_bp.get("/login")
def login():
    flow = build_google_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    session["oauth_state"] = state
    return redirect(authorization_url)


@auth_bp.get("/callback")
def callback():
    state = request.args.get("state")
    if not state or state != session.get("oauth_state"):
        return {"error": "invalid state"}, 400

    flow = build_google_flow()
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    try:
        response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=10,
        )
        response.raise_for_status()
        userinfo = response.json()
    except requests.RequestException:
        return {"error": "Failed to fetch user info from Google"}, 502

    user = User.query.filter_by(google_id=userinfo["sub"]).first()
    if user:
        user.email = userinfo["email"]
        user.access_token = credentials.token
        if credentials.refresh_token:
            user.refresh_token = credentials.refresh_token
    else:
        user = User(
            google_id=userinfo["sub"],
            email=userinfo["email"],
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            city=None,
            country=None,
        )
        db.session.add(user)

    db.session.commit()
    session["user_id"] = user.id
    session.pop("oauth_state", None)
    return redirect(f'{current_app.config["FRONTEND_URL"]}/dashboard')


@auth_bp.get("/logout")
def logout():
    session.clear()
    return {"status": "logged_out"}


@auth_bp.get("/me")
def me():
    user = get_current_user()
    if not user:
        return {"error": "not authenticated"}, 401

    return {
        "email": user.email,
        "city": user.city,
        "country": user.country,
        "calendar_id": user.calendar_id,
    }
