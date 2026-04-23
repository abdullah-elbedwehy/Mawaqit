# Google Calendar — create calendar and upsert prayer events
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

CALENDAR_NAME = "Mawaqit"

def build_service(user):
    creds = Credentials(
        token=user.access_token,
        refresh_token=user.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("calendar", "v3", credentials=creds)

def get_or_create_calendar(service, user):
    if user.calendar_id:
        return user.calendar_id
    cal = service.calendars().insert(body={"summary": CALENDAR_NAME}).execute()
    return cal["id"]

def upsert_event(service, calendar_id, prayer_name, dt_start, duration_min, reminders_enabled, existing_event_id=None):
    dt_end = dt_start + timedelta(minutes=duration_min)
    body = {
        "summary": prayer_name,
        "start": {"dateTime": dt_start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": dt_end.isoformat(), "timeZone": "UTC"},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 5}] if reminders_enabled else [],
        },
    }
    if existing_event_id:
        return service.events().update(calendarId=calendar_id, eventId=existing_event_id, body=body).execute()
    return service.events().insert(calendarId=calendar_id, body=body).execute()

def delete_event(service, calendar_id, event_id):
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
