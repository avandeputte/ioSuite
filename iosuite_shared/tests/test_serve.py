import socket
import sys
import types

import pytest

from iosuite_shared import serve


def test_hosts():
    assert serve.hosts("") == ["0.0.0.0"] and serve.hosts(None) == ["0.0.0.0"]
    assert serve.hosts("127.0.0.1") == ["127.0.0.1"]
    assert serve.hosts(" 127.0.0.1, 192.168.1.151 ,[::1]") == ["127.0.0.1", "192.168.1.151", "[::1]"]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_run(monkeypatch):
    calls = []

    class Server:
        def __init__(self, config):
            self.config = config

        def run(self, sockets=None):
            calls.append(("server", self.config, [s.getsockname()[0] for s in sockets or []]))
            for s in sockets or []:
                s.close()
    fake = types.SimpleNamespace(Server=Server, Config=lambda target, **kw: (target, kw))
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    monkeypatch.setattr(serve, "SERVER", None)
    serve.run("app.main:app", "127.0.0.1", 8630, proxy_headers=False)   # one address, one port: the web server opens it
    assert calls == [("server", ("app.main:app", {"host": "127.0.0.1", "port": 8630, "proxy_headers": False}), [])]
    assert isinstance(serve.SERVER, Server)  # what end() asks to stop
    a, b = _free_port(), _free_port()  # a copy's doors: one address, several ports
    serve.run("app.main:app", "127.0.0.1", [a, b], proxy_headers=False)
    assert calls.pop() == ("server", ("app.main:app", {"host": "127.0.0.1", "port": a, "proxy_headers": False}), ["127.0.0.1", "127.0.0.1"])
    port = _free_port()
    serve.run("app.main:app", "127.0.0.1,127.0.0.2", port, proxy_headers=False)
    assert calls[1] == ("server", ("app.main:app", {"host": "127.0.0.1", "port": port, "proxy_headers": False}), ["127.0.0.1", "127.0.0.2"])
    with pytest.raises(SystemExit) as e:
        serve.run("app.main:app", "127.0.0.1,192.0.2.77", port)  # not an address of this machine
    assert "192.0.2.77" in str(e.value)


def test_the_page_its_manifest_and_static_folder(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from iosuite_shared import pages
    (tmp_path / "index.html").write_text('<script src="static/app.js"></script><link href="static/app.css"><link href="api/auth/base.css">')
    (tmp_path / "app.js").write_text("import './js/main.js';")
    (tmp_path / "app.css").write_text("body{}")
    (tmp_path / "manifest.webmanifest").write_text("{}")
    (tmp_path / "sw.js").write_text("// sw")
    a, b = FastAPI(), FastAPI()
    pages.mount(a, tmp_path)
    pages.mount(b, tmp_path, service_worker=True)
    c = TestClient(a)
    r = c.get("/")
    js, css = pages.mark(tmp_path / "app.js"), pages.mark(tmp_path / "app.css")
    assert len(js) == 10 and js != css   # a mark of what is in the file, not of the version
    assert f'"static/app.js?v={js}"' in r.text and f'"static/app.css?v={css}"' in r.text and r.headers["cache-control"] == "no-cache"
    assert f'"api/auth/base.css?v={pages.mark(pages.SHARED / "base.css")}"' in r.text
    assert c.get("/manifest.webmanifest").headers["content-type"] == "application/manifest+json"
    assert c.get("/static/sw.js").text == "// sw" and c.get("/sw.js").status_code == 404
    assert TestClient(b).get("/sw.js").headers["content-type"].startswith("text/javascript")
    # the file changes: so does its mark, and with it the address the page names
    (tmp_path / "app.js").write_text("import './js/main.js';  // changed")
    assert pages.mark(tmp_path / "app.js") != js and f"app.js?v={js}" not in c.get("/").text


def test_static_files_are_kept_for_good_only_under_their_own_mark(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from iosuite_shared import pages
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "main.js").write_text("export const a = 1;")
    (tmp_path / "app.css").write_text("body{}")
    (tmp_path / "icon.png").write_bytes(b"\x89PNG" + bytes(2000))
    (tmp_path / "index.html").write_text("<p>")
    app = FastAPI()
    pages.mount(app, tmp_path)
    c = TestClient(app)
    # a module of the page is imported by its name alone: asked for again each time, so no update pairs it with an old one
    assert c.get("/static/js/main.js").headers["cache-control"] == "no-cache"
    assert c.get("/static/app.css").headers["cache-control"] == "no-cache"
    v = pages.mark(tmp_path / "app.css")
    r = c.get(f"/static/app.css?v={v}")
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    # a mark that is not this file's (the page of the version before, asking the copy that was just updated)
    assert c.get("/static/app.css?v=0123456789").headers["cache-control"] == "no-cache"
    assert c.get("/static/app.css?v=").headers["cache-control"] == "no-cache"
    # unchanged: 304, saying the same about keeping it
    again = c.get(f"/static/app.css?v={v}", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert c.get("/static/icon.png").headers["cache-control"] == "no-cache" and c.get("/static/nothing.js").status_code == 404
    # what the suite keeps once is in every app's /static (the maps), after the app's own files; nothing else of the shared folder is
    assert "Leaflet 1.9.4" in c.get("/static/vendor/leaflet/leaflet.js").text
    assert c.get("/static/vendor/leaflet/images/marker-icon.png").headers["content-type"] == "image/png"
    assert c.get("/static/frame.js").status_code == 404 and c.get("/static/../frame.js").status_code == 404
    (tmp_path / "vendor" / "leaflet").mkdir(parents=True)
    (tmp_path / "vendor" / "leaflet" / "leaflet.js").write_text("// the app's own")
    assert c.get("/static/vendor/leaflet/leaflet.js").text == "// the app's own"


def test_scripts_and_style_sheets_are_sent_compressed(tmp_path):
    import gzip

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from iosuite_shared import pages
    text = "export const a = 1;\n" * 400
    (tmp_path / "app.js").write_text(text)
    (tmp_path / "small.js").write_text("export const a = 1;")
    (tmp_path / "icon.png").write_bytes(b"\x89PNG" + bytes(4000))
    (tmp_path / "index.html").write_text("<p>")
    app = FastAPI()
    pages.mount(app, tmp_path)
    c = TestClient(app)
    with c.stream("GET", "/static/app.js", headers={"Accept-Encoding": "gzip"}) as r:
        raw = b"".join(r.iter_raw())
        assert r.headers["content-encoding"] == "gzip" and r.headers["vary"] == "Accept-Encoding"
        assert r.headers["content-type"].startswith("text/javascript") and int(r.headers["content-length"]) == len(raw) < len(text) // 10
        assert gzip.decompress(raw).decode() == text
        etag = r.headers["etag"]
    assert etag.startswith('W/"')
    # the browser's copy is still the file: 304, whichever way it was sent
    assert c.get("/static/app.js", headers={"Accept-Encoding": "gzip", "If-None-Match": etag}).status_code == 304
    plain = c.get("/static/app.js", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers and plain.text == text and plain.headers["vary"] == "Accept-Encoding"
    assert c.get("/static/app.js", headers={"Accept-Encoding": "identity", "If-None-Match": plain.headers["etag"]}).status_code == 304
    # not worth it: a small file, a picture; and a part of a file is sent as it is
    for path in ("/static/small.js", "/static/icon.png"):
        assert "content-encoding" not in c.get(path, headers={"Accept-Encoding": "gzip"}).headers
    part = c.get("/static/app.js", headers={"Accept-Encoding": "gzip", "Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == text[:10].encode() and "content-encoding" not in part.headers
    assert "content-encoding" not in c.head("/static/app.js", headers={"Accept-Encoding": "gzip"}).headers


def test_the_suite_s_own_scripts_at_their_routes(tmp_path):
    import gzip

    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from iosuite_shared import pages
    text = "export function h() {}\n" * 300
    (tmp_path / "ui.js").write_text(text)
    app = FastAPI()

    @app.get("/api/auth/ui.js")
    def ui(request: Request):
        return pages.send(request, tmp_path / "ui.js", "text/javascript")

    c = TestClient(app)
    with c.stream("GET", "/api/auth/ui.js", headers={"Accept-Encoding": "gzip, br"}) as r:
        assert r.headers["content-encoding"] == "gzip" and gzip.decompress(b"".join(r.iter_raw())).decode() == text
        assert r.headers["cache-control"] == "no-cache" and r.headers["content-type"].startswith("text/javascript")
        etag = r.headers["etag"]
    # imported by its name: asked for each time, and answered 304 while it is the same (it was sent whole each time before)
    again = c.get("/api/auth/ui.js", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b"" and again.headers["cache-control"] == "no-cache"
    plain = c.get("/api/auth/ui.js", headers={"Accept-Encoding": "identity"})
    assert plain.text == text and "content-encoding" not in plain.headers
    assert c.get("/api/auth/ui.js", headers={"If-None-Match": plain.headers["etag"]}).status_code == 304
    assert c.get(f"/api/auth/ui.js?v={pages.mark(tmp_path / 'ui.js')}").headers["cache-control"] == "public, max-age=31536000, immutable"
    (tmp_path / "ui.js").write_text(text + "// changed\n")
    assert c.get("/api/auth/ui.js", headers={"If-None-Match": etag}).status_code == 200


# ---- a copy with a certificate: ports that answer HTTPS and plain HTTP both
SERVER = '''
import json, sys
from iosuite_shared import serve

plain, both, cert, renewed, mark = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            m = await receive()
            if m["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            else:
                open(mark, "w").write("stopped")
                await send({"type": "lifespan.shutdown.complete"})
                return
    said = {"scheme": scope["scheme"], "port": scope["server"][1], "path": scope["path"]}
    if scope["path"] == "/renew":
        said["renewed"] = serve.reload(renewed)
    body = json.dumps(said).encode()
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})

serve.run(app, "127.0.0.1", [plain, both], secure=[both], ssl_certfile=cert, proxy_headers=False, log_config=None)
'''


def _http(sock, path="/", close=False):
    """One request on an open connection: the answer's JSON."""
    import json
    sock.sendall(f"GET {path} HTTP/1.1\r\nHost: home.example.com\r\n{'Connection: close' + chr(13) + chr(10) if close else ''}\r\n".encode())
    data = b""
    while b"\r\n\r\n" not in data:
        got = sock.recv(65536)
        if not got:
            raise ConnectionError("closed")
        data += got
    head, _, body = data.partition(b"\r\n\r\n")
    assert head.startswith(b"HTTP/1.1 200"), head
    length = int(next(line.split(b":")[1] for line in head.split(b"\r\n") if line.lower().startswith(b"content-length")))
    while len(body) < length:
        body += sock.recv(65536)
    return json.loads(body)


def test_a_port_answers_https_and_plain_http_both(tmp_path):
    import hashlib
    import signal
    import ssl
    import subprocess
    import time

    from iosuite_shared import acme
    from iosuite_shared.tests.authority import Authority
    ca = Authority()
    files = []
    for i in (1, 2):
        key, chain = ca.issue(["home.example.com"])
        f = tmp_path / f"cert{i}.pem"
        f.write_text(key + chain)
        files.append((str(f), acme.describe(chain)["fingerprint"]))
    (tmp_path / "server.py").write_text(SERVER)
    plain, both = _free_port(), _free_port()
    proc = subprocess.Popen([sys.executable, str(tmp_path / "server.py"), str(plain), str(both), files[0][0], files[1][0], str(tmp_path / "mark")],
                            stderr=subprocess.PIPE, text=True)
    trust = ssl.create_default_context(cadata=ca.root_pem())

    def secure(port):
        s = trust.wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=10), server_hostname="home.example.com")
        return s, hashlib.sha256(s.getpeercert(binary_form=True)).hexdigest()
    try:
        end = time.time() + 30
        while True:
            try:
                socket.create_connection(("127.0.0.1", both), timeout=1).close()
                break
            except OSError:
                assert proc.poll() is None and time.time() < end, "the server did not start"
                time.sleep(0.1)
        # the plain port as ever; the other port without HTTPS as before, and with it
        with socket.create_connection(("127.0.0.1", plain), timeout=10) as s:
            assert _http(s) == {"scheme": "http", "port": plain, "path": "/"}
        with socket.create_connection(("127.0.0.1", both), timeout=10) as s:
            assert _http(s, "/calendar/dav/") == {"scheme": "http", "port": both, "path": "/calendar/dav/"}
            assert _http(s, "/again")["path"] == "/again"  # the connection is kept, as on any port
        s, shown = secure(both)
        with s:
            assert shown == files[0][1]  # the certificate, checked against the authority's root and the name
            assert _http(s) == {"scheme": "https", "port": both, "path": "/"}
            assert _http(s, "/again") == {"scheme": "https", "port": both, "path": "/again"}
        with pytest.raises((ssl.SSLError, OSError)):  # the plain port speaks no TLS
            secure(plain)
        # something that begins like TLS and is not: hung up on, and the port goes on answering
        with socket.create_connection(("127.0.0.1", both), timeout=10) as s:
            s.sendall(b"\x16\x03\x01\x00\x05hello")
            try:
                while s.recv(1024):
                    pass  # an alert, perhaps, before the end
            except ConnectionError:
                pass
        # one that connects and says nothing does not hold the others up
        idle = socket.create_connection(("127.0.0.1", both), timeout=10)
        with socket.create_connection(("127.0.0.1", both), timeout=10) as s:
            assert _http(s)["scheme"] == "http"
        idle.close()
        # a renewed certificate: connections made from now on get it, without the server starting again
        s, shown = secure(both)
        with s:
            assert _http(s, "/renew")["renewed"] is True
            assert _http(s)["scheme"] == "https"  # the open one goes on
        s, shown = secure(both)
        with s:
            assert shown == files[1][1] and _http(s)["scheme"] == "https"
        # stopped like any service: the apps get their shutdown, the process ends
        held = socket.create_connection(("127.0.0.1", both), timeout=10)  # an idle connection does not keep it
        assert _http(held)["scheme"] == "http"
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=20) in (0, -signal.SIGTERM)  # the web server ends by the signal it was sent, once it has finished
        held.close()
        assert (tmp_path / "mark").read_text() == "stopped"
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", both), timeout=2)
        assert f"HTTPS on port {both}" in proc.stderr.read()
    finally:
        if proc.poll() is None:
            proc.kill()


def test_free_and_reload_without_https_doors(monkeypatch):
    port = _free_port()
    assert serve.free("127.0.0.1", port)
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))
        s.listen()
        assert not serve.free("127.0.0.1", port) and not serve.free("127.0.0.1,127.0.0.2", port)
    assert not serve.free("192.0.2.77", port)  # not an address of this machine
    monkeypatch.setattr(serve, "CONTEXT", None)
    assert serve.reload("/nowhere.pem") is False


ENDING = '''
import contextlib, json, pathlib, sys, threading
from iosuite_shared import serve

mark = pathlib.Path(sys.argv[2])


@contextlib.asynccontextmanager
async def lifespan(app):
    yield
    mark.write_text("the apps were stopped")


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        async with lifespan(None):
            while True:
                m = await receive()
                if m["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif m["type"] == "lifespan.shutdown":
                    break
        await send({"type": "lifespan.shutdown.complete"})
        return
    if scope["path"] == "/restart":
        serve.end(0.2)
    body = json.dumps({"ok": True}).encode()
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})

if len(sys.argv) > 3:   # a thread that never ends: the stop is cut short, the process still leaves
    serve.STOP_S = 1.0
    threading.Thread(target=threading.Event().wait).start()
serve.run(app, "127.0.0.1", int(sys.argv[1]), log_config=None, timeout_graceful_shutdown=2)
'''


@pytest.mark.parametrize("stuck", [False, True])
def test_a_restart_stops_the_copy_as_the_service_manager_would(tmp_path, stuck):
    """serve.end(): what asked is answered, the apps' shutdown runs, and the process leaves with exit code 0 for the
    service manager to start it again; one that cannot finish (a thread that never ends) leaves all the same."""
    import subprocess
    import time
    (tmp_path / "server.py").write_text(ENDING)
    port, mark = _free_port(), tmp_path / "mark"
    proc = subprocess.Popen([sys.executable, str(tmp_path / "server.py"), str(port), str(mark), *(["stuck"] if stuck else [])],
                            stderr=subprocess.PIPE, text=True)
    try:
        end = time.time() + 30
        while True:
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=1)
                break
            except OSError:
                assert proc.poll() is None and time.time() < end, proc.stderr.read()
                time.sleep(0.1)
        assert _http(s, "/restart", close=True) == {"ok": True}   # answered before it stops
        s.close()
        assert proc.wait(15) == 0
        assert mark.read_text() == "the apps were stopped"
    finally:
        if proc.poll() is None:
            proc.kill()

