"""The weather on the start page, from AccuWeather (developer.accuweather.com).

Settings › Weather (admins) takes an API key and a place: the city is looked up with the Locations API and its location
key kept. The page asks this
server, never AccuWeather, and the server asks AccuWeather only when its copy is older than the refresh interval, so a
free key (50 calls a day) lasts: the current conditions every hour at most, the next 12 hours every 90 minutes, the
5-day forecast every 6 hours (44 calls on a day the page stays open from morning to night), and nothing at all while
nobody opens the page. What was last fetched is kept in the database (prt_settings), so a restart does
not spend a call either.

The extras cost no more calls: the 5-day forecast asked with details brings each day's sunrise and sunset, its air
quality and its pollen. Severe weather warnings come from the US National Weather Service (api.weather.gov: free, no
key, US places only), by the place's coordinates, which AccuWeather gives once per place (one call when the place is
chosen, kept with it). Warnings are asked at most every 10 minutes, again only while somebody looks.
"""
import datetime as dt
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from iosuite_shared import credentials

from iostart import config, db

APP = config.APP

BASE = "https://dataservice.accuweather.com"
CURRENT_TTL = 60 * 60
HOURLY_TTL = 90 * 60
FORECAST_TTL = 6 * 3600
WARNINGS_TTL = 10 * 60
NWS = "https://api.weather.gov"
POLLEN = ("Tree", "Grass", "Ragweed", "Mold")  # AccuWeather's names, in the order the page lists them
SEVERITY = {"Extreme": 4, "Severe": 3, "Moderate": 2, "Minor": 1}  # the weather service's, most serious first
_lock = threading.Lock()


class WeatherError(Exception):
    pass


# ------------------------------------------------------------------ settings

def api_key() -> str:
    """The key kept with the suite's keys and tokens."""
    try:
        return credentials.get(APP, "accuweather_key").strip()
    except Exception:  # noqa: BLE001 - the shared database is away
        return ""


def location_key() -> str:
    return (db.get_setting("accuweather_location") or "").strip()


def settings() -> dict:
    """What Settings › Weather shows (the key itself never leaves the server)."""
    return {"hasKey": bool(api_key()), "locationKey": location_key(),
            "locationName": db.get_setting("accuweather_location_name") or "",
            "units": db.get_setting("weather_units") or "metric", "enabled": bool(api_key() and location_key())}


def save(changes: dict, by: str = None) -> None:
    """{key?, locationKey?, locationName?, units?}: an empty key or location clears it; a change empties the cache.
    `by`: who changed the key."""
    if "key" in changes:
        credentials.put(APP, "accuweather_key", (changes["key"] or "").strip(), by=by)
    if "locationKey" in changes:
        db.set_setting("accuweather_location", str(changes["locationKey"] or "").strip() or None)
        db.set_setting("accuweather_location_name", (changes.get("locationName") or "").strip() or None)
        db.set_setting("accuweather_location_geo", None)  # the new place's coordinates are asked for once
    if "units" in changes:
        if changes["units"] not in ("metric", "imperial"):
            raise WeatherError("units: metric or imperial")
        db.set_setting("weather_units", changes["units"])
    forget()


def forget() -> None:
    for k in ("weather_current", "weather_forecast", "weather_hourly", "weather_warnings"):
        db.set_setting(k, None)


# ------------------------------------------------------------------ AccuWeather

def _get(path: str, **params) -> object:
    """One call to AccuWeather. Replaced in the tests."""
    params["apikey"] = api_key()
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "iostart"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise WeatherError("AccuWeather refused the API key")
        if e.code == 503:
            raise WeatherError("AccuWeather: the key's daily allowance is used up (try again tomorrow)")
        raise WeatherError(f"AccuWeather answered {e.code}")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise WeatherError(f"Could not reach AccuWeather: {str(e)[:120]}")


def search(q: str, key: str = "") -> list[dict]:
    """Places matching a city name (Settings › Weather), with the key the forecast is fetched by."""
    q = (q or "").strip()
    if not q:
        return []
    if not (key or api_key()):
        raise WeatherError("An API key first")
    if key:  # trying a key before it is saved
        params = {"q": q, "apikey": key}
        url = f"{BASE}/locations/v1/cities/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "iostart"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                found = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raise WeatherError("AccuWeather refused the API key" if e.code == 401 else f"AccuWeather answered {e.code}")
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise WeatherError(f"Could not reach AccuWeather: {str(e)[:120]}")
    else:
        found = _get("/locations/v1/cities/search", q=q)
    out = []
    for p in found if isinstance(found, list) else []:
        out.append({"key": str(p.get("Key")), "name": p.get("LocalizedName") or "",
                    "region": (p.get("AdministrativeArea") or {}).get("LocalizedName") or "",
                    "country": (p.get("Country") or {}).get("LocalizedName") or ""})
    return out[:10]


def _cached(name: str, ttl: int, fetch):
    """The stored answer while it is younger than ttl; else a fresh one, stored. A failed fetch keeps the old answer
    (marked stale) rather than a hole on the page."""
    raw = db.get_setting(name)
    old = json.loads(raw) if raw else None
    now = int(time.time())
    if old and now - old.get("at", 0) < ttl:
        return old
    with _lock:
        raw = db.get_setting(name)  # another request may have fetched it meanwhile
        old = json.loads(raw) if raw else None
        if old and now - old.get("at", 0) < ttl:
            return old
        try:
            data = fetch()
        except WeatherError as e:
            if old:
                return {**old, "stale": True, "error": str(e)}
            raise
        fresh = {"at": now, "data": data}
        db.set_setting(name, json.dumps(fresh))
        return fresh


def _temp(t: dict | None, units: str) -> float | None:
    if not t:
        return None
    v = (t.get("Metric") if units == "metric" else t.get("Imperial")) or {}
    return v.get("Value")


def _fetch_current() -> dict:
    data = _get(f"/currentconditions/v1/{location_key()}", details="true")
    c = data[0] if isinstance(data, list) and data else {}
    return {"text": c.get("WeatherText"), "icon": c.get("WeatherIcon"), "isDay": c.get("IsDayTime", True),
            "temp": {"metric": _temp(c.get("Temperature"), "metric"), "imperial": _temp(c.get("Temperature"), "imperial")},
            "feels": {"metric": _temp(c.get("RealFeelTemperature"), "metric"), "imperial": _temp(c.get("RealFeelTemperature"), "imperial")},
            "humidity": c.get("RelativeHumidity"), "uv": c.get("UVIndex"),
            "wind": {"metric": (((c.get("Wind") or {}).get("Speed") or {}).get("Metric") or {}).get("Value"),
                     "imperial": (((c.get("Wind") or {}).get("Speed") or {}).get("Imperial") or {}).get("Value")},
            "observed": c.get("LocalObservationDateTime"), "link": c.get("Link")}


def _air_and_pollen(d: dict) -> tuple[dict | None, list[dict]]:
    """A day's air quality ({value, category, level 1-6, kind}) and pollen ([{name, value, category, level}] in POLLEN
    order), from AccuWeather's AirAndPollen; level is AccuWeather's CategoryValue (1 good/low ... 6 hazardous)."""
    air, pollen = None, {}
    for x in d.get("AirAndPollen") or []:
        if not isinstance(x, dict):
            continue
        one = {"value": x.get("Value"), "category": x.get("Category") or "", "level": x.get("CategoryValue")}
        if x.get("Name") == "AirQuality":
            air = {**one, "kind": x.get("Type") or ""}
        elif x.get("Name") in POLLEN:
            pollen[x["Name"]] = {"name": x["Name"], **one}
    return air, [pollen[k] for k in POLLEN if k in pollen]


def _fetch_forecast() -> dict:
    data = _get(f"/forecasts/v1/daily/5day/{location_key()}", metric="true", details="true")
    days = []
    for d in (data.get("DailyForecasts") or []) if isinstance(data, dict) else []:
        t = d.get("Temperature") or {}
        day = d.get("Day") or {}
        sun = d.get("Sun") or {}
        air, pollen = _air_and_pollen(d)
        days.append({"date": (d.get("Date") or "")[:10], "min": (t.get("Minimum") or {}).get("Value"), "max": (t.get("Maximum") or {}).get("Value"),
                     "icon": day.get("Icon"), "text": day.get("IconPhrase"), "rain": day.get("PrecipitationProbability"),
                     "sunrise": sun.get("Rise"), "sunset": sun.get("Set"), "air": air, "pollen": pollen})
    return {"headline": ((data.get("Headline") or {}).get("Text") if isinstance(data, dict) else None), "days": days,
            "link": (data.get("Headline") or {}).get("Link") if isinstance(data, dict) else None}


def _fetch_hourly() -> dict:
    data = _get(f"/forecasts/v1/hourly/12hour/{location_key()}", metric="true")
    hours = []
    for x in data if isinstance(data, list) else []:
        hours.append({"t": x.get("DateTime"), "icon": x.get("WeatherIcon"), "text": x.get("IconPhrase"),
                      "temp": (x.get("Temperature") or {}).get("Value"), "rain": x.get("PrecipitationProbability"),
                      "wet": bool(x.get("HasPrecipitation")), "kind": x.get("PrecipitationType")})
    return {"hours": hours}


def _geo() -> dict:
    """The place's {lat, lon, country} (the ISO code), asked of AccuWeather once per place and kept with it."""
    raw = db.get_setting("accuweather_location_geo")
    kept = json.loads(raw) if raw else None
    if kept and "lat" in kept:
        return kept
    if kept and time.time() - kept.get("failedAt", 0) < FORECAST_TTL:  # a failed ask is not repeated on every visit
        raise WeatherError(kept.get("error") or "No coordinates for the place")
    try:
        p = _get(f"/locations/v1/{location_key()}")
        g = (p.get("GeoPosition") or {}) if isinstance(p, dict) else {}
        if g.get("Latitude") is None or g.get("Longitude") is None:
            raise WeatherError("AccuWeather did not give the place's coordinates")
    except WeatherError as e:
        db.set_setting("accuweather_location_geo", json.dumps({"failedAt": int(time.time()), "error": str(e)}))
        raise
    geo = {"lat": g["Latitude"], "lon": g["Longitude"], "country": (p.get("Country") or {}).get("ID") or ""}
    db.set_setting("accuweather_location_geo", json.dumps(geo))
    return geo


def _nws(path: str, **params) -> object:
    """One call to the US National Weather Service. Replaced in the tests."""
    url = f"{NWS}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/geo+json", "User-Agent": "iostart (self-hosted start page)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise WeatherError(f"The weather service answered {e.code}")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise WeatherError(f"Could not reach the weather service: {str(e)[:120]}")


def _fetch_warnings(geo: dict) -> dict:
    """The warnings in force at the place, most serious first: [{id, event, headline, severity, urgency, starts, ends,
    text, instruction, source, area}]."""
    data = _nws("/alerts/active", point=f"{round(geo['lat'], 4)},{round(geo['lon'], 4)}")
    out = []
    for f in (data.get("features") or []) if isinstance(data, dict) else []:
        p = (f or {}).get("properties") or {}
        if p.get("status", "Actual") != "Actual" or p.get("messageType") == "Cancel":
            continue
        out.append({"id": p.get("id") or f.get("id"), "event": p.get("event") or "Weather warning", "headline": p.get("headline") or "",
                    "severity": p.get("severity") or "Unknown", "urgency": p.get("urgency") or "",
                    "starts": p.get("onset") or p.get("effective"), "ends": p.get("ends") or p.get("expires"),
                    "text": (p.get("description") or "").strip()[:4000], "instruction": (p.get("instruction") or "").strip()[:2000],
                    "source": p.get("senderName") or "", "area": (p.get("areaDesc") or "")[:300]})
    out.sort(key=lambda w: -SEVERITY.get(w["severity"], 0))
    return {"items": out, "link": f"https://forecast.weather.gov/MapClick.php?lat={geo['lat']}&lon={geo['lon']}"}


def warnings() -> dict:
    """{items, link, error?} for a place in the United States; {items: [], none: why} elsewhere. Never raises: the
    warnings are an extra beside the forecast."""
    try:
        geo = _geo()
    except WeatherError as e:
        return {"items": [], "none": str(e)}
    if geo.get("country") != "US":
        return {"items": [], "none": "Weather warnings come from the US National Weather Service, for places in the United States"}
    try:
        got = _cached("weather_warnings", WARNINGS_TTL, lambda: _fetch_warnings(geo))
    except WeatherError as e:  # never answered yet: not asked again for 10 minutes either
        db.set_setting("weather_warnings", json.dumps({"at": int(time.time()), "data": {"items": [], "error": str(e)}}))
        return {"items": [], "error": str(e)}
    out = dict(got["data"])
    # a warning past its end time goes even while the copy is a few minutes old
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    out["items"] = [w for w in out["items"] if not w.get("ends") or _utc(w["ends"]) > now]
    if got.get("stale"):
        out["error"] = got.get("error")
    return out


def _utc(stamp: str) -> str:
    """An ISO time with its offset, as UTC "YYYY-MM-DDTHH:MM:SS" (comparable as text); unreadable: far ahead."""
    try:
        return dt.datetime.fromisoformat(stamp).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return "9999"


def current() -> dict:
    """What the widget draws: {enabled, location, units, current, forecast, hourly, warnings}; each forecast day also
    has its sunrise, sunset, air quality and pollen. The forecasts' temperatures come in °C
    (AccuWeather gives one unit per call); the page converts for imperial."""
    s = settings()
    if not s["enabled"]:
        return {"enabled": False}
    cur = _cached("weather_current", CURRENT_TTL, _fetch_current)
    fc = _cached("weather_forecast", FORECAST_TTL, _fetch_forecast)
    try:  # the next hours are a bonus: a key or plan without them still shows the rest
        hr = _cached("weather_hourly", HOURLY_TTL, _fetch_hourly)
    except WeatherError:
        hr = None
    return {"enabled": True, "location": s["locationName"], "units": s["units"],
            "current": cur["data"], "currentAt": cur["at"], "forecast": fc["data"], "forecastAt": fc["at"],
            "hourly": hr["data"]["hours"] if hr else [], "warnings": warnings(),
            "stale": bool(cur.get("stale") or fc.get("stale")), "error": cur.get("error") or fc.get("error")}
