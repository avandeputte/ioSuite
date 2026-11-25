"""Each person's own start page: which tiles and cards they see, in what order and at what size, how the apps are laid
out, what the Today card holds, the top row, the colour and the size of the type, how the bookmarks look, and which
photo strip.

Three places a setup comes from, the nearest first:
- a device's own ("user:<id>:layout:<device>", {name, layout}): the phone, the kitchen tablet. The browser makes up
  the device's id and keeps it; the person names it.
- the account's ("user:<id>:layout"), on every device without one of its own.
- the family's ("layout:default"), which an admin sets as everyone's starting point, for whoever has none of their own.
All in the prt_state table, as JSON. Every app registered in the suite's list is on the page unless the person hides
it; the photo strip is the admin's choice (Settings › Home page) unless they pick another. Empty: the page as it comes."""
import json
import re

from iostart import apps, db
from iosuite_shared.errors import Invalid

SECTIONS = ("home", "birthdays", "week", "strip", "news", "bookmarks")  # the cards under the tiles, hideable like a tile (home: Home Assistant; news: the headlines of the feeds the person follows)
TOP = ("greeting", "search", "weather")  # the parts of the top row, hideable too (the date and the gear always stay)
ENGINES = ("duckduckgo", "google", "bing", "startpage", "ecosia", "kagi")  # the search box's web search (null: DuckDuckGo)
STRIP_MOVES = ("shuffle", "page", "off")  # how the photo strip changes by itself (null: shuffle)
STRIP_EVERY = (30, 60, 120, 300, 600, 1800)  # how often, in seconds (null: 60)
WALL_BGS = ("photos", "sky", "black")  # behind the wall display (null: photos, or the sky without ioPix)
WALL_EVERY = (20, 60, 300, 900)  # how often its photo changes, in seconds (null: 60)
STYLES = ("cards", "today")  # how the apps are laid out: a card per app, or one Today card under a row of the apps (null: cards)
WALL_PHOTOS = re.compile(r"rediscover|onthisday|favorites|album:[1-9][0-9]{0,12}")  # which ioPix photos (null: as the strip)
SIZES = ("card", "tile")  # an app in the cards layout: always a full card, always a low tile with one line (not named: by itself)
TODAY_PARTS = ("events", "tasks", "birthdays", "bills", "health", "photos")  # what the Today layout shows, each one to switch off
TODAY_DAYS = (0, 1, 2, 3)  # how many of the coming days the Today card lists under today (null: the week)
UNITS = ("metric", "imperial")  # the weather's, for this person (null: as the admin set them)
ACCENTS = ("blue", "teal", "green", "amber", "red", "pink", "purple", "graphite")  # the page's colour (null: the suite's night blue)
TEXTS = ("compact", "large")  # the size of the type (null: as it comes)
BOOKMARKS = ("icons", "folded")  # the bookmarks on the page: icons only, or folders shut until tapped (null: the full list)
EMPTY = {"hidden": [], "order": [], "cards": [], "strip": None, "search": None, "stripMove": None, "stripEvery": None,
         "wallBg": None, "wallEvery": None, "wallPhotos": None, "style": None, "sizes": {}, "todayOff": [], "todayDays": None,
         "units": None, "accent": None, "text": None, "bookmarks": None}
DEVICE = re.compile(r"[A-Za-z0-9]{8,32}")  # a device's id, as the browser made it up
DEVICES_MOST = 12  # a person's devices with a setup of their own
FAMILY = "layout:default"


def _key(user_id: int, device: str | None = None) -> str:
    return f"user:{int(user_id)}:layout" + (f":{device}" if device else "")


def _hideable(k) -> bool:
    return isinstance(k, str) and (apps.is_key(k) or k in SECTIONS or k in TOP)


def _one_of(name: str, allowed, what: str):
    """A choice from a short list; nothing (null, "", 0 where 0 is no choice) means the usual."""
    def check(v, strict):
        if v is None or v == "":
            return None
        if isinstance(v, bool) or v not in allowed:
            if strict:
                raise Invalid(f"{name}: {', '.join(map(str, allowed))}{what}")
            return None
        return v
    return check


def _keys(name: str, ok, what: str, once: bool):
    def check(v, strict):
        v = v or []
        if not isinstance(v, list) or not all(ok(k) for k in v) or (once and len(set(v)) != len(v)):
            if strict:
                raise Invalid(f"{name}: {what}")
            return list(dict.fromkeys(k for k in v if ok(k))) if isinstance(v, list) else []
        return list(dict.fromkeys(v))
    return check


def _sizes(v, strict):
    v = v or {}
    ok = isinstance(v, dict) and all(apps.is_key(k) and s in SIZES for k, s in v.items())
    if not ok:
        if strict:
            raise Invalid(f"sizes: an app key each, with {' or '.join(SIZES)}")
        return {k: s for k, s in v.items() if apps.is_key(k) and s in SIZES} if isinstance(v, dict) else {}
    return dict(v)


def _wall_photos(v, strict):
    if v is None or v == "":
        return None
    if not (isinstance(v, str) and WALL_PHOTOS.fullmatch(v)):
        if strict:
            raise Invalid("wallPhotos: rediscover, onthisday, favorites, album:<id>, or nothing (as the photo strip)")
        return None
    return v


def _today_days(v, strict):
    if v is None or v == "":
        return None
    if isinstance(v, bool) or v not in TODAY_DAYS:
        if strict:
            raise Invalid(f"todayDays: {', '.join(map(str, TODAY_DAYS))} days after today, or nothing (the week)")
        return None
    return v


# each key of a layout: how it is checked (strict: a wrong value is an error; else it is left out)
FIELDS = {
    "hidden": _keys("hidden", _hideable, f"a list of app keys, {', '.join(SECTIONS)} and {', '.join(TOP)}", once=False),
    "order": _keys("order", lambda k: isinstance(k, str) and apps.is_key(k), "a list of app keys, each once", once=True),
    "cards": _keys("cards", lambda k: isinstance(k, str) and k in SECTIONS, f"a list of {', '.join(SECTIONS)}, each once", once=True),
    "strip": lambda v, strict: _one_of("strip", apps.STRIPS, ", or nothing (the admin's choice)")(v, strict),
    "search": _one_of("search", ENGINES, ", or nothing (DuckDuckGo)"),
    "stripMove": _one_of("stripMove", STRIP_MOVES, ", or nothing (shuffle)"),
    "stripEvery": _one_of("stripEvery", STRIP_EVERY, " seconds, or nothing (60)"),
    "wallBg": _one_of("wallBg", WALL_BGS, ", or nothing (photos)"),
    "wallEvery": _one_of("wallEvery", WALL_EVERY, " seconds, or nothing (60)"),
    "wallPhotos": _wall_photos,
    "style": _one_of("style", STYLES, ", or nothing (cards)"),
    "sizes": _sizes,
    "todayOff": _keys("todayOff", lambda k: isinstance(k, str) and k in TODAY_PARTS, f"a list of {', '.join(TODAY_PARTS)}", once=False),
    "todayDays": _today_days,
    "units": _one_of("units", UNITS, ", or nothing (as the weather is set up)"),
    "accent": _one_of("accent", ACCENTS, ", or nothing (the suite's blue)"),
    "text": _one_of("text", TEXTS, ", or nothing (the usual size)"),
    "bookmarks": _one_of("bookmarks", BOOKMARKS, ", or nothing (the full list)"),
}


def clean(body, strict: bool = True) -> dict:
    """A layout with every key, each value checked. strict: what a person sends (a wrong value is an Invalid); not
    strict: what was kept (a value no longer known, an app key no longer written that way, is left out)."""
    if not isinstance(body, dict):
        if strict:
            raise Invalid("An object, please")
        return _empty()
    return {k: check(body.get(k), strict) for k, check in FIELDS.items()}


def _empty() -> dict:
    return {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for k, v in EMPTY.items()}


def _read(key: str):
    """The JSON kept under a settings key, or None."""
    raw = db.get_state(key)
    if not raw:
        return None
    try:
        v = json.loads(raw)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def device_ok(device) -> bool:
    return isinstance(device, str) and bool(DEVICE.fullmatch(device))


def family() -> dict | None:
    """The setup an admin made everyone's starting point, or None."""
    v = _read(FAMILY)
    return clean(v, strict=False) if v else None


def set_family(body: dict | None) -> dict | None:
    """Admins: this setup for whoever has none of their own; nothing (or an empty one) takes it away again."""
    v = clean(body or {})
    db.set_state(FAMILY, None if v == EMPTY else json.dumps(v))
    return family()


def devices(user_id: int) -> list:
    """The person's devices that have a setup of their own: [{id, name}], by name."""
    prefix = _key(user_id) + ":"
    out = []
    for r in db.q("SELECT name, value FROM prt_state WHERE name LIKE %s", (prefix + "%",)):
        dev = r["name"][len(prefix):]
        try:
            v = json.loads(r["value"])
        except ValueError:
            continue
        if device_ok(dev) and isinstance(v, dict):
            out.append({"id": dev, "name": str(v.get("name") or "A device")})
    return sorted(out, key=lambda d: (d["name"].lower(), d["id"]))


def has_own(user_id: int) -> bool:
    return _read(_key(user_id)) is not None


def where(user_id: int, device: str | None = None) -> dict:
    """The setup this person's page is drawn from, and where it comes from:
    {layout, scope: device | account | family | none, device: {id, name} | None}."""
    if device_ok(device):
        v = _read(_key(user_id, device))
        if v and isinstance(v.get("layout"), dict):
            return {"layout": clean(v["layout"], strict=False), "scope": "device", "device": {"id": device, "name": str(v.get("name") or "This device")}}
    v = _read(_key(user_id))
    if v:
        return {"layout": clean(v, strict=False), "scope": "account", "device": None}
    fam = family()
    return {"layout": fam or _empty(), "scope": "family" if fam else "none", "device": None}


def get(user_id: int, device: str | None = None) -> dict:
    """{hidden: [tile, card or top row keys], order: [tile keys, the first ones first], cards: [section keys, top first],
    strip: rediscover|onthisday|off|null, search: a web search engine (ENGINES) | null,
    stripMove: shuffle|page|off|null, stripEvery: seconds (STRIP_EVERY) | null,
    wallBg: photos|sky|black|null, wallEvery: seconds (WALL_EVERY) | null,
    wallPhotos: rediscover|onthisday|favorites|album:<ioPix album id>|null, style: cards|today|null,
    sizes: {app key: card|tile}, todayOff: [events|tasks|birthdays|bills|health|photos], todayDays: 0-3|null,
    units: metric|imperial|null, accent: a colour (ACCENTS) | null, text: compact|large|null, bookmarks: icons|folded|null}:
    the device's own when it has one, else the account's, else the family's starting point."""
    return where(user_id, device)["layout"]


def device_name(name) -> str:
    return re.sub(r"\s+", " ", str(name or "")).strip()[:40] or "This device"


def save(user_id: int, body: dict, device: str | None = None, name: str | None = None) -> dict:
    """Checks and keeps the layout: the account's, or with a device this device's own. For the account, {} (or
    everything empty) puts the page back as it comes (the family's starting point, when there is one)."""
    v = clean(body)
    if device is not None:
        if not device_ok(device):
            raise Invalid("device: 8 to 32 letters and digits")
        if not _read(_key(user_id, device)) and len(devices(user_id)) >= DEVICES_MOST:
            raise Invalid(f"{DEVICES_MOST} devices have a setup of their own already: remove one first")
        db.set_state(_key(user_id, device), json.dumps({"name": device_name(name), "layout": v}))
        return get(user_id, device)
    db.set_state(_key(user_id), None if v == EMPTY else json.dumps(v))
    return get(user_id)


def forget_device(user_id: int, device: str) -> None:
    """The device goes back to the account's setup."""
    if device_ok(device):
        db.set_state(_key(user_id, device), None)


def give(user_id: int, body: dict) -> dict:
    """Admins: this setup as that person's, on every device (the ones their devices kept are removed)."""
    v = clean(body)
    with db.tx():
        db.ex("DELETE FROM prt_state WHERE name LIKE %s", (_key(user_id) + ":%",))
        db.set_state(_key(user_id), None if v == EMPTY else json.dumps(v))
    return get(user_id)
