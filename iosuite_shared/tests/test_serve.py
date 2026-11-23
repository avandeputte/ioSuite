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
    (tmp_path / "index.html").write_text('<script src="static/app.js"></script><link href="static/app.css">')
    (tmp_path / "manifest.webmanifest").write_text("{}")
    (tmp_path / "sw.js").write_text("// sw")
    a, b = FastAPI(), FastAPI()
    pages.mount(a, tmp_path, "3.9.0")
    pages.mount(b, tmp_path, "3.9.0", service_worker=True)
    c = TestClient(a)
    r = c.get("/")
    assert '"static/app.js?v=3.9.0"' in r.text and '"static/app.css?v=3.9.0"' in r.text and r.headers["cache-control"] == "no-cache"
    assert c.get("/manifest.webmanifest").headers["content-type"] == "application/manifest+json"
    assert c.get("/static/sw.js").text == "// sw" and c.get("/sw.js").status_code == 404
    assert TestClient(b).get("/sw.js").headers["content-type"].startswith("text/javascript")


def test_page_modules_are_never_kept_stale(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from iosuite_shared import pages
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "main.js").write_text("export const a = 1;")
    (tmp_path / "app.css").write_text("body{}")
    (tmp_path / "index.html").write_text("<p>")
    app = FastAPI()
    pages.mount(app, tmp_path, "1.0")
    c = TestClient(app)
    assert c.get("/static/js/main.js").headers["cache-control"] == "no-cache"
    assert "cache-control" not in c.get("/static/app.css").headers


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

