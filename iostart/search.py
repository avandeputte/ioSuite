"""One search across the apps: the search box asks the start page once, and the start page asks every app that has a
search at the same time and ranks what they found together.

Each app is asked at its standard endpoint (/api/suite/search, iosuite_shared.suiteitems) on the viewer's behalf,
through widgets.fetch and so iosuite_shared.links.as_viewer: an app that runs in this copy of the program is handed the
request in this process (iosuite_shared.inside), one that runs in another copy, or on another server, is asked over
the network as before. Both answer with what that person may see there and nothing more: nothing here decides what
someone may see, and nothing is kept.

All of them are asked at once. Those that answered within DEADLINE seconds are ranked together; the ones that had not
are named in `late`, and the page asks each of those on its own (/api/widgets/<app>?q=, whose items are scored the
same way) and puts them in where they belong when they come. So one slow app holds up nobody.

The ranking (score()) is the same for every app, so a contact called "Ann" beats a note that mentions Ann in passing,
whichever app answered first: how well the title matches what was typed, then the app's own order (each app puts its
best first), then whether it is soon (an event or a task of the coming days), then the app's place in the search box
(app.json "start": find.rank) to settle the rest. Finished tasks and events that are over are left out, as they always
were in the search box: the app's own search has them.
"""
import concurrent.futures as cf
import datetime as dt
import re
import unicodedata

from iosuite_shared import catalog

from iostart import apps, widgets

DEADLINE = 2.5   # seconds the combined answer waits for the apps; a later one is asked again on its own by the page
PER_APP = 5      # what each app is asked for
_pool = cf.ThreadPoolExecutor(max_workers=16, thread_name_prefix="search")
_FOLD = {"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ı": "i"}
_WORD = re.compile(r"[^\W_]+")


def fold(s) -> str:
    """Lower case without accents ("Café Ørsted" → "cafe orsted"), as the page folds what it compares."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return "".join(_FOLD.get(c, c) for c in s)


def finders(user, only: list[str] | None = None) -> list[str]:
    """The apps this person may use that have a search, in the search box's order; only: of these (the page leaves out
    the apps the person hid)."""
    keys = [t["key"] for t in apps.tiles(user) if (t.get("start") or {}).get("find")]
    keys.sort(key=lambda k: _rank(k))
    return [k for k in keys if only is None or k in only]


def _rank(key: str) -> int:
    return int((((catalog.APPS.get(key) or {}).get("start") or {}).get("find") or {}).get("rank") or 100)


def _soon(when, today: dt.date) -> float:
    """A little more for what is coming in the next days (an event, a task's due date)."""
    if not isinstance(when, str) or len(when) < 10:
        return 0.0
    try:
        d = dt.date.fromisoformat(when[:10])
    except ValueError:
        return 0.0
    days = (d - today).days
    return 6.0 if 0 <= days <= 2 else 3.0 if 0 <= days <= 14 else 0.0


def score(q: str, item: dict, key: str, position: int, today: dt.date | None = None) -> float:
    """How well the item answers q, the same measure for every app (see above). Higher is better."""
    ql, title, text = fold(q).strip(), fold(item.get("title")), fold(item.get("text"))
    words = _WORD.findall(ql)
    tw = _WORD.findall(title)
    if title == ql:
        s = 100
    elif title.startswith(ql):
        s = 80
    elif words and all(any(t.startswith(w) for t in tw) for w in words):
        s = 65   # every word typed starts a word of the title: "ann sm" finds "Ann Smith"
    elif ql and ql in title:
        s = 50
    elif words and all(w in title for w in words):
        s = 40
    elif ql and (ql in text or (words and all(w in text for w in words))):
        s = 25
    else:
        s = 15   # the app found it in what it does not show here (a note's body, a photo's place)
    return round(s - 2 * position + _soon(item.get("when"), today or dt.date.today()) - _rank(key) / 25, 2)


def ranked(q: str, key: str, got) -> dict:
    """An app's answer ({items, more}) with each item marked with its app and score, finished ones left out."""
    got = got if isinstance(got, dict) else {"items": got or [], "more": False}
    items = [x for x in (got.get("items") or []) if isinstance(x, dict) and not x.get("done")]
    return {"items": [{**x, "app": key, "score": score(q, x, key, i)} for i, x in enumerate(items)], "more": bool(got.get("more"))}


def _ask(request, key: str, q: str, tz: str) -> dict:
    params = {"q": q, "n": PER_APP, **({"tz": tz} if tz else {})}
    return ranked(q, key, widgets.fetch(request, key, "/api/suite/search", params))


def everywhere(request, q: str, tz: str = "", only: list[str] | None = None, deadline: float = DEADLINE) -> dict:
    """{items, apps, late}: what every app found for q, ranked together (best first); apps: {key: {more}} of those that
    answered, or {why, status} of one that could not be asked; late: the apps that had not answered in time."""
    q = q.strip()[:80]
    if tz and not re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", tz):
        tz = ""
    keys = finders(getattr(request.state, "user", None), only)
    if not q or not keys:
        return {"items": [], "apps": {}, "late": []}
    asked = {_pool.submit(_ask, request, k, q, tz): k for k in keys}
    done, waiting = cf.wait(asked, timeout=deadline)
    items, out = [], {}
    for f in done:
        k = asked[f]
        try:
            got = f.result()
        except widgets.Unavailable as e:
            out[k] = {"status": e.status, "why": str(e)}
            continue
        except Exception as e:  # noqa: BLE001 - one app's trouble is not the search's
            out[k] = {"status": 502, "why": f"{type(e).__name__}"}
            continue
        out[k] = {"more": got["more"]}
        items.extend(got["items"])
    order = {k: i for i, k in enumerate(keys)}
    items.sort(key=lambda x: (-x["score"], order[x["app"]]))
    return {"items": items, "apps": out, "late": [k for k in keys if any(asked[f] == k for f in waiting)]}
