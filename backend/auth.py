# Google OAuth flow
from flask import Blueprint

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.route("/login")
def login():
    pass  # TODO: redirect to Google OAuth

@auth_bp.route("/callback")
def callback():
    pass  # TODO: handle OAuth callback, upsert user, set session

@auth_bp.route("/logout")
def logout():
    pass  # TODO: clear session
