import requests
from datetime import date, timedelta

ALADHAN_URL = "http://api.aladhan.com/v1/timingsByCity"
IP_API_URL = "http://ip-api.com/json"
PRAYERS = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]


def detect_city_from_ip(ip_address: str) -> dict:
    try:
        response = requests.get(
            f"{IP_API_URL}/{ip_address}",
            params={"fields": "city,country,countryCode,timezone,status,message"},
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError("Could not detect city from IP") from exc

    payload = response.json()

    if payload.get("status") != "success":
        raise ValueError("Could not detect city from IP")

    return {
        "city": payload.get("city"),
        "country": payload.get("country"),
        "timezone": payload.get("timezone"),
    }


def get_prayer_times(city: str, country: str, target_date: date) -> dict:
    if not city or not country:
        raise ValueError(f"Could not fetch prayer times for {city}")

    params = {
        "city": city,
        "country": country,
        "date": target_date.strftime("%d-%m-%Y"),
        "method": 4,
    }
    try:
        response = requests.get(ALADHAN_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"Could not fetch prayer times for {city}") from exc

    payload = response.json()
    if payload.get("code") != 200 or "data" not in payload:
        raise ValueError(f"Could not fetch prayer times for {city}")

    timings = payload["data"]["timings"]
    return {prayer: timings[prayer][:5] for prayer in PRAYERS}


def get_week_prayer_times(city: str, country: str) -> list[dict]:
    today = date.today()
    return [
        {
            "date": today + timedelta(days=offset),
            "times": get_prayer_times(city, country, today + timedelta(days=offset)),
        }
        for offset in range(7)
    ]
