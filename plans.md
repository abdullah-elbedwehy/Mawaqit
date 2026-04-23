# Mawaqit — Implementation Plans

Each phase is self-contained. Do not start the next phase until the current one passes its verification checklist.
Do not add features not listed. Do not refactor things not listed. Do not create files not listed.
Read every instruction twice before touching a file.

---

## PHASE 1 — Backend Foundation

**Goal:** A running Flask app with a working SQLite database, proper config loading, and a health check route. Nothing else.

### Files to create / modify

| File | Action |
|------|--------|
| `backend/config.py` | Already exists — verify it loads from `.env` correctly |
| `backend/models.py` | Already exists — verify schema matches spec below |
| `backend/app.py` | Already exists — wire everything together, add `/health` route |
| `backend/.env` | Create from `.env.example`, fill in placeholder values for local dev |

### Exact requirements

**`config.py`**
- Load `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `FLASK_SECRET_KEY`, `FRONTEND_URL` from `.env` via `python-dotenv`.
- If any of `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` is missing, raise a clear `RuntimeError` at startup.
- `SQLALCHEMY_DATABASE_URI` must be `sqlite:///mawaqit.db` (stored inside `/backend/`).

**`models.py`**
- Two tables: `users` and `prayer_events`. Exact columns:
  ```
  users:
    id                 INTEGER PRIMARY KEY
    google_id          TEXT UNIQUE NOT NULL
    email              TEXT NOT NULL
    access_token       TEXT
    refresh_token      TEXT
    city               TEXT
    country            TEXT
    event_duration_min INTEGER DEFAULT 5
    reminders_enabled  BOOLEAN DEFAULT 1
    calendar_id        TEXT
    created_at         DATETIME DEFAULT now

  prayer_events:
    id             INTEGER PRIMARY KEY
    user_id        INTEGER FK → users.id NOT NULL
    prayer_name    TEXT NOT NULL   (one of: Fajr, Dhuhr, Asr, Maghrib, Isha)
    event_date     DATE NOT NULL
    gcal_event_id  TEXT
    scheduled_time DATETIME
  ```
- Add a `UniqueConstraint` on `(user_id, prayer_name, event_date)` to prevent duplicates at DB level.

**`app.py`**
- Flask app factory `create_app()`.
- Register CORS with `origins=[config.FRONTEND_URL]` and `supports_credentials=True`.
- Call `db.create_all()` inside app context on startup.
- Register a `/health` GET route that returns `{"status": "ok"}` with 200.
- Import and start the scheduler (already stubbed in `scheduler.py`).
- Do NOT register any other blueprints yet.

### Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Verification checklist
- [ ] `python app.py` starts without errors
- [ ] `curl http://localhost:5000/health` returns `{"status": "ok"}`
- [ ] `mawaqit.db` is created in `/backend/` with both tables and the unique constraint
- [ ] Missing env var raises `RuntimeError` at startup (test by temporarily removing `GOOGLE_CLIENT_ID`)

---

## PHASE 2 — Google OAuth

**Goal:** A user can sign in with Google. Their tokens and profile are stored in SQLite. Session is maintained. The user can log out.

### Files to create / modify

| File | Action |
|------|--------|
| `backend/auth.py` | Full implementation |
| `backend/app.py` | Register `auth_bp` |

### Exact requirements

**OAuth flow using `google-auth-oauthlib`**

1. `GET /auth/login`
   - Build the Google authorization URL with scopes:
     - `openid`
     - `https://www.googleapis.com/auth/userinfo.email`
     - `https://www.googleapis.com/auth/calendar`
   - Set `access_type=offline` and `prompt=consent` (required to get refresh token every time).
   - Store the `state` in Flask session for CSRF protection.
   - Redirect the user to Google.

2. `GET /auth/callback`
   - Verify `state` matches session.
   - Exchange code for tokens using `Flow.fetch_token()`.
   - Extract `access_token` and `refresh_token` from credentials.
   - Call Google's userinfo endpoint to get `google_id` (sub) and `email`.
   - Upsert user in DB:
     - If user with `google_id` exists: update `access_token`, `refresh_token` (if new one was issued).
     - If not: create new user. Set `city` and `country` to `None` — geolocation happens later.
   - Store `user_id` in Flask session.
   - Redirect to `FRONTEND_URL/dashboard`.

3. `GET /auth/logout`
   - Clear Flask session.
   - Return `{"status": "logged_out"}`.

4. `GET /auth/me`
   - Require session. If no session, return 401 `{"error": "not authenticated"}`.
   - Return `{"email": ..., "city": ..., "country": ..., "calendar_id": ...}`.

**Helper: `get_current_user()`**
- A function (not a route) that reads `user_id` from session and returns the `User` object, or `None`.
- Use this in every protected route from now on.

**Token refresh helper**
- Write a function `refresh_user_token(user)` that:
  - Uses `google.oauth2.credentials.Credentials` + `google.auth.transport.requests.Request` to refresh.
  - Updates `user.access_token` in DB.
  - Returns refreshed credentials.
- This will be called from `calendar_service.py` later. Write it here, import it there.

### What NOT to do
- Do not implement IP geolocation here. City stays `None` after login.
- Do not create the Google Calendar here.
- Do not run any sync here.

### Verification checklist
- [ ] `GET /auth/login` redirects to `accounts.google.com`
- [ ] After completing Google sign-in, user is redirected to `FRONTEND_URL/dashboard`
- [ ] User row exists in `users` table with `access_token` and `refresh_token` populated
- [ ] `GET /auth/me` returns correct user data when session is active
- [ ] `GET /auth/me` returns 401 when no session
- [ ] `GET /auth/logout` clears session; subsequent `/auth/me` returns 401

---

## PHASE 3 — Prayer Service + Geolocation

**Goal:** Given a city and country, fetch prayer times from AlAdhan. Given an IP, detect city and country. Both functions work correctly and handle errors gracefully.

### Files to create / modify

| File | Action |
|------|--------|
| `backend/prayer_service.py` | Full implementation |
| `backend/app.py` | Add `/api/detect-city` and `/api/prayer-times` routes |

### Exact requirements

**`prayer_service.py`**

```python
PRAYERS = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
```

Function 1: `detect_city_from_ip(ip_address: str) -> dict`
- Call `http://ip-api.com/json/{ip}?fields=city,country,countryCode,status,message`
- If `status == "success"`: return `{"city": ..., "country": ...}` (use `country` field, not `countryCode`).
- If `status == "fail"` or request fails: raise `ValueError("Could not detect city from IP")`.
- Timeout: 5 seconds.

Function 2: `get_prayer_times(city: str, country: str, target_date: date) -> dict`
- Call `http://api.aladhan.com/v1/timingsByCity`
- Params: `city`, `country`, `date` (formatted as `DD-MM-YYYY`), `method=4` (Umm Al-Qura — good default for Middle East).
- Return only the 5 prayers: `{prayer_name: "HH:MM" string, ...}`.
- If API returns error code or request fails: raise `ValueError(f"Could not fetch prayer times for {city}")`.
- Timeout: 10 seconds.

Function 3: `get_week_prayer_times(city: str, country: str) -> list[dict]`
- Call `get_prayer_times` for today + 6 days.
- Return: `[{"date": date_obj, "times": {prayer: "HH:MM", ...}}, ...]`

**Routes in `app.py`**

`GET /api/detect-city`
- Get client IP from `request.headers.get("X-Forwarded-For", request.remote_addr)`.
- Call `detect_city_from_ip(ip)`.
- Return `{"city": ..., "country": ...}`.
- On error: return 502 `{"error": "Could not detect city"}`.

`GET /api/prayer-times`
- Require session (use `get_current_user()`). Return 401 if not logged in.
- Get `city` and `country` from query params (or fall back to user's stored city/country).
- Call `get_week_prayer_times(city, country)`.
- Return the list serialized with dates as `"YYYY-MM-DD"` strings.
- On error: return 502 `{"error": "..."}`.

### What NOT to do
- Do not convert "HH:MM" strings to timezone-aware datetimes here. That happens in `calendar_service.py`.
- Do not store anything to DB here. Routes only read.

### Verification checklist
- [ ] `GET /api/detect-city` returns city/country (may be wrong on VPN — that's acceptable)
- [ ] `GET /api/prayer-times?city=Riyadh&country=Saudi Arabia` returns 7 days of 5 prayers
- [ ] Prayer times are strings in `"HH:MM"` format
- [ ] Bad city name returns 502 with error message, not a 500 crash

---

## PHASE 4 — Google Calendar Service

**Goal:** Given a logged-in user, create their Mawaqit calendar if it doesn't exist, and upsert/delete prayer events correctly.

### Files to create / modify

| File | Action |
|------|--------|
| `backend/calendar_service.py` | Full implementation |

### Exact requirements

**`calendar_service.py`**

All functions take `user` (a `User` model instance) as first argument.

---

`build_service(user) -> Resource`
- Call `refresh_user_token(user)` from `auth.py` to get fresh credentials.
- Build and return a Google Calendar API service object.

---

`get_or_create_calendar(service, user) -> str`
- If `user.calendar_id` is not None: verify the calendar still exists by calling `service.calendars().get(calendarId=user.calendar_id).execute()`.
  - If it returns 404: set `user.calendar_id = None` and continue.
- If `user.calendar_id` is None: create a new calendar:
  ```python
  body = {"summary": "Mawaqit", "description": "Prayer times synced by Mawaqit"}
  ```
- Save the new `calendar_id` to `user.calendar_id` in DB.
- Return the `calendar_id`.

---

`parse_prayer_datetime(date_obj: date, time_str: str, timezone_str: str) -> datetime`
- Combine `date_obj` and `time_str` ("HH:MM") into a timezone-aware `datetime`.
- Use the `pytz` library with the provided `timezone_str` (e.g., `"Asia/Riyadh"`).
- This is the only place timezones are handled.

---

`upsert_prayer_event(service, user, calendar_id, prayer_name, event_date, time_str, timezone_str) -> str`
- Look up `PrayerEvent` in DB where `user_id=user.id`, `prayer_name=prayer_name`, `event_date=event_date`.
- Build event body:
  ```python
  dt_start = parse_prayer_datetime(event_date, time_str, timezone_str)
  dt_end = dt_start + timedelta(minutes=user.event_duration_min)
  body = {
      "summary": prayer_name,
      "start": {"dateTime": dt_start.isoformat(), "timeZone": timezone_str},
      "end":   {"dateTime": dt_end.isoformat(),   "timeZone": timezone_str},
      "reminders": {
          "useDefault": False,
          "overrides": [{"method": "popup", "minutes": 5}] if user.reminders_enabled else []
      }
  }
  ```
- If `PrayerEvent` row exists and has `gcal_event_id`:
  - Call `service.events().update(...)`.
  - Update `scheduled_time` in DB row.
- If no row or no `gcal_event_id`:
  - Call `service.events().insert(...)`.
  - Create `PrayerEvent` row with the new `gcal_event_id`.
- Commit DB changes.
- Return the `gcal_event_id`.

---

`delete_past_events(service, user, calendar_id)`
- Query all `PrayerEvent` rows for `user_id=user.id` where `event_date < date.today()`.
- For each row:
  - If `gcal_event_id` is not None: call `service.events().delete(...)`. Ignore 404 errors (event already gone).
  - Delete the DB row.
- Commit.

---

**Timezone note:** Do not hardcode a timezone. The right approach for MVP: use `ip-api.com`'s `timezone` field when detecting city. Store it in the `users` table. Add a `timezone` column to `users`:

```
users.timezone  TEXT DEFAULT "Asia/Riyadh"
```

Update `detect_city_from_ip` in `prayer_service.py` to also return `timezone` from the ip-api response (add `timezone` to the fields param). Update the `/auth/callback` flow to store `timezone` if city is detected on first login.

### What NOT to do
- Do not call the AlAdhan API here. Receive prayer time strings as parameters.
- Do not run geolocation here.

### Add to `requirements.txt`
```
pytz
```

### Verification checklist
- [ ] After calling `get_or_create_calendar`, `user.calendar_id` is populated in DB
- [ ] Calling `upsert_prayer_event` twice for the same prayer/date updates, does not create a duplicate
- [ ] `delete_past_events` removes DB rows and deletes events from Google Calendar
- [ ] A 404 from Google Calendar during delete does not crash the function

---

## PHASE 5 — Sync Engine

**Goal:** A single `sync_user(user)` function that orchestrates the full sync. APScheduler runs it for all users at 01:00 daily. A manual `/api/sync` endpoint triggers it immediately.

### Files to create / modify

| File | Action |
|------|--------|
| `backend/scheduler.py` | Full implementation of `sync_user` and scheduler |
| `backend/app.py` | Add `POST /api/sync`, `POST /api/disconnect`, `PATCH /api/settings` routes |

### Exact requirements

**`sync_user(user)` in `scheduler.py`**

```
1. Build Google Calendar service (calendar_service.build_service)
2. Get or create the Mawaqit calendar (calendar_service.get_or_create_calendar)
3. Delete past events (calendar_service.delete_past_events)
4. Call prayer_service.get_week_prayer_times(user.city, user.country)
5. For each day, for each of the 5 prayers:
     call calendar_service.upsert_prayer_event(...)
6. Commit any remaining DB changes
7. Log success: print(f"Synced {user.email}")
```

Error handling:
- If step 1 or 2 fails (auth error): log the error, do not raise, continue to next user.
- If a single prayer upsert fails: log it, continue with remaining prayers.
- Never let one user's failure stop other users from syncing.

**`sync_all_users(app)` in `scheduler.py`**
- Query all users where `city IS NOT NULL` (skip users who haven't set their city yet).
- Call `sync_user(user)` for each, wrapped in try/except.

**`start_scheduler(app)`**
- Use `BackgroundScheduler`.
- Add job: `sync_all_users`, trigger `cron`, `hour=1`, `minute=0` (runs at 01:00 server time daily).
- Call `scheduler.start()`.
- Register `atexit.register(scheduler.shutdown)` to clean up on exit.

---

**Routes in `app.py`**

`POST /api/sync`
- Require session. Return 401 if not logged in.
- If `user.city` is None: return 400 `{"error": "City not set. Please update your settings first."}`.
- Call `sync_user(user)` synchronously (this is a demo — async not needed).
- Return `{"status": "synced"}`.

`POST /api/disconnect`
- Require session.
- Delete all `PrayerEvent` rows for the user (and delete them from Google Calendar first).
- Set `user.calendar_id = None`.
- Clear session.
- Return `{"status": "disconnected"}`.

`PATCH /api/settings`
- Require session.
- Accept JSON body with any subset of: `city`, `country`, `timezone`, `event_duration_min`, `reminders_enabled`.
- Validate: `event_duration_min` must be between 1 and 60 if provided.
- Update user fields. Commit.
- Return updated user fields.

### Verification checklist
- [ ] `POST /api/sync` with a logged-in user triggers a full sync — events appear in Google Calendar
- [ ] Running sync twice does not create duplicate events
- [ ] `POST /api/sync` with no city returns 400
- [ ] `POST /api/disconnect` removes all calendar events and clears the user's `calendar_id`
- [ ] `PATCH /api/settings` with `{"city": "Dubai", "country": "UAE"}` updates the DB
- [ ] APScheduler job is registered and visible at startup (check logs)

---

## PHASE 6 — Frontend Foundation

**Goal:** Vite + React + Tailwind fully configured and running. Routing works. A shared API client exists. Auth state is managed globally.

### Files to create / modify

| File | Action |
|------|--------|
| `frontend/package.json` | Create with all dependencies |
| `frontend/vite.config.js` | Create with proxy config |
| `frontend/tailwind.config.js` | Create |
| `frontend/postcss.config.js` | Create |
| `frontend/index.html` | Create |
| `frontend/src/api.js` | Create — central API client |
| `frontend/src/AuthContext.jsx` | Create — global auth state |
| `frontend/src/App.jsx` | Update — wrap with AuthContext, add protected routes |

### Exact requirements

**`package.json` dependencies**
```json
{
  "dependencies": {
    "react": "^18",
    "react-dom": "^18",
    "react-router-dom": "^6",
    "axios": "^1"
  },
  "devDependencies": {
    "vite": "^5",
    "@vitejs/plugin-react": "^4",
    "tailwindcss": "^3",
    "postcss": "^8",
    "autoprefixer": "^10"
  }
}
```

**`vite.config.js`**
- Proxy `/auth` and `/api` to `http://localhost:5000` so CORS is not an issue in dev.
  ```js
  server: {
    proxy: {
      "/auth": "http://localhost:5000",
      "/api": "http://localhost:5000"
    }
  }
  ```

**`frontend/src/api.js`**
- Create an `axios` instance with `baseURL: ""` and `withCredentials: true`.
- Export named functions (not the raw axios instance):
  ```js
  export const getMe = () => api.get("/auth/me")
  export const logout = () => api.get("/auth/logout")
  export const detectCity = () => api.get("/api/detect-city")
  export const sync = () => api.post("/api/sync")
  export const disconnect = () => api.post("/api/disconnect")
  export const updateSettings = (data) => api.patch("/api/settings", data)
  export const getPrayerTimes = (city, country) =>
    api.get("/api/prayer-times", { params: { city, country } })
  ```

**`frontend/src/AuthContext.jsx`**
- Create a React context with: `{ user, setUser, loading }`.
- On mount, call `getMe()`. If 200: set `user`. If 401: set `user = null`.
- Set `loading = false` after the call.
- Export `AuthProvider` (wraps children) and `useAuth` hook.

**`App.jsx`**
- Wrap everything in `<AuthProvider>`.
- Route `/` → `<Home />`
- Route `/dashboard` → `<ProtectedRoute><Dashboard /></ProtectedRoute>`
- Route `/settings` → `<ProtectedRoute><Settings /></ProtectedRoute>`
- `ProtectedRoute`: if `loading`, show a spinner. If `!user`, redirect to `/`. Otherwise render children.

### Verification checklist
- [ ] `npm install` in `/frontend` succeeds
- [ ] `npm run dev` starts on port 5173 without errors
- [ ] Navigating to `/dashboard` without a session redirects to `/`
- [ ] `getMe()` in browser console returns the logged-in user's data when session exists

---

## PHASE 7 — Frontend Pages

**Goal:** Three fully functional pages. No placeholder text. Real data. Real interactions.

### Files to create / modify

| File | Action |
|------|--------|
| `frontend/src/pages/Home.jsx` | Full implementation |
| `frontend/src/pages/Dashboard.jsx` | Full implementation |
| `frontend/src/pages/Settings.jsx` | Full implementation |

### Exact requirements

---

**`Home.jsx`**
- If user is already logged in (from `useAuth`): redirect to `/dashboard` immediately.
- Show centered card:
  - App name "Mawaqit" in large text
  - Subtitle: "Your prayer times, automatically in Google Calendar."
  - A "Sign in with Google" button — links to `/auth/login` (plain `<a>` tag, not React Router link — it causes a full redirect).
- No other UI elements.

---

**`Dashboard.jsx`**
- On mount:
  - If `user.city` is null: call `detectCity()` and pre-fill city/country in state (not saved yet — just shown to user).
  - Call `getPrayerTimes(city, country)` to load this week's schedule.
- Show:
  - Header: "Mawaqit" + user email (small, top right).
  - If city is not set: a highlighted notice "We detected your city as **[city]**. Is this correct?" with a Confirm button and an Edit button.
  - If city is set: show city name with an Edit link next to it.
  - A table or card list showing prayer times for the next 7 days (prayer name + time per row).
  - A "Sync Now" button → calls `sync()` → shows "Synced!" or error message.
  - A "Settings" link → navigates to `/settings`.
- States to handle: loading, error from prayer API, sync in progress.

---

**`Settings.jsx`**
- Load current user data from `useAuth`.
- Form fields:
  - City (text input)
  - Country (text input)
  - Event duration (number input, min=1, max=60, label: "Event duration (minutes)")
  - Reminders (checkbox, label: "Enable prayer reminders")
- Save button → calls `updateSettings(formData)` → shows "Saved!" on success.
- Danger zone section at the bottom:
  - "Disconnect" button → calls `disconnect()` → redirects to `/` after success.
  - "Sync Now" button → calls `sync()` → shows result inline.
- No dropdowns for calculation method or madhhab. No language toggle.

---

### Design rules (Tailwind)
- Use a clean white background with a green accent color (`green-600`).
- Mobile-first. Stack everything vertically on small screens.
- No custom CSS files — Tailwind only.
- No UI library (no shadcn, no MUI, no Chakra).
- Keep it simple — this is a school project, not a portfolio piece.

### Verification checklist
- [ ] Logged-out user sees Home page, cannot reach Dashboard
- [ ] After Google sign-in, user lands on Dashboard
- [ ] Dashboard shows prayer times for 7 days
- [ ] "Sync Now" triggers sync and shows result
- [ ] Settings saves correctly — changing city and saving, then revisiting Settings shows the new city
- [ ] Disconnect removes calendar events and redirects to Home

---

## PHASE 8 — First-Time Setup Flow

**Goal:** On first login, auto-detect the user's city, prompt them to confirm or change it, then immediately run the first sync. This is the "wow moment" of the demo.

### Files to create / modify

| File | Action |
|------|--------|
| `backend/auth.py` | After callback: detect city from IP and store if `user.city` is None |
| `frontend/src/pages/Dashboard.jsx` | Handle first-time state (city not confirmed yet) |

### Exact requirements

**`auth.py` — in the callback route, after upserting user:**
- If `user.city` is None:
  - Get client IP from `request.headers.get("X-Forwarded-For", request.remote_addr)`.
  - Call `detect_city_from_ip(ip)` from `prayer_service.py`.
  - If successful: set `user.city`, `user.country`, `user.timezone`. Commit.
  - If it fails: leave them as `None`. The user will set them manually.
- Do not run sync in the callback — that happens when the user confirms their city.

**`Dashboard.jsx` — first-time flow:**
- If `user.city` is None after mount (geolocation also failed): show a text input asking the user to enter their city manually. Save button calls `updateSettings` then `sync`.
- If `user.city` is set but this is their first login (detect by `user.calendar_id === null`): show "Setting up your calendar..." and immediately call `sync()`. Show a loading spinner during sync.
- After first sync completes: show the prayer times table normally.

### Verification checklist
- [ ] New user logs in → city is auto-detected and stored → `sync()` is called → events appear in Google Calendar within 30 seconds of login
- [ ] New user on VPN (city detection fails) → sees manual city input → enters city → clicks Save → sync runs → events appear
- [ ] Returning user logs in → goes straight to Dashboard with prayer times already visible

---

## PHASE 9 — Final Polish & Error Hardening

**Goal:** Make it demo-ready. Handle the failure cases that will definitely happen during a live demo.

### Things to fix / add

**Backend**
- Wrap every Google API call in a try/except for `google.auth.exceptions.RefreshError`. When caught: set `user.access_token = None`, `user.refresh_token = None` in DB, return 401 with `{"error": "reauth_required"}` to frontend.
- Add `GOOGLE_REDIRECT_URI` to config (must match what is set in Google Cloud Console exactly).
- Return proper JSON errors (not HTML Flask error pages) for 404 and 500:
  ```python
  @app.errorhandler(404)
  def not_found(e): return {"error": "not found"}, 404
  @app.errorhandler(500)
  def server_error(e): return {"error": "internal server error"}, 500
  ```

**Frontend**
- If any API call returns `{"error": "reauth_required"}` or 401: clear local auth state and redirect to `/`.
- Add a loading state to every button that makes an API call. Disable button while in progress.
- Show error messages inline (not alert() popups).
- Dashboard: if prayer times fail to load, show "Could not load prayer times. Check your city settings." with a link to Settings.

**`.env.example`** — document every variable with a comment explaining what it is and where to get it.

**`README.md`** — write a minimal setup guide:
1. Google Cloud Console setup (OAuth credentials, Calendar API enabled)
2. Backend setup (`pip install`, `.env` config, `python app.py`)
3. Frontend setup (`npm install`, `npm run dev`)
4. How to use the app

### Verification checklist
- [ ] Expired/revoked token → app redirects user to login, does not crash
- [ ] All buttons show loading state during async operations
- [ ] No `alert()` calls anywhere in the frontend
- [ ] `README.md` is clear enough for the professor to run the project locally

---

## Phase Order Summary

```
Phase 1  →  Flask + SQLite foundation
Phase 2  →  Google OAuth (login / logout / session)
Phase 3  →  Prayer times API + IP geolocation
Phase 4  →  Google Calendar create + upsert + delete
Phase 5  →  Sync engine + scheduler + API routes
Phase 6  →  Frontend scaffold (Vite + Tailwind + auth context)
Phase 7  →  Frontend pages (Home, Dashboard, Settings)
Phase 8  →  First-time setup flow
Phase 9  →  Error hardening + demo polish
```

Do not skip phases. Do not merge phases. One phase at a time.
