# Mawaqit — Claude Code Reference

## What This Project Is

Mawaqit is a school-project web app that syncs the five daily Islamic prayer times into a user's Google Calendar. The user signs in with Google once, the app auto-detects their city, creates a dedicated calendar named **Mawaqit**, and keeps the next 7 days of prayer events updated daily.

---

## Stack

| Layer     | Tech                        |
|-----------|-----------------------------|
| Frontend  | React + Tailwind CSS (Vite) |
| Backend   | Python + Flask              |
| Database  | SQLite                      |
| Scheduler | APScheduler (inside Flask)  |
| Auth      | Google OAuth 2.0            |
| Calendar  | Google Calendar API         |
| Prayer API| AlAdhan API (free, no key)  |
| Geo IP    | ip-api.com (free, no key)   |

---

## Folder Structure

```
/frontend
  /src
    /pages        — Home.jsx, Dashboard.jsx, Settings.jsx
    /components   — LoginButton.jsx, SyncStatus.jsx, SettingsForm.jsx
  /public
  package.json
  vite.config.js

/backend
  app.py            — Flask app factory, routes
  auth.py           — Google OAuth flow
  calendar_service.py — Google Calendar create/update logic
  prayer_service.py — AlAdhan API calls
  scheduler.py      — APScheduler daily sync job
  models.py         — SQLite models (User, PrayerEvent)
  config.py         — Env-based config
  requirements.txt
  .env.example
```

---

## Database Schema

### users
| column             | type    |
|--------------------|---------|
| id                 | INTEGER PK |
| google_id          | TEXT UNIQUE |
| email              | TEXT    |
| access_token       | TEXT    |
| refresh_token      | TEXT    |
| city               | TEXT    |
| country            | TEXT    |
| event_duration_min | INTEGER (default 5) |
| reminders_enabled  | BOOLEAN (default true) |
| calendar_id        | TEXT    |
| created_at         | DATETIME |

### prayer_events
| column         | type    |
|----------------|---------|
| id             | INTEGER PK |
| user_id        | INTEGER FK → users |
| prayer_name    | TEXT  (Fajr/Dhuhr/Asr/Maghrib/Isha) |
| event_date     | DATE  |
| gcal_event_id  | TEXT  |
| scheduled_time | DATETIME |

---

## Key Decisions

- **City detection**: IP geolocation via `ip-api.com`. Inaccurate on VPNs — manual override always available.
- **Event update strategy**: store `gcal_event_id` per prayer per day. On sync, update existing events if time changed; create if missing. Never delete and recreate.
- **Old event cleanup**: delete Google Calendar events (and DB rows) for dates before today during each sync run.
- **7-day window**: always maintain events for today + next 6 days.
- **Scheduler**: APScheduler runs inside Flask. Restarts reset the schedule — acceptable for school demo.
- **Settings kept minimal**: city, event duration, reminders on/off, disconnect, manual resync.
- **Calculation method / madhhab**: not exposed in UI for simplicity. Use AlAdhan defaults.
- **No duplicate events**: enforced by looking up `gcal_event_id` in DB before creating.

---

## Prayer Names (English only)
Fajr, Dhuhr, Asr, Maghrib, Isha

---

## Environment Variables (.env)
```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
FLASK_SECRET_KEY=
FRONTEND_URL=http://localhost:5173
```

---

## MVP Scope (do not expand)
- Google sign-in
- Auto city detection with manual override
- Create "Mawaqit" Google Calendar
- Sync 5 daily prayers for next 7 days
- Daily auto-sync via scheduler
- Update existing events, delete past ones
- Simple settings: city, duration, reminders, disconnect, resync
- No multi-language, no notifications, no mobile app
