from datetime import date, datetime, timedelta

import pytz
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from models import PrayerEvent, db

CALENDAR_NAME = "Mawaqit"


def build_service(user):
    from auth import refresh_user_token
    credentials = refresh_user_token(user)
    return build("calendar", "v3", credentials=credentials)


def get_or_create_calendar(service, user):
    if user.calendar_id:
        try:
            service.calendars().get(calendarId=user.calendar_id).execute()
            return user.calendar_id
        except HttpError as e:
            if e.resp.status == 404:
                user.calendar_id = None
            else:
                raise

    cal = service.calendars().insert(body={
        "summary": CALENDAR_NAME,
        "description": "Prayer times synced by Mawaqit",
    }).execute()
    user.calendar_id = cal["id"]
    db.session.commit()
    return user.calendar_id


def parse_prayer_datetime(date_obj, time_str, timezone_str):
    tz = pytz.timezone(timezone_str)
    hour, minute = map(int, time_str.split(":"))
    naive = datetime(date_obj.year, date_obj.month, date_obj.day, hour, minute)
    return tz.localize(naive)


def upsert_prayer_event(service, user, calendar_id, prayer_name, event_date, time_str, timezone_str):
    dt_start = parse_prayer_datetime(event_date, time_str, timezone_str)
    dt_end = dt_start + timedelta(minutes=user.event_duration_min)
    body = {
        "summary": prayer_name,
        "start": {"dateTime": dt_start.isoformat(), "timeZone": timezone_str},
        "end": {"dateTime": dt_end.isoformat(), "timeZone": timezone_str},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 5}] if user.reminders_enabled else [],
        },
    }

    existing = PrayerEvent.query.filter_by(
        user_id=user.id,
        prayer_name=prayer_name,
        event_date=event_date,
    ).first()

    if existing and existing.gcal_event_id:
        service.events().update(
            calendarId=calendar_id,
            eventId=existing.gcal_event_id,
            body=body,
        ).execute()
        existing.scheduled_time = dt_start
        db.session.commit()
        return existing.gcal_event_id

    result = service.events().insert(calendarId=calendar_id, body=body).execute()
    gcal_id = result["id"]
    if existing:
        existing.gcal_event_id = gcal_id
        existing.scheduled_time = dt_start
    else:
        db.session.add(PrayerEvent(
            user_id=user.id,
            prayer_name=prayer_name,
            event_date=event_date,
            gcal_event_id=gcal_id,
            scheduled_time=dt_start,
        ))
    db.session.commit()
    return gcal_id


def delete_past_events(service, user, calendar_id):
    past = PrayerEvent.query.filter(
        PrayerEvent.user_id == user.id,
        PrayerEvent.event_date < date.today(),
    ).all()

    for event in past:
        if event.gcal_event_id:
            try:
                service.events().delete(
                    calendarId=calendar_id,
                    eventId=event.gcal_event_id,
                ).execute()
            except HttpError as e:
                if e.resp.status != 404:
                    raise
        db.session.delete(event)

    db.session.commit()


def delete_all_user_events(service, user, calendar_id):
    """Delete all events for a user — used during disconnect."""
    all_events = PrayerEvent.query.filter_by(user_id=user.id).all()

    for event in all_events:
        if event.gcal_event_id:
            try:
                service.events().delete(
                    calendarId=calendar_id,
                    eventId=event.gcal_event_id,
                ).execute()
            except HttpError as e:
                if e.resp.status != 404:
                    raise
        db.session.delete(event)

    db.session.commit()
