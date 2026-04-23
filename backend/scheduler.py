# APScheduler — daily sync job for all users
from apscheduler.schedulers.background import BackgroundScheduler

def sync_all_users(app):
    with app.app_context():
        from models import User
        for user in User.query.all():
            try:
                sync_user(user)
            except Exception as e:
                print(f"Sync failed for {user.email}: {e}")

def sync_user(user):
    pass  # TODO: call prayer_service + calendar_service, update DB

def start_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(sync_all_users, "cron", hour=1, args=[app])
    scheduler.start()
