"""The reader (app/news.py): following a feed from a site's address, what is read and starred, each person's own,
mark all as read, the headlines card, OPML, and what a look at a feed does. The sites are stood in for."""
import time

import pytest

from iosuite_shared import testing

from iostart import db, news


def rss(title, items):
    body = "".join(f"<item><title>{t}</title><link>https://site.example/{g}</link><guid>{g}</guid><pubDate>{d}</pubDate><description>&lt;p&gt;Words of {t}&lt;/p&gt;</description></item>"
                   for g, t, d in items)
    return f'<rss version="2.0"><channel><title>{title}</title><link>https://site.example/</link>{body}</channel></rss>'.encode()


def day(n):
    return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time() - n * 86400))


@pytest.fixture()
def web(monkeypatch):
    """{address: bytes, or an Exception to raise}; asked: every (address, etag) the server fetched."""
    pages, asked = {}, []

    def fake(url, etag=None, modified=None):
        asked.append((url, etag))
        got = pages.get(url) or pages.get(url + "/")
        if got is None:
            raise ValueError("The site answered 404")
        if isinstance(got, Exception):
            raise got
        if etag == "v1" and url in pages.get("_same", ()):
            return 304, b"", url, {}
        return 200, got, url, {"etag": "v1", "modified": None}
    monkeypatch.setattr(news, "fetch_url", fake)
    pages["https://site.example/"] = b'<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'
    pages["https://site.example/feed.xml"] = rss("The Site", [("a3", "Third", day(0)), ("a2", "Second", day(1)), ("a1", "First", day(2))])
    return pages, asked


def test_follow_read_star(client, web):
    pages, asked = web
    r = client.post("/api/news/feeds", json={"url": "site.example", "folder": " Tech  news "})
    assert r.status_code == 200, r.text
    f = r.json()["feed"]
    assert r.json()["new"] and f["title"] == "The Site" and f["url"] == "https://site.example/feed.xml" and f["folder"] == "Tech news" and f["unread"] == 3
    assert client.post("/api/news/feeds", json={"url": "https://site.example/feed.xml"}).json()["new"] is False  # followed already
    assert client.post("/api/news/feeds", json={"url": "https://nothing.example"}).status_code == 400
    assert client.post("/api/news/feeds", json={"url": "javascript:alert(1)"}).status_code == 400
    o = client.get("/api/news").json()
    assert o["unread"] == 3 and o["folders"] == ["Tech news"] and [x["id"] for x in o["feeds"]] == [f["id"]]
    items = client.get("/api/news/items").json()["items"]
    assert [i["title"] for i in items] == ["Third", "Second", "First"] and not items[0]["read"] and items[0]["text"] == "Words of Third" and "html" not in items[0]
    one = client.get(f"/api/news/items/{items[0]['id']}").json()
    assert one["html"] == "<p>Words of Third</p>" and one["link"] == "https://site.example/a3" and one["feed"] == "The Site"
    # read one, star another
    assert client.post("/api/news/items/mark", json={"ids": [items[0]["id"]], "read": True}).json()["n"] == 1
    client.post("/api/news/items/mark", json={"ids": [items[2]["id"]], "starred": True})
    assert [i["title"] for i in client.get("/api/news/items").json()["items"]] == ["Second", "First"]
    assert [i["title"] for i in client.get("/api/news/items?show=starred").json()["items"]] == ["First"]
    assert [i["read"] for i in client.get("/api/news/items?show=all").json()["items"]] == [True, False, False]
    assert [i["title"] for i in client.get("/api/news/items?show=all&q=seco").json()["items"]] == ["Second"]
    assert client.get("/api/news").json()["unread"] == 2 and client.get("/api/news").json()["starred"] == 1
    # pages
    p1 = client.get("/api/news/items?show=all&limit=2").json()
    p2 = client.get(f"/api/news/items?show=all&limit=2&before={p1['next']}").json()
    assert [i["title"] for i in p1["items"]] == ["Third", "Second"] and [i["title"] for i in p2["items"]] == ["First"] and p2["next"] is None
    # everything read; the star stays; unread again one by one
    assert client.post("/api/news/read", json={"feed": f["id"]}).status_code == 200
    assert client.get("/api/news").json()["unread"] == 0 and client.get("/api/news").json()["starred"] == 1
    assert db.one("SELECT COUNT(*) AS n FROM prt_feed_marks")["n"] == 1  # only the star is left
    client.post("/api/news/items/mark", json={"ids": [items[1]["id"]], "read": False})
    assert [i["title"] for i in client.get("/api/news/items").json()["items"]] == ["Second"]
    assert client.post("/api/news/items/mark", json={"ids": [999999], "read": True}).json()["n"] == 0
    assert client.get("/api/news/items/999999").status_code == 404 and client.get("/api/news/items?feed=999").status_code == 404


def test_a_look_brings_the_new_ones(client, web):
    pages, asked = web
    f = client.post("/api/news/feeds", json={"url": "https://site.example/"}).json()["feed"]
    client.post("/api/news/read", json={})
    fid = db.one("SELECT feed_id FROM prt_feed_subs WHERE id = %s", (f["id"],))["feed_id"]
    assert news.tick() == 0  # not its turn yet
    pages["https://site.example/feed.xml"] = rss("The Site, renamed", [("a4", "Fourth", day(0)), ("a3", "Third, corrected", day(0))])
    del asked[:]
    assert news.tick(time.time() + news.EVERY + 1) == 1
    assert asked == [("https://site.example/feed.xml", None)]  # the first look by the loop: the follow itself kept no ETag
    o = client.get("/api/news").json()
    assert o["unread"] == 1 and o["feeds"][0]["title"] == "The Site, renamed"
    assert [i["title"] for i in client.get("/api/news/items?show=all").json()["items"]][:2] == ["Fourth", "Third, corrected"]
    # nothing changed: asked with the ETag, nothing new, no error
    pages["_same"] = ("https://site.example/feed.xml",)
    del asked[:]
    assert news.refresh(fid, time.time() + 2 * news.EVERY) == {"new": 0, "error": None} and asked == [("https://site.example/feed.xml", "v1")]
    # the site is away: the feed says so, and is asked less often
    pages["https://site.example/feed.xml"] = OSError("timed out")
    assert client.post(f"/api/news/feeds/{f['id']}/refresh").json() == {"checked": 1, "new": 0}
    got = client.get("/api/news").json()["feeds"][0]
    assert got["error"] == "The site took too long to answer" and got["unread"] == 1
    r = db.one("SELECT failures, next_at, fetched_at FROM prt_feeds WHERE id = %s", (fid,))
    assert r["failures"] == 1 and r["next_at"] - r["fetched_at"] == pytest.approx(2 * news.EVERY)
    # an article the feed dropped long ago goes, a starred one stays
    old = db.q("SELECT id FROM prt_feed_items WHERE feed_id = %s ORDER BY id", (fid,))
    client.post("/api/news/items/mark", json={"ids": [old[0]["id"]], "starred": True})
    db.ex("UPDATE prt_feed_items SET seen_at = 1 WHERE id IN (%s, %s)", (old[0]["id"], old[1]["id"]))
    pages["https://site.example/feed.xml"] = rss("The Site", [("a4", "Fourth", day(0))])
    del pages["_same"]
    news.refresh(fid)
    assert {r["id"] for r in db.q("SELECT id FROM prt_feed_items WHERE feed_id = %s", (fid,))} == {o["id"] for o in old} - {old[1]["id"]}


def test_each_person_their_own(client, web):
    pages, _ = web
    f = client.post("/api/news/feeds", json={"url": "https://site.example/feed.xml"}).json()["feed"]
    assert client.patch(f"/api/news/feeds/{f['id']}", json={"title": "Mine", "folder": "A", "onStart": False}).json()["title"] == "Mine"
    assert client.post("/api/news/folders/rename", json={"from": "A", "to": "B"}).json() == {"feeds": 1}
    assert client.get("/api/news").json()["folders"] == ["B"]
    assert client.get("/api/news/card").json() == {"items": [], "unread": 0, "feeds": 1}  # not on the start page
    client.patch(f"/api/news/feeds/{f['id']}", json={"onStart": True, "title": ""})
    c = client.get("/api/news/card?n=2").json()
    assert [i["title"] for i in c["items"]] == ["Third", "Second"] and c["unread"] == 3
    item = c["items"][0]["id"]
    testing.add_account(client, {"name": "riley", "password": "secret123", "role": "member"})
    kid = testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"})
    assert kid.status_code in (200, 201)
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "riley", "password": "secret123"})
    assert client.get("/api/news").json() == {"feeds": [], "folders": [], "unread": 0, "starred": 0}
    assert client.get(f"/api/news/items/{item}").status_code == 404 and client.patch(f"/api/news/feeds/{f['id']}", json={"title": "x"}).status_code == 404
    assert client.post("/api/news/items/mark", json={"ids": [item], "read": True}).json()["n"] == 0
    assert client.delete(f"/api/news/feeds/{f['id']}").status_code == 404
    mine = client.post("/api/news/feeds", json={"url": "https://site.example/feed.xml"}).json()["feed"]
    assert mine["id"] != f["id"] and mine["title"] == "The Site" and db.one("SELECT COUNT(*) AS n FROM prt_feeds")["n"] == 1  # one feed, two followers
    client.post("/api/news/read", json={})
    assert client.delete(f"/api/news/feeds/{mine['id']}").status_code == 200
    assert db.one("SELECT COUNT(*) AS n FROM prt_feeds")["n"] == 1 and db.one("SELECT COUNT(*) AS n FROM prt_feed_marks m JOIN prt_feed_subs s ON s.user_id = m.user_id")["n"] == db.one("SELECT COUNT(*) AS n FROM prt_feed_marks")["n"]
    # a viewer keeps nothing of their own
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/news").status_code == 403 and client.post("/api/news/feeds", json={"url": "https://site.example/feed.xml"}).status_code == 403
    assert client.get("/api/news/card").json() == {"items": [], "unread": 0, "feeds": 0}
    # alex's own are untouched; when alex goes, so does the feed
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert client.get("/api/news").json()["unread"] == 3
    uid = db.one("SELECT user_id FROM prt_feed_subs")["user_id"]
    assert news.person_data(uid, False) == 1 and news.person_data(uid, True) == 1
    assert db.one("SELECT COUNT(*) AS n FROM prt_feeds")["n"] == 0 and db.one("SELECT COUNT(*) AS n FROM prt_feed_items")["n"] == 0


def test_many_articles_start_mostly_read_and_opml(client, web):
    pages, _ = web
    pages["https://big.example/feed"] = rss("Big", [(f"b{n}", f"Post {n}", day(n)) for n in range(30)])
    f = client.post("/api/news/feeds", json={"url": "https://big.example/feed"}).json()["feed"]
    assert f["unread"] == news.NEW_UNREAD
    assert [i["title"] for i in client.get("/api/news/items?limit=3").json()["items"]] == ["Post 0", "Post 1", "Post 2"]
    # upto: what arrived after the page was drawn stays unread
    top = client.get("/api/news/items?limit=1").json()["items"][0]["id"]
    pages["https://big.example/feed"] = rss("Big", [("new", "Newer", day(0))] + [(f"b{n}", f"Post {n}", day(n)) for n in range(30)])
    client.post(f"/api/news/feeds/{f['id']}/refresh")
    client.post("/api/news/read", json={"feed": f["id"], "upto": top})
    assert [i["title"] for i in client.get("/api/news/items").json()["items"]] == ["Newer"]
    # out as OPML, and in again as somebody else's file
    client.post("/api/news/feeds", json={"url": "https://site.example/feed.xml", "folder": "News"})
    out = client.get("/api/news/opml")
    assert out.status_code == 200 and b'xmlUrl="https://big.example/feed"' in out.content and b'<outline text="News"' in out.content
    for s in client.get("/api/news").json()["feeds"]:
        client.delete(f"/api/news/feeds/{s['id']}")
    assert db.one("SELECT COUNT(*) AS n FROM prt_feeds")["n"] == 0
    assert client.post("/api/news/opml", content=out.content).json() == {"added": 2, "known": 0, "total": 2}
    assert client.post("/api/news/opml", content=out.content).json() == {"added": 0, "known": 2, "total": 2}
    assert client.post("/api/news/opml", content=b"<html></html>").status_code == 400
    o = client.get("/api/news").json()
    assert o["unread"] == 0 and {(x["title"], x["folder"]) for x in o["feeds"]} == {("Big", ""), ("The Site", "News")}
    assert news.tick() == 2  # read by the loop: the newest few of each are unread
    o = client.get("/api/news").json()
    assert {x["title"]: x["unread"] for x in o["feeds"]} == {"Big": news.NEW_UNREAD, "The Site": 3}


def test_layout_takes_the_news_card(client):
    assert client.put("/api/me/layout", json={"hidden": ["news"], "cards": ["news", "bookmarks"]}).json()["cards"] == ["news", "bookmarks"]
