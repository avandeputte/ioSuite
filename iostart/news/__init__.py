"""Feeds: the start page's reader (the Feeds page, #/news) and the headlines card.

A feed (prt_feeds) is fetched once for everybody, by the job here, however many people follow it; its articles are
prt_feed_items. What is a person's own: which feeds they follow, under which name and in which folder
(prt_feed_subs), and what they have read and starred (prt_feed_marks). Nobody sees what another person follows, reads
or stars, an admin included.

Read and unread: a subscription's `read_upto` is the id of the newest article "mark all as read" covered; an article
is read when its id is at or under it, unless the person said otherwise for that one article (prt_feed_marks.is_read:
1 read, 0 not read, NULL no word). So marking a whole feed as read is one row, not one per article.

The server asks a feed every half hour (less often while it fails), sending what the site said the last time (ETag,
Last-Modified) so an unchanged feed costs the site almost nothing. An article the feed no longer lists goes after
KEEP_DAYS, unless somebody starred it. The browser never asks a feed itself; the pictures inside an article do come
from their own site, when the article is opened.
"""
import hashlib
import logging
import time
import urllib.error
import urllib.request

from iosuite_shared import outbound
from iosuite_shared.errors import Invalid

from iostart import config, db
from iostart.news import read as feedread
from iostart.bookmarks import icons as siteicons

log = logging.getLogger("iostart.news")

UA = "Mozilla/5.0 (compatible; ioStart feed reader)"
TIMEOUT = 15
MAX_BYTES = 6 * 1024 * 1024    # of a feed (or the page a feed is looked for on)
EVERY = 30 * 60                # between two looks at a feed
SLOWEST = 24 * 3600            # ... at one that keeps failing
KEEP_DAYS = 45                 # an article the feed no longer lists stays this long (starred ones always)
NEW_UNREAD = 20                # of a feed just followed, the newest count as not read; the rest as read
MAX_FEEDS = 500                # a person's feeds
PAGE = 50                      # articles in one answer
TICK = 60                      # seconds between the job's looks at what is due
BATCH = 8                      # feeds fetched in one look
_opener = outbound.opener(outbound.not_this_machine, redirects=True)  # the home network is fine (a feed of one's own server)

SCHEMA = [
    # a feed, once for everybody who follows it. next_at: when the job asks it again; failures: looks in a row that
    # went wrong (error says how the last one did)
    """CREATE TABLE IF NOT EXISTS prt_feeds (
        id INT AUTO_INCREMENT PRIMARY KEY,
        url_hash CHAR(64) NOT NULL,
        url TEXT NOT NULL,
        title VARCHAR(300) NOT NULL DEFAULT '',
        site TEXT NULL,
        etag VARCHAR(255) NULL,
        modified VARCHAR(64) NULL,
        fetched_at DOUBLE NOT NULL DEFAULT 0,
        next_at DOUBLE NOT NULL DEFAULT 0,
        failures INT NOT NULL DEFAULT 0,
        error VARCHAR(300) NULL,
        created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
        UNIQUE KEY idx_prt_feeds_url (url_hash),
        KEY idx_prt_feeds_next (next_at)
    )""",
    # an article. guid_hash: what makes it the same article at the next look; at: when it counts as published (the
    # feed's date, or when it was first seen if the feed gives none or one in the future), what the lists sort by;
    # seen_at: the last look that still listed it
    """CREATE TABLE IF NOT EXISTS prt_feed_items (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        feed_id INT NOT NULL,
        guid_hash CHAR(40) NOT NULL,
        title VARCHAR(500) NOT NULL,
        link TEXT NULL,
        author VARCHAR(200) NULL,
        at BIGINT NOT NULL,
        html MEDIUMTEXT NOT NULL,
        words TEXT NOT NULL,
        image TEXT NULL,
        audio TEXT NULL,
        seen_at DOUBLE NOT NULL,
        UNIQUE KEY idx_prt_feed_items_guid (feed_id, guid_hash),
        KEY idx_prt_feed_items_at (feed_id, at),
        FOREIGN KEY (feed_id) REFERENCES prt_feeds(id) ON DELETE CASCADE
    )""",
    # a person follows a feed: under their own name for it (NULL: the feed's), in a folder ('' : none), and on their
    # start page's headlines card or not
    """CREATE TABLE IF NOT EXISTS prt_feed_subs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        feed_id INT NOT NULL,
        title VARCHAR(300) NULL,
        folder VARCHAR(100) NOT NULL DEFAULT '',
        on_start TINYINT(1) NOT NULL DEFAULT 1,
        read_upto BIGINT NOT NULL DEFAULT 0,
        created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
        UNIQUE KEY idx_prt_feed_subs_user_feed (user_id, feed_id),
        KEY idx_prt_feed_subs_feed (feed_id),
        FOREIGN KEY (feed_id) REFERENCES prt_feeds(id) ON DELETE CASCADE
    )""",
    # a person's word on one article: read or not (NULL: as read_upto has it), starred
    """CREATE TABLE IF NOT EXISTS prt_feed_marks (
        user_id INT NOT NULL,
        item_id BIGINT NOT NULL,
        is_read TINYINT(1) NULL,
        starred TINYINT(1) NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, item_id),
        KEY idx_prt_feed_marks_starred (user_id, starred),
        FOREIGN KEY (item_id) REFERENCES prt_feed_items(id) ON DELETE CASCADE
    )""",
]

READ = "COALESCE(m.is_read, i.id <= s.read_upto)"  # with prt_feed_items i, prt_feed_subs s, LEFT JOIN prt_feed_marks m
JOIN = ("FROM prt_feed_subs s JOIN prt_feed_items i ON i.feed_id = s.feed_id "
        "LEFT JOIN prt_feed_marks m ON m.item_id = i.id AND m.user_id = s.user_id")


# ------------------------------------------------------------------ asking a site

def fetch_url(url: str, etag: str | None = None, modified: str | None = None) -> tuple[int, bytes, str, dict]:
    """(status, body, the address it came from after redirects, {etag, modified}); 304 with no body when the site says
    nothing changed. Raises OSError / ValueError when there is no answer to use."""
    headers = {"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/feed+json, application/xml;q=0.9, text/html;q=0.7, */*;q=0.5"}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        with _opener.open(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:  # noqa: S310 - checked as it connects (outbound)
            body = r.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("The feed is too large")
            return r.status, body, r.geturl(), {"etag": r.headers.get("ETag"), "modified": r.headers.get("Last-Modified")}
    except urllib.error.HTTPError as e:
        try:
            if e.code == 304:
                return 304, b"", url, {}
            raise ValueError(f"The site answered {e.code}")
        finally:
            e.close()
    except outbound.Invalid as e:
        raise ValueError(str(e)) from e


def _why(e: Exception) -> str:
    """An error as one line a person can read."""
    if isinstance(e, (feedread.NotAFeed, ValueError)) and str(e):
        return str(e)[:300]
    if isinstance(e, TimeoutError) or "timed out" in str(e).lower():
        return "The site took too long to answer"
    reason = getattr(e, "reason", None)
    return f"The site did not answer ({reason or type(e).__name__})"[:300]


def find(url: str) -> tuple[str, dict]:
    """(the feed's address, the feed parsed) for what a person typed: a feed's address, or a site's, whose page names
    its feed (or keeps one at a usual place). Invalid when there is none."""
    url = (url or "").strip()
    if url and "://" not in url:
        url = "https://" + url
    if not feedread.http_url(url):
        raise Invalid("A web address, please (https://example.com)")
    try:
        _, body, final, _ = fetch_url(url)
    except (OSError, ValueError) as e:
        raise Invalid(f"That address could not be read. {_why(e)}.")
    try:
        return final, feedread.parse(body, final)
    except feedread.NotAFeed:
        pass
    named = [f["url"] for f in feedread.discover(body.decode("utf-8", "replace"), final)]
    for cand in named[:4] + [g for g in feedread.guesses(final) if g not in named][:8]:
        try:
            _, b2, f2, _ = fetch_url(cand)
            return f2, feedread.parse(b2, f2)
        except (OSError, ValueError):  # NotAFeed is a ValueError
            continue
    raise Invalid("No feed found at that address. Not every site has one; try the address of its feed (often ending in /feed or /rss).")


# ------------------------------------------------------------------ the feeds and their articles

def _hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _store(feed_id: int, parsed: dict, now: float) -> int:
    """The articles of a look, kept: new ones added, known ones brought up to date. How many were new."""
    new = 0
    items = parsed.get("items") or []
    for n, it in enumerate(reversed(items)):  # oldest first, so ids rise with age as the feed orders them
        gh = hashlib.sha1(it["guid"].encode()).hexdigest()
        at = it["published"] if it["published"] and it["published"] <= now + 3600 else int(now) - (len(items) - n)
        got = db.one("SELECT id FROM prt_feed_items WHERE feed_id = %s AND guid_hash = %s", (feed_id, gh))
        if got:
            db.ex("UPDATE prt_feed_items SET title = %s, link = %s, author = %s, html = %s, words = %s, image = %s, audio = %s, seen_at = %s WHERE id = %s",
                  (it["title"], it["link"], it["author"], it["html"], it["text"], it["image"], it["audio"], now, got["id"]))
        else:
            db.ex("INSERT INTO prt_feed_items (feed_id, guid_hash, title, link, author, at, html, words, image, audio, seen_at) "
                  "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                  (feed_id, gh, it["title"], it["link"], it["author"], at, it["html"], it["text"], it["image"], it["audio"], now))
            new += 1
    return new


def _prune(feed_id: int, now: float) -> None:
    db.ex("DELETE i FROM prt_feed_items i LEFT JOIN prt_feed_marks m ON m.item_id = i.id AND m.starred = 1 "
          "WHERE i.feed_id = %s AND i.seen_at < %s AND m.item_id IS NULL", (feed_id, now - KEEP_DAYS * 86400))


def refresh(feed_id: int, now: float = None) -> dict:
    """One look at a feed. {new, error}: how many articles it brought, or why it brought none."""
    now = time.time() if now is None else now
    f = db.one("SELECT * FROM prt_feeds WHERE id = %s", (feed_id,))
    if not f:
        return {"new": 0, "error": "No such feed"}
    try:
        status, body, _, heads = fetch_url(f["url"], f["etag"], f["modified"])
        if status == 304:
            db.ex("UPDATE prt_feeds SET fetched_at = %s, next_at = %s, failures = 0, error = NULL WHERE id = %s", (now, now + EVERY, feed_id))
            db.ex("UPDATE prt_feed_items SET seen_at = %s WHERE feed_id = %s AND seen_at >= %s", (now, feed_id, f["fetched_at"] - 1))  # still listed, as far as anyone knows
            return {"new": 0, "error": None}
        parsed = feedread.parse(body, f["url"])
    except (OSError, ValueError) as e:
        fails = f["failures"] + 1
        db.ex("UPDATE prt_feeds SET fetched_at = %s, next_at = %s, failures = %s, error = %s WHERE id = %s",
              (now, now + min(SLOWEST, EVERY * 2 ** min(fails, 8)), fails, _why(e), feed_id))
        return {"new": 0, "error": _why(e)}
    with db.tx():
        new = _store(feed_id, parsed, now)
        db.ex("UPDATE prt_feeds SET title = %s, site = %s, etag = %s, modified = %s, fetched_at = %s, next_at = %s, failures = 0, error = NULL WHERE id = %s",
              (parsed["title"] or f["title"], parsed["site"] or f["site"], (heads.get("etag") or "")[:255] or None, (heads.get("modified") or "")[:64] or None,
               now, now + EVERY, feed_id))
        _prune(feed_id, now)
        if not f["fetched_at"]:  # its first look (a feed that came with an OPML file): whoever follows it starts with the newest few
            for sub in db.q("SELECT id, user_id FROM prt_feed_subs WHERE feed_id = %s AND read_upto = 0", (feed_id,)):
                _start_fresh(sub["user_id"], sub["id"], feed_id)
    return {"new": new, "error": None}


def tick(now: float = None, limit: int = BATCH) -> int:
    """The feeds whose turn it is (somebody follows them, and next_at has passed), looked at. How many."""
    now = time.time() if now is None else now
    due = db.q("SELECT f.id FROM prt_feeds f WHERE f.next_at <= %s AND EXISTS (SELECT 1 FROM prt_feed_subs s WHERE s.feed_id = f.id) "
               "ORDER BY f.next_at LIMIT %s", (now, int(limit)))
    for r in due:
        try:
            refresh(r["id"], now)
        except Exception as e:  # noqa: BLE001  one feed's trouble is not the others'
            log.warning("feed %s: %s", r["id"], e)
            db.ex("UPDATE prt_feeds SET next_at = %s WHERE id = %s", (now + EVERY, r["id"]))
    return len(due)


# ------------------------------------------------------------------ a person's feeds

def _sub(user_id: int, sid) -> dict:
    r = db.one("SELECT s.*, f.url, f.title AS feed_title, f.site, f.error, f.fetched_at FROM prt_feed_subs s JOIN prt_feeds f ON f.id = s.feed_id "
               "WHERE s.id = %s AND s.user_id = %s", (int(sid), user_id)) if str(sid).isdigit() else None
    if not r:
        raise LookupError("No such feed")
    return r


def _folder(v) -> str:
    return " ".join(str(v or "").split())[:100]


def _out(r: dict, unread: int = 0, sites: dict | None = None) -> dict:
    return {"id": r["id"], "title": r["title"] or r["feed_title"] or r["url"], "feedTitle": r["feed_title"], "url": r["url"], "site": r["site"],
            "folder": r["folder"], "onStart": bool(r["on_start"]), "unread": unread, "error": r["error"],
            "fetchedAt": r["fetched_at"] or None, "icon": siteicons.of(r["site"] or r["url"], sites)["siteIcon"]}


def overview(user_id: int) -> dict:
    """{feeds: [the person's feeds, by folder and name, each with how many articles are not read], folders, unread,
    starred}."""
    rows = db.q("SELECT s.*, f.url, f.title AS feed_title, f.site, f.error, f.fetched_at FROM prt_feed_subs s JOIN prt_feeds f ON f.id = s.feed_id "
                "WHERE s.user_id = %s", (user_id,))
    counts = {r["id"]: r["n"] for r in db.q(f"SELECT s.id, COUNT(*) AS n {JOIN} WHERE s.user_id = %s AND NOT {READ} GROUP BY s.id", (user_id,))}
    sites = siteicons.known() if rows else {}
    feeds = sorted((_out(r, counts.get(r["id"], 0), sites) for r in rows), key=lambda f: (f["folder"].lower(), f["title"].lower()))
    starred = db.one("SELECT COUNT(*) AS n FROM prt_feed_marks m JOIN prt_feed_items i ON i.id = m.item_id JOIN prt_feed_subs s ON s.feed_id = i.feed_id AND s.user_id = m.user_id "
                     "WHERE m.user_id = %s AND m.starred = 1", (user_id,))["n"]
    return {"feeds": feeds, "folders": sorted({f["folder"] for f in feeds if f["folder"]}, key=str.lower),
            "unread": sum(counts.values()), "starred": starred}


def _follow(user_id: int, url: str, parsed: dict | None, title: str | None, folder: str, now: float) -> tuple[int, bool]:
    """(the subscription's id, whether it is new). parsed: the feed as just read, or None to leave reading it to the
    loop (an OPML file's many feeds)."""
    with db.tx():
        f = db.one("SELECT id FROM prt_feeds WHERE url_hash = %s", (_hash(url),))
        if f:
            fid = f["id"]
        else:
            fid = db.ex("INSERT INTO prt_feeds (url_hash, url, title, site, next_at) VALUES (%s, %s, %s, %s, %s)",
                        (_hash(url), url, ((parsed or {}).get("title") or title or "")[:300], (parsed or {}).get("site"), 0 if parsed is None else now + EVERY))
        if parsed is not None:
            _store(fid, parsed, now)
            db.ex("UPDATE prt_feeds SET fetched_at = %s, failures = 0, error = NULL WHERE id = %s", (now, fid))
        was = db.one("SELECT id FROM prt_feed_subs WHERE user_id = %s AND feed_id = %s", (user_id, fid))
        if was:
            return was["id"], False
        sid = db.ex("INSERT INTO prt_feed_subs (user_id, feed_id, title, folder) VALUES (%s, %s, %s, %s)", (user_id, fid, (title or "")[:300] or None, folder))
        _start_fresh(user_id, sid, fid)
        return sid, True


def _start_fresh(user_id: int, sid: int, fid: int) -> None:
    """Of a feed just followed, only the newest few articles count as not read: the line goes above them all, and
    those few get a word of their own."""
    top = db.one("SELECT MAX(id) AS n FROM prt_feed_items WHERE feed_id = %s", (fid,))["n"]
    if not top:
        return  # not read yet (an imported feed): refresh() comes back here after its first look
    db.ex("UPDATE prt_feed_subs SET read_upto = %s WHERE id = %s", (top, sid))
    for r in db.q("SELECT id FROM prt_feed_items WHERE feed_id = %s ORDER BY at DESC, id DESC LIMIT %s", (fid, NEW_UNREAD)):
        db.ex("INSERT INTO prt_feed_marks (user_id, item_id, is_read) VALUES (%s, %s, 0) ON DUPLICATE KEY UPDATE is_read = 0", (user_id, r["id"]))


def _room(user_id: int, more: int = 1) -> None:
    n = db.one("SELECT COUNT(*) AS n FROM prt_feed_subs WHERE user_id = %s", (user_id,))["n"]
    if n + more > MAX_FEEDS:
        raise Invalid(f"You follow {n} feeds; {MAX_FEEDS} is the most")


def add(user_id: int, b: dict) -> dict:
    """Follow the feed at b.url (a feed's address or a site's), in b.folder. {feed, new: false when it was followed already}."""
    if not isinstance(b, dict):
        raise Invalid("An object, please")
    _room(user_id)
    url, parsed = find(str(b.get("url") or ""))
    sid, new = _follow(user_id, url, parsed, None, _folder(b.get("folder")), time.time())
    return {"feed": _out(_sub(user_id, sid), _unread(user_id, sid)), "new": new}


def _unread(user_id: int, sid: int) -> int:
    return db.one(f"SELECT COUNT(*) AS n {JOIN} WHERE s.user_id = %s AND s.id = %s AND NOT {READ}", (user_id, sid))["n"]


def change(user_id: int, sid, b: dict) -> dict:
    """b: title (nothing: the feed's own), folder, onStart."""
    r = _sub(user_id, sid)
    if not isinstance(b, dict):
        raise Invalid("An object, please")
    if "title" in b:
        db.ex("UPDATE prt_feed_subs SET title = %s WHERE id = %s", (" ".join(str(b["title"] or "").split())[:300] or None, r["id"]))
    if "folder" in b:
        db.ex("UPDATE prt_feed_subs SET folder = %s WHERE id = %s", (_folder(b["folder"]), r["id"]))
    if "onStart" in b:
        db.ex("UPDATE prt_feed_subs SET on_start = %s WHERE id = %s", (1 if b["onStart"] else 0, r["id"]))
    return _out(_sub(user_id, sid), _unread(user_id, r["id"]))


def remove(user_id: int, sid) -> None:
    """Stop following: the person's marks on its articles go; the feed itself goes when nobody follows it any more."""
    r = _sub(user_id, sid)
    with db.tx():
        db.ex("DELETE m FROM prt_feed_marks m JOIN prt_feed_items i ON i.id = m.item_id WHERE m.user_id = %s AND i.feed_id = %s", (user_id, r["feed_id"]))
        db.ex("DELETE FROM prt_feed_subs WHERE id = %s", (r["id"],))
        _sweep()


def _sweep() -> None:
    db.ex("DELETE FROM prt_feeds WHERE NOT EXISTS (SELECT 1 FROM prt_feed_subs s WHERE s.feed_id = prt_feeds.id)")


def rename_folder(user_id: int, b: dict) -> int:
    """b: {from, to}; to '' takes the feeds out of the folder. How many feeds moved."""
    old, new = _folder((b or {}).get("from")), _folder((b or {}).get("to"))
    if not old:
        raise Invalid("from: the folder's name")
    n = db.one("SELECT COUNT(*) AS n FROM prt_feed_subs WHERE user_id = %s AND folder = %s", (user_id, old))["n"]
    db.ex("UPDATE prt_feed_subs SET folder = %s WHERE user_id = %s AND folder = %s", (new, user_id, old))
    return n


def refresh_mine(user_id: int, sid=None) -> dict:
    """Look now at one of the person's feeds, or at all of them not looked at in the last two minutes. {checked, new}."""
    now = time.time()
    if sid is not None:
        ids = [_sub(user_id, sid)["feed_id"]]
    else:
        ids = [r["feed_id"] for r in db.q("SELECT s.feed_id FROM prt_feed_subs s JOIN prt_feeds f ON f.id = s.feed_id WHERE s.user_id = %s AND f.fetched_at < %s "
                                          "ORDER BY f.fetched_at LIMIT 40", (user_id, now - 120))]
    new = sum(refresh(i, now)["new"] for i in ids)
    return {"checked": len(ids), "new": new}


# ------------------------------------------------------------------ the articles

COLS = (f"i.id, i.title, i.link, i.author, i.at, i.words, i.image, i.audio, s.id AS sub_id, COALESCE(s.title, f.title, f.url) AS feed, f.site, "
        f"{READ} AS is_read, COALESCE(m.starred, 0) AS starred")


def _item(r: dict, full: bool = False) -> dict:
    d = {"id": r["id"], "title": r["title"], "link": r["link"], "author": r["author"], "at": r["at"], "text": r["words"], "image": r["image"],
         "audio": r["audio"], "feedId": r["sub_id"], "feed": r["feed"], "read": bool(r["is_read"]), "starred": bool(r["starred"])}
    if full:
        d["html"] = r["html"]
    return d


def _scope(user_id: int, feed=None, folder=None) -> tuple[str, list]:
    where, args = "s.user_id = %s", [user_id]
    if feed not in (None, ""):
        where, args = where + " AND s.id = %s", args + [_sub(user_id, feed)["id"]]
    elif folder not in (None, ""):
        where, args = where + " AND s.folder = %s", args + [_folder(folder)]
    return where, args


def items(user_id: int, feed=None, folder=None, show: str = "unread", q: str = "", before: str = "", limit: int = PAGE, start: bool = False) -> dict:
    """{items, next}: the newest first. show: unread, all or starred; q: words in the title or the text; before: the
    `next` of the answer before this one. start: only the feeds on the start page's card."""
    where, args = _scope(user_id, feed, folder)
    if start:
        where += " AND s.on_start = 1"
    if show == "starred":
        where += " AND m.starred = 1"
    elif show != "all":
        where += f" AND NOT {READ}"
    q = " ".join((q or "").split())[:100]
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where, args = where + " AND (i.title LIKE %s OR i.words LIKE %s)", args + [like, like]
    if before:
        try:
            at, iid = (int(x) for x in before.split("-", 1))
        except ValueError:
            raise Invalid("before: the `next` of the answer before")
        where, args = where + " AND (i.at, i.id) < (%s, %s)", args + [at, iid]
    limit = max(1, min(int(limit or PAGE), 200))
    rows = db.q(f"SELECT {COLS} {JOIN} JOIN prt_feeds f ON f.id = s.feed_id WHERE {where} ORDER BY i.at DESC, i.id DESC LIMIT %s", (*args, limit + 1))
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [_item(r) for r in rows], "next": f"{rows[-1]['at']}-{rows[-1]['id']}" if more else None}


def item(user_id: int, iid) -> dict:
    r = db.one(f"SELECT {COLS}, i.html {JOIN} JOIN prt_feeds f ON f.id = s.feed_id WHERE s.user_id = %s AND i.id = %s", (user_id, int(iid))) if str(iid).isdigit() else None
    if not r:
        raise LookupError("No such article")
    return _item(r, True)


def _mine(user_id: int, ids) -> list[int]:
    """The ids among `ids` that are articles of feeds the person follows."""
    if not isinstance(ids, list) or len(ids) > 500 or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise Invalid("ids: up to 500 article ids")
    if not ids:
        return []
    marks = ", ".join(["%s"] * len(ids))
    return [r["id"] for r in db.q(f"SELECT i.id FROM prt_feed_items i JOIN prt_feed_subs s ON s.feed_id = i.feed_id WHERE s.user_id = %s AND i.id IN ({marks})", (user_id, *ids))]


def mark(user_id: int, b: dict) -> dict:
    """b: {ids, read?: bool, starred?: bool} for those articles."""
    if not isinstance(b, dict):
        raise Invalid("An object, please")
    ids = _mine(user_id, b.get("ids"))
    with db.tx():
        for i in ids:
            if "read" in b:
                db.ex("INSERT INTO prt_feed_marks (user_id, item_id, is_read) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE is_read = VALUES(is_read)", (user_id, i, 1 if b["read"] else 0))
            if "starred" in b:
                db.ex("INSERT INTO prt_feed_marks (user_id, item_id, starred) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE starred = VALUES(starred)", (user_id, i, 1 if b["starred"] else 0))
    return {"ok": True, "n": len(ids)}


def mark_all(user_id: int, b: dict) -> dict:
    """Everything read in a feed (b.feed), a folder (b.folder) or everywhere; b.upto: only up to that article's id (what
    the page was showing, so an article that arrived meanwhile stays unread)."""
    b = b if isinstance(b, dict) else {}
    where, args = _scope(user_id, b.get("feed"), b.get("folder"))
    upto = b.get("upto")
    if upto is not None and (isinstance(upto, bool) or not isinstance(upto, int) or upto < 0):
        raise Invalid("upto: an article's id")
    with db.tx():
        subs = db.q(f"SELECT s.id, s.feed_id, s.read_upto, (SELECT MAX(id) FROM prt_feed_items WHERE feed_id = s.feed_id) AS top FROM prt_feed_subs s WHERE {where}", tuple(args))
        for s in subs:
            to = min(s["top"] or 0, upto) if upto is not None else (s["top"] or 0)
            if to <= s["read_upto"]:
                to = s["read_upto"]
            db.ex("UPDATE prt_feed_subs SET read_upto = %s WHERE id = %s", (to, s["id"]))
            # the words on single articles under the line are no longer needed, a star apart
            db.ex("UPDATE prt_feed_marks m JOIN prt_feed_items i ON i.id = m.item_id SET m.is_read = NULL WHERE m.user_id = %s AND i.feed_id = %s AND i.id <= %s",
                  (user_id, s["feed_id"], to))
        db.ex("DELETE FROM prt_feed_marks WHERE user_id = %s AND is_read IS NULL AND starred = 0", (user_id,))
    return {"ok": True, "feeds": len(subs)}


def card(user_id: int, n: int = 5) -> dict:
    """The start page's headlines card: {items: the newest unread articles of the feeds the person keeps on it, unread:
    how many there are in all of them, feeds: how many feeds the person follows}."""
    n = max(1, min(int(n or 5), 12))
    feeds = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(on_start), 0) AS shown FROM prt_feed_subs WHERE user_id = %s", (user_id,))
    got = items(user_id, show="unread", limit=n, start=True) if feeds["shown"] else {"items": []}
    unread = db.one(f"SELECT COUNT(*) AS n {JOIN} WHERE s.user_id = %s AND s.on_start = 1 AND NOT {READ}", (user_id,))["n"] if feeds["shown"] else 0
    return {"items": got["items"], "unread": unread, "feeds": feeds["n"]}


# ------------------------------------------------------------------ OPML in and out

def opml_out(user_id: int) -> bytes:
    rows = overview(user_id)["feeds"]
    return feedread.opml_write([{"url": f["url"], "title": f["title"], "site": f["site"], "folder": f["folder"] or None} for f in rows], "ioStart feeds")


def opml_in(user_id: int, data: bytes) -> dict:
    """Follow every feed of an OPML file, in its folders; they are read by the job over the next minutes. {added,
    known: followed already, total}."""
    try:
        feeds = feedread.opml_read(data)
    except feedread.NotAFeed as e:
        raise Invalid(f"{e}. Export your feeds from the other reader as OPML and choose that file.")
    if not feeds:
        raise Invalid("The file names no feeds")
    now, added = time.time(), 0
    have = db.one("SELECT COUNT(*) AS n FROM prt_feed_subs WHERE user_id = %s", (user_id,))["n"]
    for f in feeds:
        if have + added >= MAX_FEEDS:
            break
        _, new = _follow(user_id, f["url"], None, f["title"], _folder(f["folder"]), now)
        added += new
    return {"added": added, "known": len(feeds) - added, "total": len(feeds)}


# ------------------------------------------------------------------ a person leaves

def person_data(user_id: int, remove: bool) -> int:
    n = db.one("SELECT COUNT(*) AS n FROM prt_feed_subs WHERE user_id = %s", (user_id,))["n"]
    if remove:
        with db.tx():
            db.ex("DELETE FROM prt_feed_marks WHERE user_id = %s", (user_id,))
            db.ex("DELETE FROM prt_feed_subs WHERE user_id = %s", (user_id,))
            _sweep()
    return n


# ------------------------------------------------------------------ the job

def job():
    """The look for feeds that are due, as one of the copy's jobs (main.py at start; NEWS_LOOP=0 leaves it off: the
    tests call tick() themselves)."""
    from iosuite_shared import chores
    if not config.NEWS_LOOP:
        return None
    return chores.start(tick, every_s=TICK, first_s=TICK, name="feeds", app=config.APP, quiet=True,
                        title="Read the feeds people follow that are due")
