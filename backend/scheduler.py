import atexit

from apscheduler.schedulers.background import BackgroundScheduler


def sync_user(user):
    from calendar_service import (
        build_service,
        delete_past_events,
        get_or_create_calendar,
        upsert_prayer_event,
    )
    from prayer_service import get_week_prayer_times

    timezone_str = user.timezone or "Asia/Riyadh"

    try:
        service = build_service(user)
        calendar_id = get_or_create_calendar(service, user)
    except Exception as e:
        print(f"Auth/calendar error for {user.email}: {e}")
        return

    delete_past_events(service, user, calendar_id)

    try:
        week_times = get_week_prayer_times(user.city, user.country)
    except ValueError as e:
        print(f"Prayer times error for {user.email}: {e}")
        return

    for day in week_times:
        for prayer, time_str in day["times"].items():
            try:
                upsert_prayer_event(
                    service, user, calendar_id,
                    prayer, day["date"], time_str, timezone_str,
                )
            except Exception as e:
                print(f"Upsert failed {prayer} {day['date']} for {user.email}: {e}")

    print(f"Synced {user.email}")


def sync_all_users(app):
    with app.app_context():
        from models import User
        for user in User.query.filter(User.city.isnot(None)).all():
            try:
                sync_user(user)
            except Exception as e:
                print(f"Sync failed for {user.email}: {e}")


def start_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(sync_all_users, "cron", hour=1, minute=0, args=[app])
    scheduler.start()
    atexit.register(scheduler.shutdown)
