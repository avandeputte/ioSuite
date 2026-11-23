"""The bookmarks as a tree: what the start page shows of it, the sign-in flow that gives the browser extension and
the iPhone app their app password, and files in and out."""
import base64

from iostart import bookmarks
from iostart.bookmarks import files as bookmarkfiles


def _basic(name, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{name}:{pw}".encode()).decode()}


def _anon():
    from fastapi.testclient import TestClient
    from iostart.main import app
    return TestClient(app)  # no `with`: the app is started once per process


def test_start_page_shows_only_what_is_picked(client):
    work = client.post("/api/bookmarks/groups", json={"name": "Work"}).json()  # made in Settings: on the start page
    menu = client.post("/api/bookmarks/groups", json={"name": "Bookmarks bar", "start": False}).json()
    sub = client.post("/api/bookmarks/groups", json={"name": "Recipes", "parentId": menu["id"], "start": False}).json()
    a = client.post(f"/api/bookmarks/groups/{work['id']}/links", json={"name": "Mail", "href": "mail.example.com"}).json()
    b = client.post(f"/api/bookmarks/groups/{work['id']}/links", json={"name": "Wiki", "href": "https://wiki.example.com"}).json()
    c = client.post(f"/api/bookmarks/groups/{menu['id']}/links", json={"name": "News", "href": "https://news.example.com"}).json()
    d = client.post(f"/api/bookmarks/groups/{sub['id']}/links", json={"name": "Bread", "href": "https://bread.example.com"}).json()
    assert a["onStart"] and a["start"] is None and not c["onStart"]
    shown = lambda: [(g["name"], [l["name"] for l in g["links"]]) for g in client.get("/api/bookmarks").json()["groups"]]  # noqa: E731
    assert shown() == [("Work", ["Mail", "Wiki"])]
    # one link hidden in a folder that is shown, one shown in a folder that is not
    assert client.patch(f"/api/bookmarks/links/{b['id']}", json={"start": False}).json()["onStart"] is False
    assert client.patch(f"/api/bookmarks/links/{d['id']}", json={"start": True}).json()["onStart"] is True
    assert shown() == [("Work", ["Mail"]), ("Recipes", ["Bread"])]
    # the whole folder, and back to "as its folder"
    assert client.patch(f"/api/bookmarks/groups/{menu['id']}", json={"start": True}).json()["start"] is True
    client.patch(f"/api/bookmarks/links/{b['id']}", json={"start": None})
    assert shown() == [("Work", ["Mail", "Wiki"]), ("Bookmarks bar", ["News"]), ("Recipes", ["Bread"])]
    # everything is in the tree, nested, whatever the start page shows
    t = client.get("/api/bookmarks/tree").json()
    assert t["count"] == 4 and [x["name"] for x in t["items"]] == ["Work", "Bookmarks bar"]
    bar = t["items"][1]["items"]
    assert [(x["type"], x["name"]) for x in bar] == [("folder", "Recipes"), ("bookmark", "News")] and bar[0]["items"][0]["start"] is True
    # a folder cannot go inside itself; a link moves to another folder; deleting a folder takes what is in it
    assert client.patch(f"/api/bookmarks/groups/{menu['id']}", json={"parentId": sub["id"]}).status_code == 400
    assert client.patch(f"/api/bookmarks/links/{c['id']}", json={"groupId": work["id"]}).json()["groupId"] == work["id"]
    assert client.delete(f"/api/bookmarks/groups/{menu['id']}").status_code == 200
    assert client.get("/api/bookmarks/tree").json()["count"] == 3


def test_sign_in_flow_for_apps_gives_a_sync_only_app_password(client):
    anon = _anon()
    f = anon.post("/dav/nextcloud/index.php/login/v2", headers={"User-Agent": "ioStart Bookmarks in Firefox", "Host": "start.example.com"}).json()
    assert f["login"].startswith("http://start.example.com/dav/nextcloud/index.php/login/v2/flow/")
    poll = lambda: anon.post(f["poll"]["endpoint"].replace("http://start.example.com", ""), data={"token": f["poll"]["token"]})  # noqa: E731
    assert poll().status_code == 404
    page = f["login"].replace("http://start.example.com", "")
    assert "Sign in to ioStart first" in anon.get(page).text  # nobody signed in: nothing to allow
    assert f'href="/?flow={page.rsplit("/", 1)[-1]}"' in anon.get(page).text  # the start page signs in and sends back here
    r = client.get(page)
    assert "ioStart Bookmarks in Firefox" in r.text and "alex" in r.text
    token = page.rsplit("/", 1)[-1]
    assert anon.post("/dav/nextcloud/index.php/login/v2/grant", data={"page": token}).status_code == 403
    assert client.post("/dav/nextcloud/index.php/login/v2/grant", data={"page": token}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert poll().status_code == 404
    assert "Done" in client.post("/dav/nextcloud/index.php/login/v2/grant", data={"page": token}).text
    got = poll().json()
    assert got["loginName"] == "alex" and got["appPassword"].startswith("iostart-") and got["server"].endswith("/dav/nextcloud")
    assert poll().status_code == 404  # handed out once
    assert "no longer valid" in client.get(page).text
    auth = _basic("alex", got["appPassword"])
    assert anon.get("/dav/ext/tree", headers=auth).status_code == 200
    # for sync only: not the rest of the start page; listed with the account's app passwords, where it is revoked
    assert anon.get("/api/apps", headers=auth).status_code == 403
    mine = client.get("/api/auth/app-passwords").json()["items"]
    assert [(p["label"], p["scope"]) for p in mine] == [("Bookmark sync: ioStart Bookmarks in Firefox", "dav")]
    client.delete(f"/api/auth/app-passwords/{mine[0]['id']}")
    assert anon.get("/dav/ext/tree", headers=auth).status_code == 401


def test_what_other_sync_apps_asked_is_no_longer_answered(client):
    """Only the sign-in flow is left under /dav/nextcloud: no Nextcloud Bookmarks API, no bookmarks file over WebDAV."""
    pw = client.post("/api/auth/app-passwords", json={"label": "A sync app", "scope": "dav"}).json()["password"]
    auth = _basic("alex", pw)
    anon = _anon()
    for path in ("/dav/nextcloud/status.php", "/dav/nextcloud/index.php/apps/bookmarks/public/rest/v2/folder",
                 "/dav/nextcloud/ocs/v2.php/cloud/capabilities", "/dav/bookmarks/bookmarks.xbel", "/dav/bookmarks/"):
        assert anon.get(path, headers=auth).status_code == 404, path


def test_files_in_and_out(client):
    exported = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3 ADD_DATE="1700000000" PERSONAL_TOOLBAR_FOLDER="true">Bookmarks bar</H3>
    <DL><p>
        <DT><A HREF="https://example.com/?a=1&amp;b=2" ADD_DATE="1700000000" ICON="data:image/png;base64,AAAA">Example &amp; co</A>
        <DT><H3>Sub</H3>
        <DL><p>
            <DT><A HREF="https://deep.example/">Deep</A>
            <DD>a description some browsers add
        </DL><p>
    </DL><p>
    <DT><A HREF="https://top.example/">Top</A>
</DL><p>
"""
    r = client.post("/api/bookmarks/import", json={"file": exported})
    assert r.status_code == 200 and r.json() == {"groups": 2, "links": 3}
    t = client.get("/api/bookmarks/tree").json()["items"]
    assert [(x["type"], x["name"]) for x in t] == [("folder", "Bookmarks bar"), ("bookmark", "Top")]
    assert t[0]["items"][0]["href"] == "https://example.com/?a=1&b=2" and t[0]["items"][1]["items"][0]["name"] == "Deep"
    assert client.get("/api/bookmarks").json() == {"groups": []}  # a browser's bookmarks: none on the start page until picked
    assert client.post("/api/bookmarks/import", json={"file": "hello"}).status_code == 400
    out = client.get("/api/bookmarks/export.html")
    assert out.headers["content-disposition"] == 'attachment; filename="bookmarks.html"'
    assert [(x["type"], x["title"]) for x in bookmarkfiles.parse(out.text)] == [("folder", "Bookmarks bar"), ("bookmark", "Top")]
    x = bookmarkfiles.parse(client.get("/api/bookmarks/export.xbel").text)
    assert x[0]["children"][1]["children"][0]["url"] == "https://deep.example/" and x[0]["id"] == t[0]["id"]
    assert client.get("/api/bookmarks/export.pdf").status_code == 404
    s = client.get("/api/bookmarks/sync", headers={"host": "start.example.com"}).json()
    assert s["server"] == "http://start.example.com" and s["user"] == "alex" and "nextcloud" not in s and "webdav" not in s


def test_order_keeps_the_places_of_what_is_not_named(client):
    f = bookmarks.create(None, True, "F")["id"]
    a, sub, b, c = (bookmarks.create(f, k == "sub", k, None if k == "sub" else f"https://{k}.example")["id"] for k in ("a", "sub", "b", "c"))
    bookmarks.order(f, [c, a, b])  # the links, as Settings shows them apart from the folders
    assert [r["id"] for r in bookmarks.Tree().children(f)] == [c, sub, a, b]
    other = bookmarks.create(None, False, "o", "https://o.example")["id"]
    bookmarks.order(f, [a, other, c, b])  # one dragged in from elsewhere
    assert [r["id"] for r in bookmarks.Tree().children(f)] == [a, sub, other, c, b]
    assert bookmarks.Tree().by[other]["parent_id"] == f
