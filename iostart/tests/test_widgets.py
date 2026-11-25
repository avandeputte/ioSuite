"""The weather (AccuWeather mocked: no network, no key spent) and the bookmarks."""
import json

from iostart import weather
from iosuite_shared import testing


def _fake_accuweather(calls):
    def get(path, **params):
        calls.append(path)
        if path.startswith("/locations/v1/cities/search"):
            return [{"Key": "349727", "LocalizedName": "New York", "AdministrativeArea": {"LocalizedName": "New York"}, "Country": {"LocalizedName": "United States"}}]
        if path.startswith("/currentconditions/v1/"):
            return [{"WeatherText": "Sunny", "WeatherIcon": 1, "IsDayTime": True, "RelativeHumidity": 40, "UVIndex": 3, "Link": "https://example.com",
                     "Temperature": {"Metric": {"Value": 20.0}, "Imperial": {"Value": 68.0}}, "RealFeelTemperature": {"Metric": {"Value": 21.0}, "Imperial": {"Value": 70.0}},
                     "Wind": {"Speed": {"Metric": {"Value": 10.0}, "Imperial": {"Value": 6.2}}}}]
        if path.startswith("/forecasts/v1/daily/5day/"):
            return {"Headline": {"Text": "Sunny week"}, "DailyForecasts": [
                {"Date": "2026-11-04T07:00:00-05:00", "Temperature": {"Minimum": {"Value": 10.0}, "Maximum": {"Value": 18.0}}, "Day": {"Icon": 2, "IconPhrase": "Mostly sunny", "PrecipitationProbability": 5},
                 "Sun": {"Rise": "2026-11-04T06:32:00-05:00", "Set": "2026-11-04T16:47:00-05:00"},
                 "AirAndPollen": [{"Name": "AirQuality", "Value": 41, "Category": "Good", "CategoryValue": 1, "Type": "Ozone"},
                                  {"Name": "Grass", "Value": 12, "Category": "Moderate", "CategoryValue": 2},
                                  {"Name": "Mold", "Value": 0, "Category": "Low", "CategoryValue": 1},
                                  {"Name": "Ragweed", "Value": 3, "Category": "Low", "CategoryValue": 1},
                                  {"Name": "Tree", "Value": 90, "Category": "High", "CategoryValue": 3},
                                  {"Name": "UVIndex", "Value": 3, "Category": "Moderate", "CategoryValue": 2}]}]}
        if path.startswith("/forecasts/v1/hourly/12hour/"):
            return [{"DateTime": "2026-11-04T15:00:00-05:00", "WeatherIcon": 12, "IconPhrase": "Showers", "Temperature": {"Value": 14.0},
                     "PrecipitationProbability": 70, "HasPrecipitation": True, "PrecipitationType": "Rain"}]
        if path == "/locations/v1/349727":
            return {"Key": "349727", "GeoPosition": {"Latitude": 40.713, "Longitude": -74.006}, "Country": {"ID": "US"}}
        raise AssertionError(path)
    return get


def _fake_nws(calls, features):
    def get(path, **params):
        calls.append((path, params))
        assert path == "/alerts/active" and params == {"point": "40.713,-74.006"}
        return {"features": features}
    return get


def _alert(event, severity, ends="2099-01-01T00:00:00-05:00", **more):
    return {"id": f"urn:{event}", "properties": {"id": f"urn:{event}", "event": event, "headline": f"{event} until tonight", "severity": severity,
                                                  "urgency": "Expected", "onset": "2026-11-04T12:00:00-05:00", "ends": ends, "description": "Snow.",
                                                  "instruction": "Stay off the roads.", "senderName": "NWS New York NY", "areaDesc": "Manhattan",
                                                  "status": "Actual", "messageType": "Alert", **more}}


def test_weather_off_until_set_up(client):
    assert client.get("/api/weather").json() == {"enabled": False}
    assert client.get("/api/weather/place").json() == {"name": "", "units": "metric"}
    s = client.get("/api/weather/settings").json()
    assert s["hasKey"] is False and s["enabled"] is False and s["units"] == "metric"


def test_weather_setup_and_cache(client, monkeypatch):
    calls = []
    monkeypatch.setattr(weather, "_get", _fake_accuweather(calls))
    r = client.get("/api/weather/search?q=New York&key=abc")
    assert r.status_code == 400  # a key given on the request is tried directly against AccuWeather (not mocked here): refused or unreachable
    assert client.post("/api/weather/settings", json={"key": "abc", "units": "imperial"}).json()["hasKey"] is True
    found = client.get("/api/weather/search?q=New York").json()["items"]
    assert found == [{"key": "349727", "name": "New York", "region": "New York", "country": "United States"}]
    s = client.post("/api/weather/settings", json={"locationKey": "349727", "locationName": "New York, United States"}).json()
    assert s["enabled"] and s["locationName"] == "New York, United States"
    n = len(calls)
    assert client.get("/api/weather/place").json() == {"name": "New York, United States", "units": "imperial"}
    assert len(calls) == n, "the place for the other apps never asks AccuWeather"
    w = client.get("/api/weather").json()
    assert w["enabled"] and w["units"] == "imperial" and w["current"]["text"] == "Sunny" and w["current"]["temp"] == {"metric": 20.0, "imperial": 68.0}
    assert w["forecast"]["days"][0] == {"date": "2026-11-04", "min": 10.0, "max": 18.0, "icon": 2, "text": "Mostly sunny", "rain": 5,
                                        "sunrise": "2026-11-04T06:32:00-05:00", "sunset": "2026-11-04T16:47:00-05:00",
                                        "air": {"value": 41, "category": "Good", "level": 1, "kind": "Ozone"},
                                        "pollen": [{"name": "Tree", "value": 90, "category": "High", "level": 3},
                                                   {"name": "Grass", "value": 12, "category": "Moderate", "level": 2},
                                                   {"name": "Ragweed", "value": 3, "category": "Low", "level": 1},
                                                   {"name": "Mold", "value": 0, "category": "Low", "level": 1}]}
    assert w["hourly"] == [{"t": "2026-11-04T15:00:00-05:00", "icon": 12, "text": "Showers", "temp": 14.0, "rain": 70, "wet": True, "kind": "Rain"}]
    n = len(calls)
    assert client.get("/api/weather").json()["current"]["text"] == "Sunny"
    assert len(calls) == n, "the second visit comes from the server's copy, not from AccuWeather"
    # a failing AccuWeather keeps the old reading, marked stale
    monkeypatch.setattr(weather, "_get", lambda *a, **k: (_ for _ in ()).throw(weather.WeatherError("down")))
    from iostart import db
    stale = json.loads(db.get_state("weather_current"))
    db.set_state("weather_current", json.dumps({**stale, "at": 0}))
    w = client.get("/api/weather").json()
    assert w["current"]["text"] == "Sunny" and w["stale"] and "down" in w["error"]
    # a viewer may read the weather, not the settings
    testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/weather").json()["enabled"]
    assert client.get("/api/weather/settings").status_code == 403


def test_weather_warnings(client, monkeypatch):
    """Warnings from the US weather service at the place's coordinates (asked of AccuWeather once per place), most
    serious first, kept 10 minutes; ended or test messages left out; none outside the United States."""
    from iostart import db
    calls, asked = [], []
    monkeypatch.setattr(weather, "_get", _fake_accuweather(calls))
    feats = [_alert("Wind Advisory", "Moderate"), _alert("Winter Storm Warning", "Severe"),
             _alert("Old Warning", "Severe", ends="2020-01-01T00:00:00-05:00"), _alert("Test Message", "Minor", status="Test")]
    monkeypatch.setattr(weather, "_nws", _fake_nws(asked, feats))
    client.post("/api/weather/settings", json={"key": "abc", "locationKey": "349727", "locationName": "New York"})
    w = client.get("/api/weather").json()["warnings"]
    assert [x["event"] for x in w["items"]] == ["Winter Storm Warning", "Wind Advisory"]
    assert w["items"][0] == {"id": "urn:Winter Storm Warning", "event": "Winter Storm Warning", "headline": "Winter Storm Warning until tonight",
                             "severity": "Severe", "urgency": "Expected", "starts": "2026-11-04T12:00:00-05:00", "ends": "2099-01-01T00:00:00-05:00",
                             "text": "Snow.", "instruction": "Stay off the roads.", "source": "NWS New York NY", "area": "Manhattan"}
    assert w["link"].startswith("https://forecast.weather.gov/MapClick.php?lat=40.713")
    client.get("/api/weather")
    assert calls.count("/locations/v1/349727") == 1 and len(asked) == 1, "the coordinates once, the warnings kept 10 minutes"
    # the weather service away: no warnings and a note, and not asked again on the next visit
    db.set_state("weather_warnings", None)
    monkeypatch.setattr(weather, "_nws", lambda *a, **k: (_ for _ in ()).throw(weather.WeatherError("The weather service answered 500")))
    w = client.get("/api/weather").json()
    assert w["current"]["text"] == "Sunny" and w["warnings"]["items"] == [] and "500" in w["warnings"]["error"]
    monkeypatch.setattr(weather, "_nws", _fake_nws(asked, feats))
    assert client.get("/api/weather").json()["warnings"]["items"] == [] and len(asked) == 1
    # another place, outside the United States: its coordinates asked anew, no warnings and why
    fake = _fake_accuweather(calls)
    monkeypatch.setattr(weather, "_get", lambda path, **k: {"GeoPosition": {"Latitude": 51.2, "Longitude": 4.4}, "Country": {"ID": "BE"}}
                        if path == "/locations/v1/27581" else fake(path, **k))
    client.post("/api/weather/settings", json={"locationKey": "27581", "locationName": "Antwerp"})
    w = client.get("/api/weather").json()["warnings"]
    assert w["items"] == [] and "United States" in w["none"] and len(asked) == 1


def test_bookmarks(client):
    assert client.get("/api/bookmarks").json() == {"groups": []}
    g = client.post("/api/bookmarks/groups", json={"name": "Developer"}).json()
    r = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Hacker News", "href": "news.ycombinator.com"})
    assert r.status_code == 200, r.text
    l1 = r.json()
    assert l1["abbr"] == "HN" and l1["href"] == "https://news.ycombinator.com" and l1["description"] == "news.ycombinator.com"
    l2 = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Github", "href": "https://github.com/", "abbr": "GH", "description": "Code"}).json()
    assert l2["abbr"] == "GH" and l2["description"] == "Code"
    assert client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Bad", "href": ""}).status_code == 400
    # order, rename, move between groups
    client.post(f"/api/bookmarks/groups/{g['id']}/order", json={"ids": [l2["id"], l1["id"]]})
    gs = client.get("/api/bookmarks").json()["groups"]
    assert [x["name"] for x in gs[0]["links"]] == ["Github", "Hacker News"]
    g2 = client.post("/api/bookmarks/groups", json={"name": "Social"}).json()
    client.post("/api/bookmarks/groups/order", json={"ids": [g2["id"], g["id"]]})
    assert client.patch(f"/api/bookmarks/links/{l1['id']}", json={"groupId": g2["id"], "name": "HN"}).json()["abbr"] == "HN"
    gs = client.get("/api/bookmarks").json()["groups"]
    assert [(x["name"], [y["name"] for y in x["links"]]) for x in gs] == [("Social", ["HN"]), ("Developer", ["Github"])]
    assert client.post("/api/bookmarks/import", json={"yaml": "- Only: []"}).status_code == 400  # a browser's file only
    for x in client.get("/api/bookmarks").json()["groups"][1:]:
        client.delete(f"/api/bookmarks/groups/{x['id']}")
    client.delete(f"/api/bookmarks/groups/{client.get('/api/bookmarks').json()['groups'][0]['id']}")
    assert client.get("/api/bookmarks").json() == {"groups": []}


def test_viewer_reads_bookmarks_editor_changes_them(client):
    testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"})
    testing.add_account(client, {"name": "sam", "password": "secret123", "role": "editor"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/bookmarks").status_code == 200
    assert client.post("/api/bookmarks/groups", json={"name": "X"}).status_code == 403
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "sam", "password": "secret123"})
    assert client.post("/api/bookmarks/groups", json={"name": "X"}).status_code == 200


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="#c33"/></svg>'


def test_uploaded_svg_icon(client):
    g = client.post("/api/bookmarks/groups", json={"name": "Dev"}).json()
    l = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Forge", "href": "https://forge.example", "icon": "github.png"}).json()
    assert l["iconUrl"] == ""
    r = client.put(f"/api/bookmarks/links/{l['id']}/icon", content=SVG, headers={"Content-Type": "image/svg+xml"})
    assert r.status_code == 200, r.text
    url = r.json()["iconUrl"]
    assert url.startswith(f"api/bookmarks/links/{l['id']}/icon.svg?v=") and r.json()["icon"] == "github.png"
    got = client.get("/" + url)
    assert got.status_code == 200 and got.headers["content-type"].startswith("image/svg+xml") and got.content == SVG
    assert "immutable" in got.headers["cache-control"]
    assert client.get("/api/bookmarks").json()["groups"][0]["links"][0]["iconUrl"] == url
    # replacing changes the address; the list follows
    r2 = client.put(f"/api/bookmarks/links/{l['id']}/icon", content=SVG.replace(b"#c33", b"#3c3"))
    assert r2.json()["iconUrl"] != url
    # what is refused
    for bad, why in [(b"<svg onload='alert(1)'/>", "handler"), (b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", "script"),
                     (b"<html/>", "root"), (b"not xml <", "parse"), (b"", "empty"), (b"<svg/>" + b" " * (256 * 1024), "size")]:
        assert client.put(f"/api/bookmarks/links/{l['id']}/icon", content=bad).status_code == 400, why
    assert client.put("/api/bookmarks/links/9999/icon", content=SVG).status_code == 404
    # a PNG is taken too, and served inside an SVG of its size
    import base64 as b64
    png = b64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAYAAAC56t6BAAAAEUlEQVR4nGM4ISf3H4QZMBgAoR8ME4Q16BEAAAAASUVORK5CYII=")
    rp = client.put(f"/api/bookmarks/links/{l['id']}/icon", content=png, headers={"Content-Type": "image/png"})
    assert rp.status_code == 200 and rp.json()["iconUrl"] not in ("", r2.json()["iconUrl"])
    got = client.get("/" + rp.json()["iconUrl"])
    assert got.headers["content-type"].startswith("image/svg+xml") and 'viewBox="0 0 2 3"' in got.text
    assert b64.b64encode(png).decode() in got.text and "img-src data:" in got.headers["content-security-policy"]
    for bad, why in ((png[:30], "cut short"), (b"\x89PNG\r\n\x1a\n" + b"x" * 300 * 1024, "too large"), (b"GIF89a" + b"0" * 50, "another kind")):
        assert client.put(f"/api/bookmarks/links/{l['id']}/icon", content=bad).status_code == 400, why
    assert client.delete(f"/api/bookmarks/links/{l['id']}/icon").json()["iconUrl"] == ""
    assert client.get(f"/api/bookmarks/links/{l['id']}/icon.svg").status_code == 404
    client.put(f"/api/bookmarks/links/{l['id']}/icon", content=SVG)
    client.delete(f"/api/bookmarks/links/{l['id']}")
    from iostart import db
    assert db.q("SELECT * FROM prt_bookmark_node_icons") == []
    # a viewer sees the icon of a shared link but cannot change it
    client.patch(f"/api/bookmarks/groups/{g['id']}", json={"shared": True})
    l2 = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Wiki", "href": "https://wiki.example"}).json()
    assert l2["shared"] is True
    client.put(f"/api/bookmarks/links/{l2['id']}/icon", content=SVG)
    testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get(f"/api/bookmarks/links/{l2['id']}/icon.svg").status_code == 200
    assert client.put(f"/api/bookmarks/links/{l2['id']}/icon", content=SVG).status_code == 403


def test_weather_without_hourly(client, monkeypatch):
    """A key or plan without the hourly forecast still shows the conditions and the days ahead."""
    fake = _fake_accuweather([])

    def get(path, **params):
        if "hourly" in path:
            raise weather.WeatherError("AccuWeather answered 403")
        return fake(path, **params)
    monkeypatch.setattr(weather, "_get", get)
    client.post("/api/weather/settings", json={"key": "abc", "locationKey": "349727", "locationName": "New York"})
    w = client.get("/api/weather").json()
    assert w["current"]["text"] == "Sunny" and w["hourly"] == [] and not w["stale"]
