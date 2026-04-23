# AlAdhan API — fetch prayer times
import requests
from datetime import date, timedelta

ALADHAN_URL = "http://api.aladhan.com/v1/timingsByCity"
PRAYERS = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]

def get_prayer_times(city: str, country: str, target_date: date) -> dict:
    params = {
        "city": city,
        "country": country,
        "date": target_date.strftime("%d-%m-%Y"),
    }
    resp = requests.get(ALADHAN_URL, params=params, timeout=10)
    resp.raise_for_status()
    timings = resp.json()["data"]["timings"]
    return {p: timings[p] for p in PRAYERS}

def get_week_prayer_times(city: str, country: str) -> list[dict]:
    today = date.today()
    return [
        {"date": today + timedelta(days=i), "times": get_prayer_times(city, country, today + timedelta(days=i))}
        for i in range(7)
    ]
