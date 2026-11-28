"""Each person's own start page: which tiles and cards they see, in what order and at what size, how the apps are laid
out, what the Today card holds, the top row, the colour and the size of the type, how the bookmarks look, and which
photo strip. Further: a grid the person lays out block by block (style "grid": sections of blocks, each with a width
and a height), badges under the greeting, a rule for when a thing shows (the screen, the hour, the day, whether it has
anything to say, a Home Assistant state), and more pages than one, each laid out by itself.

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
STYLES = ("cards", "today", "grid")  # how the apps are laid out: a card per app, one Today card under a row of the apps, or the person's own grid of blocks (null: cards)
WALL_PHOTOS = re.compile(r"rediscover|onthisday|favorites|album:[1-9][0-9]{0,12}")  # which ioPix photos (null: as the strip)
SIZES = ("card", "tile")  # an app in the cards layout: always a full card, always a low tile with one line (not named: by itself)
TODAY_PARTS = ("events", "tasks", "birthdays", "bills", "health", "photos")  # what the Today layout shows, each one to switch off
TODAY_DAYS = (0, 1, 2, 3)  # how many of the coming days the Today card lists under today (null: the week)
WEATHER_PARTS = ("warnings", "sun", "air", "pollen")  # the weather's extras, each one to switch off: severe weather warnings, sunrise and sunset, air quality, pollen
UNITS = ("metric", "imperial")  # the weather's, for this person (null: as the admin set them)
ACCENTS = ("blue", "teal", "green", "amber", "red", "pink", "purple", "graphite")  # the page's colour (null: the suite's night blue)
TEXTS = ("compact", "large")  # the size of the type (null: as it comes)
BOOKMARKS = ("icons", "folded")  # the bookmarks on the page: icons only, or folders shut until tapped (null: the full list)
# ---- the grid (style "grid"): sections one under the other, each a heading (or none) over its blocks. A block is one
# thing on the page, as wide as `w` columns and as tall as `h` rows; the same kind can stand there more than once, each
# with what it shows: {id, kind, w, h, when, and what its kind takes}.
BLOCKS = {  # kind: what a block of it takes besides
    "app": ("app",),             # one app's card (app: its key)
    "apps": ("apps", "look"),    # apps to open: all on the page, or the ones named (apps); look: dock | list
    "today": (),                 # the Today card, with what stands beside it (todayOff, todayDays)
    "home": ("title", "entities"),   # Home Assistant: every chosen entity, or the ones named (a room)
    "birthdays": (),
    "week": ("who",),            # the coming days, the family's or one member's (who: their id in the family list)
    "strip": ("strip",),         # a row of photos: rediscover | onthisday (null: as the page's)
    "news": ("folder",),         # headlines, of every feed on the page or of one folder
    "bookmarks": ("group", "look"),  # the bookmarks, or one group of them (group: its id)
}
WIDTHS = (1, 2, 3, 4)   # columns a block takes (null: 1); never more than the screen has, so 4 is the full width
HEIGHTS = (1, 2, 3)     # rows it takes, and no taller than that (what does not fit scrolls); null: one row, as tall as what it shows
GRID_COLS = (2, 3, 4)   # no more than this many across (null: 3)
APPS_LOOKS = ("dock", "list")  # a block of apps: icons in a row, or one under the other with a line each (null: dock)
SCREENS = ("phone", "tablet", "wide")  # a rule's screens: narrower than 640px, up to 1100px, wider
SECTIONS_MOST, BLOCKS_MOST, BADGES_MOST, PAGES_MOST = 12, 60, 12, 8
ID = re.compile(r"[a-z0-9]{4,12}")  # a block's, a section's, a badge's or a page's id, as the browser made it up
ENTITY = re.compile(r"[a-z_0-9]{1,40}\.[a-z0-9_]{1,80}")  # a Home Assistant entity
HHMM = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")
SIZE_MOST = 200_000  # a setup, written down
# what a page holds by itself; the rest (the colour, the units, the photo strip, the wall display…) is the person's
PAGE = ("hidden", "order", "cards", "style", "sizes", "todayOff", "todayDays", "bookmarks", "grid", "whens", "badges")
EMPTY = {"hidden": [], "order": [], "cards": [], "strip": None, "search": None, "stripMove": None, "stripEvery": None,
         "wallBg": None, "wallEvery": None, "wallPhotos": None, "style": None, "sizes": {}, "todayOff": [], "todayDays": None, "weatherOff": [],
         "units": None, "accent": None, "text": None, "bookmarks": None, "grid": None, "whens": {}, "badges": [], "name": None, "pages": []}
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


def _text(name: str, most: int):
    """A few words (a page's name, a section's heading), or nothing."""
    def check(v, strict):
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            if strict:
                raise Invalid(f"{name}: a few words")
            return None
        return re.sub(r"\s+", " ", v).strip()[:most] or None
    return check


def _when(v, strict, name: str = "when"):
    """When a thing shows; every part it names must hold. {screen: [phone|tablet|wide], from: "HH:MM", to: "HH:MM" (past
    midnight when `to` is the earlier), days: [0-6, Sunday 0], content: true (only while it has something to say),
    ha: {id: a Home Assistant entity, state: what it must say (null: on), not: true (anything but that)}}. A part that
    rules nothing out (every screen, every day) is left out; nothing left: None (always)."""
    if v is None or v == "" or v == {}:
        return None

    def bad(what):
        if strict:
            raise Invalid(f"{name}: {what}")

    if not isinstance(v, dict):
        return bad("an object: screen, from and to, days, content, ha")
    out = {}
    if strict and (extra := set(v) - {"screen", "from", "to", "days", "content", "ha"}):
        raise Invalid(f"{name}: {', '.join(sorted(map(str, extra)))} is not a part of a rule (screen, from, to, days, content, ha)")
    sc = v.get("screen")
    if sc:
        if isinstance(sc, list) and all(x in SCREENS for x in sc):
            keep = [x for x in SCREENS if x in sc]
            if len(keep) < len(SCREENS):
                out["screen"] = keep
        else:
            bad(f"screen: a list of {', '.join(SCREENS)}")
    a, b = v.get("from"), v.get("to")
    if a or b:
        if isinstance(a, str) and isinstance(b, str) and HHMM.fullmatch(a) and HHMM.fullmatch(b) and a != b:
            out["from"], out["to"] = a, b
        else:
            bad("from and to: two different times of the day, as HH:MM")
    days = v.get("days")
    if days:
        if isinstance(days, list) and all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days):
            keep = sorted(set(days))
            if len(keep) < 7:
                out["days"] = keep
        else:
            bad("days: a list of 0 (Sunday) to 6 (Saturday)")
    if v.get("content"):
        out["content"] = True
    ha = v.get("ha")
    if ha:
        if isinstance(ha, dict) and isinstance(ha.get("id"), str) and ENTITY.fullmatch(ha["id"]) and isinstance(ha.get("state") or "", str):
            out["ha"] = {"id": ha["id"], "state": (ha.get("state") or "").strip()[:40] or "on", **({"not": True} if ha.get("not") else {})}
        else:
            bad("ha: {id: a Home Assistant entity, state: what it says}")
    return out or None


def _whens(v, strict):
    """A rule for a tile, a card or a part of the top row, in the layouts the page draws by itself: {key: when}."""
    v = {} if v is None else v
    if not isinstance(v, dict) or not all(_hideable(k) for k in v):
        if strict:
            raise Invalid(f"whens: a rule each for app keys, {', '.join(SECTIONS)} and {', '.join(TOP)}")
        v = {k: w for k, w in v.items() if _hideable(k)} if isinstance(v, dict) else {}
    out = {k: _when(w, strict, f"whens.{k}") for k, w in v.items()}
    return {k: w for k, w in out.items() if w}


def _id(v, seen: set, strict: bool, what: str):
    """An id no other thing of the page has, or None (strict: an Invalid)."""
    if isinstance(v, str) and ID.fullmatch(v) and v not in seen:
        seen.add(v)
        return v
    if strict:
        raise Invalid(f"{what}: an id of 4 to 12 small letters and digits, each once")
    return None


def _block(b, seen: set, strict: bool):
    """One block of the grid, checked; None when it cannot be kept."""
    def bad(what):
        if strict:
            raise Invalid(f"A block: {what}")

    if not isinstance(b, dict) or b.get("kind") not in BLOCKS:
        return bad(f"kind: {', '.join(BLOCKS)}")
    kind, takes = b["kind"], BLOCKS[b["kind"]]
    if strict and (extra := set(b) - {"id", "kind", "w", "h", "when", *takes}):
        raise Invalid(f"A {kind} block takes no {', '.join(sorted(map(str, extra)))}")
    bid = _id(b.get("id"), seen, strict, "A block")
    if not bid:
        return None
    out = {"id": bid, "kind": kind}
    if (w := _one_of("w", WIDTHS, "")(b.get("w"), strict)) and w != 1:
        out["w"] = w
    if h := _one_of("h", HEIGHTS, "")(b.get("h"), strict):
        out["h"] = h
    if rule := _when(b.get("when"), strict):
        out["when"] = rule
    if kind == "app":
        if not apps.is_key(b.get("app")):
            return bad("app: the key of the app whose card it is")
        out["app"] = b["app"]
    if "apps" in takes and b.get("apps") is not None:
        keys = b["apps"]
        if not isinstance(keys, list) or not all(apps.is_key(k) for k in keys):
            bad("apps: a list of app keys")
            keys = [k for k in keys if apps.is_key(k)] if isinstance(keys, list) else []
        out["apps"] = list(dict.fromkeys(keys))[:40]
    if "look" in takes and (x := _one_of("look", APPS_LOOKS if kind == "apps" else BOOKMARKS, "")(b.get("look"), strict)):
        out["look"] = x
    if "title" in takes and (x := _text("title", 40)(b.get("title"), strict)):
        out["title"] = x
    if "entities" in takes and b.get("entities") is not None:
        ids = b["entities"]
        if not isinstance(ids, list) or not all(isinstance(e, str) and ENTITY.fullmatch(e) for e in ids):
            bad("entities: a list of Home Assistant entities")
            ids = [e for e in ids if isinstance(e, str) and ENTITY.fullmatch(e)] if isinstance(ids, list) else []
        out["entities"] = list(dict.fromkeys(ids))[:60]
    if "who" in takes and b.get("who") is not None:
        who = b["who"]
        if isinstance(who, int) and not isinstance(who, bool) and 0 < who < 10 ** 9:
            out["who"] = who
        else:
            bad("who: a member of the family, by id")
    if "strip" in takes and (x := _one_of("strip", ("rediscover", "onthisday"), "")(b.get("strip"), strict)):
        out["strip"] = x
    if "folder" in takes and (x := _text("folder", 60)(b.get("folder"), strict)):
        out["folder"] = x
    if "group" in takes and b.get("group") not in (None, ""):
        g = b["group"]
        if isinstance(g, (str, int)) and not isinstance(g, bool) and re.fullmatch(r"[A-Za-z0-9_-]{1,40}", str(g)):
            out["group"] = str(g)
        else:
            bad("group: the id of a group of bookmarks")
    return out


def _grid(v, strict):
    """The person's own grid: {cols: 2-4 | null, sections: [{id, title, when, blocks: [block]}]}; None: not laid out
    yet (the page makes one from what the person had)."""
    if v is None or v == "" or v == {}:
        return None
    if not isinstance(v, dict) or not isinstance(v.get("sections") or [], list):
        if strict:
            raise Invalid("grid: {cols, sections: [{id, title, blocks}]}")
        return None
    seen, sections, n = set(), [], 0
    for sec in v.get("sections") or []:
        if not isinstance(sec, dict) or not isinstance(sec.get("blocks") or [], list):
            if strict:
                raise Invalid("A section: {id, title, blocks: [...]}")
            continue
        sid = _id(sec.get("id"), seen, strict, "A section")
        if not sid:
            continue
        blocks = [x for x in (_block(b, seen, strict) for b in sec.get("blocks") or []) if x]
        n += len(blocks)
        sections.append({"id": sid, "title": _text("title", 40)(sec.get("title"), strict), "blocks": blocks,
                         **({"when": w} if (w := _when(sec.get("when"), strict)) else {})})
    if len(sections) > SECTIONS_MOST or n > BLOCKS_MOST:
        if strict:
            raise Invalid(f"A page holds {SECTIONS_MOST} sections and {BLOCKS_MOST} blocks at most")
        sections = sections[:SECTIONS_MOST]
    return {"cols": _one_of("cols", GRID_COLS, " across, or nothing (3)")(v.get("cols"), strict), "sections": sections}


def _badges(v, strict):
    """The small chips under the greeting, a fact each: [{id, app: an app key} | {id, entity: a Home Assistant entity},
    each with an optional `when`]."""
    v = [] if v is None else v
    if not isinstance(v, list) or len(v) > BADGES_MOST:
        if strict:
            raise Invalid(f"badges: a list of {BADGES_MOST} at most")
        v = v[:BADGES_MOST] if isinstance(v, list) else []
    seen, out = set(), []
    for b in v:
        app, entity = (b.get("app"), b.get("entity")) if isinstance(b, dict) else (None, None)
        ok = isinstance(b, dict) and (apps.is_key(app) if app else isinstance(entity, str) and bool(ENTITY.fullmatch(entity)))
        if not ok or (app and entity):
            if strict:
                raise Invalid("A badge: {id, app: an app key} or {id, entity: a Home Assistant entity}")
            continue
        bid = _id(b.get("id"), seen, strict, "A badge")
        if bid:
            out.append({"id": bid, **({"app": app} if app else {"entity": entity}), **({"when": w} if (w := _when(b.get("when"), strict)) else {})})
    return out


def _pages(v, strict):
    """The pages after the first: [{id, name, when, and what a page holds (PAGE)}]."""
    v = [] if v is None else v
    if not isinstance(v, list) or len(v) > PAGES_MOST - 1 or not all(isinstance(p, dict) for p in v):
        if strict:
            raise Invalid(f"pages: a list of {PAGES_MOST - 1} at most after the first")
        v = [p for p in v if isinstance(p, dict)][:PAGES_MOST - 1] if isinstance(v, list) else []
    seen, out = set(), []
    for p in v:
        if strict and (extra := set(p) - {"id", "name", "when", *PAGE}):
            raise Invalid(f"A page holds no {', '.join(sorted(map(str, extra)))}: that is set once, for every page")
        pid = _id(p.get("id"), seen, strict, "A page")
        if not pid:
            continue
        out.append({"id": pid, "name": _text("name", 30)(p.get("name"), strict) or "Page", **({"when": w} if (w := _when(p.get("when"), strict)) else {}),
                    **{k: FIELDS[k](p.get(k), strict) for k in PAGE}})
    return out


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
    "weatherOff": _keys("weatherOff", lambda k: isinstance(k, str) and k in WEATHER_PARTS, f"a list of {', '.join(WEATHER_PARTS)}", once=False),
    "units": _one_of("units", UNITS, ", or nothing (as the weather is set up)"),
    "accent": _one_of("accent", ACCENTS, ", or nothing (the suite's blue)"),
    "text": _one_of("text", TEXTS, ", or nothing (the usual size)"),
    "bookmarks": _one_of("bookmarks", BOOKMARKS, ", or nothing (the full list)"),
    "grid": _grid,
    "whens": _whens,
    "badges": _badges,
    "name": _text("name", 30),
    "pages": _pages,
}


def clean(body, strict: bool = True) -> dict:
    """A layout with every key, each value checked. strict: what a person sends (a wrong value is an Invalid); not
    strict: what was kept (a value no longer known, an app key no longer written that way, is left out)."""
    if not isinstance(body, dict):
        if strict:
            raise Invalid("An object, please")
        return _empty()
    if strict and (extra := set(body) - set(FIELDS)):
        raise Invalid(f"A setup has no {', '.join(sorted(map(str, extra)))}. It has: {', '.join(FIELDS)}")
    out = {k: check(body.get(k), strict) for k, check in FIELDS.items()}
    if strict and len(json.dumps(out)) > SIZE_MOST:
        raise Invalid("That setup is too large to keep")
    return out


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
    weatherOff: [warnings|sun|air|pollen], units: metric|imperial|null, accent: a colour (ACCENTS) | null, text: compact|large|null, bookmarks: icons|folded|null,
    grid: {cols, sections: [{id, title, when, blocks}]} | null, whens: {key: when}, badges: [{id, app | entity, when}],
    name: the first page's | null, pages: [{id, name, when, and a page's own hidden, order, cards, style, sizes, todayOff,
    todayDays, bookmarks, grid, whens, badges}]}:
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


def of_device(user_id: int, device: str) -> dict | None:
    """The setup one of the person's devices keeps for itself, or None."""
    v = _read(_key(user_id, device)) if device_ok(device) else None
    return clean(v["layout"], strict=False) if v and isinstance(v.get("layout"), dict) else None


def of_account(user_id: int) -> dict | None:
    """The setup of the person's account (not a device's, not the family's), or None."""
    v = _read(_key(user_id))
    return clean(v, strict=False) if v else None


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
