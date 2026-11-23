"""The suite's own certificate: what is asked for, when, how it is kept, and what a copy serves."""
import json
import os
import stat
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from iosuite_shared import acme, admin, certs, config, credentials, db, users
from iosuite_shared.errors import Invalid
from iosuite_shared.tests.authority import Authority


@pytest.fixture(autouse=True)
def machine(monkeypatch, tmp_path):
    """A machine with the usual ports and a data folder of the test's own; nothing served yet."""
    monkeypatch.setattr(acme, "PAUSE", (0.01, 0.02))
    for k, v in (("PORT", 80), ("SYNC_PORT", 8443), ("MCP_PORT", 8444), ("HTTPS_PORT", 443), ("TLS_CERT_FILE", ""), ("TLS_KEY_FILE", ""),
                 ("ACME_CA_FILE", ""), ("DATA_DIR", tmp_path), ("HOST", "127.0.0.1")):
        monkeypatch.setattr(config, k, v)
    for k, v in (("SERVING", None), ("LOADED", ""), ("NAMES", ()), ("PAGES_PORT", 0), ("UNUSABLE", ""), ("NOTE", ""), ("HOOKS", {})):
        monkeypatch.setattr(certs, k, v)
    credentials.forget()


@pytest.fixture
def ca():
    with Authority(fetch=lambda name, path: certs.proof(path)) as a:  # the authority asks the suite, whichever copy answers
        yield a


def addresses(**of):
    """PUBLIC_URL and the like, as Settings stores them: suite="https://…", iocalendar="https://…", iocalendar_sync=…"""
    for k, v in of.items():
        app, _, door = k.partition("_")
        db.set_setting({"": "PUBLIC_URL", "sync": "SYNC_URL", "mcp": "MCP_URL"}[door], v, "" if app == "suite" else app)


def switch_on(ca, **more):
    return certs.save({"on": True, "ca": ca.directory, **more})


# ---- what the admin sets
def test_what_the_admin_sets():
    assert certs.settings() == {"on": False, "email": "", "ca": "letsencrypt", "proof": "http", "names": []}
    s = certs.save({"email": " alex@example.com ", "ca": "staging", "names": "Photos.Example.com, calendar.example.com photos.example.com"})
    assert s["email"] == "alex@example.com" and s["ca"] == "staging" and s["names"] == ["photos.example.com", "calendar.example.com"]
    assert not s["on"] and not s["serving"] and s["certificate"] is None and s["tokenSet"] is False
    assert certs.directory("staging") == acme.STAGING and certs.directory("letsencrypt") == acme.LETSENCRYPT
    assert certs.directory("https://ca.example.com/dir") == "https://ca.example.com/dir"
    for bad in ({"email": "alex"}, {"ca": "ftp://ca.example.com"}, {"ca": "http://ca.example.com/dir"}, {"proof": "smoke"},
                {"names": ["not a name"]}, {"names": ["192.168.1.5"]}, {"names": ["*.example.com"]},  # a star needs DNS
                {"on": True, "proof": "cloudflare"}):                                               # and DNS needs the token
        with pytest.raises(Invalid):
            certs.save(bad)
    assert certs.settings()["names"] == ["photos.example.com", "calendar.example.com"]  # nothing of a refused change is kept
    s = certs.save({"proof": "cloudflare", "token": " cf-token ", "names": ["*.example.com"], "on": True})
    assert s["on"] and s["tokenSet"] and credentials.get("", certs.CF_TOKEN) == "cf-token"
    assert "cf-token" not in json.dumps(s)
    assert certs.save({"ca": ""})["ca"] == "letsencrypt"


def test_the_names_are_the_suite_s_addresses():
    assert certs.wanted() == []
    addresses(suite="http://home.example.com", iocalendar="https://calendar.example.com", iopix="https://photos.example.com:8443/",
              iocalendar_sync="https://sync.example.com/calendar", iotask="http://192.168.1.151:8000", ionote="http://nas.lan",
              iodocs="http://nas", suite_mcp="https://home.example.com:8444")
    assert certs.wanted() == ["home.example.com", "calendar.example.com", "photos.example.com", "sync.example.com"]  # the suite's own first
    certs.save({"names": ["extra.example.org"]})
    assert certs.wanted()[-1] == "extra.example.org"
    certs.save({"proof": "cloudflare", "token": "t", "names": ["*.example.com", "example.com"]})
    assert certs.wanted() == ["*.example.com", "example.com"]  # what a star covers is not asked beside it
    assert not certs.certifiable("localhost") and not certs.certifiable("printer.local") and not certs.certifiable("[fd00::1]")


# ---- asking
def test_a_certificate_is_asked_for_kept_and_described(ca):
    addresses(suite="http://home.example.com", iocalendar="http://calendar.example.com")
    assert certs.due() == ""  # not switched on: nothing is asked
    switch_on(ca, email="alex@example.com")
    assert certs.due() == "there is none yet"
    said = []
    have = certs.obtain(said.append)
    assert have["names"] == ["home.example.com", "calendar.example.com"]
    key, chain = certs.bundle()
    assert "PRIVATE KEY" in key and chain.count("BEGIN CERTIFICATE") == 2 and certs.certificate()["fingerprint"] == have["fingerprint"]
    st = certs.state()
    assert st["ok"] and st["names"] == have["names"] and st["until"] == have["until"] and st["ca"] == ca.directory and st["copy"]
    assert certs.due() == "" and any("home.example.com" in line for line in said)
    assert not db.q("SELECT name FROM ios_settings WHERE name LIKE 'acme\\_%%' OR name = %s", (certs.LOCK,))  # proofs and the lock are gone
    assert list(ca.accounts.values())[0]["contact"] == ["mailto:alex@example.com"]
    # what the suite made for itself is not among the keys people set, and cannot be set there
    names = {k["name"] for k in credentials.listing()}
    assert certs.BUNDLE not in names and certs.ACCOUNT not in names and credentials.get("", certs.ACCOUNT)
    me = users.create("alex", "secret123", suite_admin=True)
    for name in (certs.BUNDLE, certs.ACCOUNT):
        with pytest.raises(LookupError):
            admin.set_key(me, "_suite", name, "mine")
    # the same account the next time
    certs.obtain()
    assert len(ca.accounts) == 1 and certs.certificate()["fingerprint"] != have["fingerprint"]


def test_when_one_is_due(ca):
    addresses(suite="https://home.example.com")
    switch_on(ca)
    certs.obtain()
    have = certs.certificate()
    life = have["until"] - have["from"]
    assert certs.due(have["from"] + life * 0.6) == ""
    assert certs.due(have["from"] + life * 0.67).startswith("it runs out on ")  # a third of its life is left
    addresses(iopix="https://photos.example.com")
    assert certs.due() == "it does not hold for photos.example.com"
    certs.obtain()
    assert certs.due() == "" and certs.certificate()["names"] == ["home.example.com", "photos.example.com"]
    certs.save({"ca": "staging"})
    assert certs.due() == "another authority was chosen"
    certs.save({"ca": ca.directory, "on": False})
    assert certs.due() == ""
    certs.save({"on": True})
    db.set_setting("PUBLIC_URL", None, "")
    db.set_setting("PUBLIC_URL", None, "iopix")
    assert certs.due() == ""  # no name left to ask for
    with pytest.raises(Invalid):
        certs.obtain()


def test_a_refusal_is_kept_and_not_asked_again_within_the_hour(ca):
    addresses(suite="http://home.example.com")
    switch_on(ca)
    ca.fail["home.example.com"] = "Connection refused"
    with pytest.raises(acme.Problem):
        certs.obtain()
    st = certs.state()
    assert st["ok"] is False and st["error"] == "home.example.com: Connection refused" and st["kind"] == "unauthorized"
    assert certs.bundle() is None and certs.due() == "there is none yet"
    assert not certs.may_try() and certs.may_try(time.time() + certs.AGAIN_S + 1)
    looked = len(ca.looked)
    assert certs.tick() == "" and len(ca.looked) == looked  # tick() leaves the authority alone for the hour
    ca.fail.clear()
    db.set_setting(certs.STATE, json.dumps({**st, "at": st["at"] - certs.AGAIN_S - 5}), "")
    assert certs.tick().startswith("asked for a certificate") and certs.state()["ok"] and certs.bundle()
    assert not db.q("SELECT name FROM ios_settings WHERE name = %s", (certs.LOCK,))


def test_one_copy_asks_at_a_time(ca):
    addresses(suite="http://home.example.com")
    switch_on(ca)
    assert certs._lock()
    with pytest.raises(Invalid) as e:
        certs.obtain()
    assert "Another server" in str(e.value) and not ca.seen
    assert "Another server" in certs.tick()
    # a copy that died while asking does not hold the others up for ever
    db.ex("UPDATE ios_settings SET value = %s WHERE name = %s", (f"nas:1:{int(time.time()) - certs.LOCK_S - 5}", certs.LOCK))
    assert certs.obtain()["names"] == ["home.example.com"]


def test_the_proof_any_copy_answers():
    certs._publish("http-01", "home.example.com", "tok_en-1", "tok_en-1.thumb")
    assert certs.proof("/.well-known/acme-challenge/tok_en-1") == "tok_en-1.thumb"
    for path in ("/.well-known/acme-challenge/other", "/.well-known/acme-challenge/", "/.well-known/acme-challenge/a/b",
                 "/.well-known/acme-challenge/%27", "/somewhere/tok_en-1"):
        assert certs.proof(path) is None
    certs._remove("http-01", "home.example.com", "tok_en-1")
    assert certs.proof("/.well-known/acme-challenge/tok_en-1") is None


# ---- through Cloudflare's DNS
class FakeCloudflare:
    """Cloudflare's API and a DNS-over-HTTPS resolver, as far as the proof needs them."""

    def __init__(self, zones):
        self.zones, self.records, self.calls, self.token, self.n = dict(zones), {}, [], "cf-token", 0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _answer(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _do(self):
                u = urlsplit(self.path)
                q = parse_qs(u.query)
                if u.path == "/dns-query":
                    got = [r["content"] for r in fake.records.values() if r["name"] == q["name"][0]]
                    return self._answer(200, {"Answer": [{"data": f'"{v}"'} for v in got]})
                fake.calls.append((self.command, u.path + (f"?{u.query}" if u.query else "")))
                if self.headers.get("Authorization") != f"Bearer {fake.token}":
                    return self._answer(403, {"success": False, "errors": [{"code": 9109, "message": "Invalid access token"}]})
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"null")
                part = u.path.strip("/").split("/")
                if part == ["zones"]:
                    z = fake.zones.get(q["name"][0])
                    return self._answer(200, {"success": True, "result": [{"id": z, "name": q["name"][0]}] if z else []})
                if len(part) == 3 and part[2] == "dns_records" and self.command == "POST":
                    fake.n += 1
                    fake.records[f"r{fake.n}"] = {"zone": part[1], **body}
                    return self._answer(200, {"success": True, "result": {"id": f"r{fake.n}"}})
                if len(part) == 4 and self.command == "DELETE" and fake.records.pop(part[3], None):
                    return self._answer(200, {"success": True, "result": {"id": part[3]}})
                self._answer(404, {"success": False, "errors": [{"message": "not found"}]})
            do_GET = do_POST = do_DELETE = _do

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def txt(self, record):
        return [r["content"] for r in self.records.values() if r["name"] == record]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def cloudflare(monkeypatch):
    f = FakeCloudflare({"example.com": "z1", "example.org": "z2"})
    monkeypatch.setattr(certs.Cloudflare, "API", f.url)
    monkeypatch.setattr(certs.Cloudflare, "DOH", f.url + "/dns-query")
    yield f
    f.close()


def test_the_proof_through_cloudflare(cloudflare):
    dns = certs.Cloudflare("cf-token", wait=2)
    dns.publish("dns-01", "*.home.example.com", "t1", "value-1")
    dns.publish("dns-01", "home.example.com", "t2", "value-2")
    assert cloudflare.txt("_acme-challenge.home.example.com") == ["value-1", "value-2"]
    assert all(r["type"] == "TXT" and r["zone"] == "z1" and r["ttl"] == 60 for r in cloudflare.records.values())
    assert ("GET", "/zones?name=home.example.com") in cloudflare.calls and ("GET", "/zones?name=example.com") in cloudflare.calls  # the zone is found from the name up
    dns.remove("dns-01", "home.example.com", "t2")
    dns.remove("dns-01", "*.home.example.com", "t1")
    dns.remove("dns-01", "never.example.com", "t9")  # one that was never made
    assert not cloudflare.records
    with pytest.raises(acme.Problem) as e:
        dns.publish("dns-01", "home.example.net", "t3", "v")
    assert "no zone for home.example.net" in e.value.detail
    with pytest.raises(acme.Problem) as e:
        certs.Cloudflare("wrong").publish("dns-01", "home.example.com", "t4", "v")
    assert e.value.detail == "Cloudflare: Invalid access token" and e.value.kind == "dns"
    with pytest.raises(Invalid):
        certs.Cloudflare("")
    cloudflare.close()
    with pytest.raises(acme.Problem) as e:
        dns.publish("dns-01", "home.example.com", "t5", "v")
    assert e.value.kind == "connection"


def test_a_certificate_with_a_star_through_cloudflare(cloudflare):
    with Authority(txt=cloudflare.txt) as ca:
        addresses(suite="https://home.example.com", iocalendar="https://calendar.example.com")
        certs.save({"on": True, "ca": ca.directory, "proof": "cloudflare", "token": "cf-token", "names": ["*.example.com", "family.example.org"]})
        assert certs.wanted() == ["*.example.com", "family.example.org"]  # what the star covers is not asked twice
        have = certs.obtain()
        assert have["names"] == ["*.example.com", "family.example.org"] and not cloudflare.records
        assert acme.covers(have["names"], "home.example.com") and certs.due() == ""
        credentials.put("", certs.CF_TOKEN, "revoked")
        with pytest.raises(acme.Problem) as e:
            certs.obtain()
        assert certs.state()["error"] == "Cloudflare: Invalid access token" == e.value.detail


# ---- what a copy serves
def test_a_copy_serves_the_stored_certificate(ca):
    addresses(suite="http://home.example.com", suite_sync="http://home.example.com:8443", suite_mcp="http://home.example.com:9999",
              iocalendar="http://calendar.example.com", iopix="http://photos.lan")
    certs.start(free=lambda port: True)
    assert not certs.serving() and certs.PAGES_PORT == 0  # none stored
    switch_on(ca)
    certs.obtain()
    certs.start(free=lambda port: True)
    assert certs.serving() and certs.PAGES_PORT == 443 and certs.NAMES == ("home.example.com", "calendar.example.com")
    file, key = certs.SERVING
    assert key is None and file == str(config.DATA_DIR / "tls" / "suite.pem")
    assert stat.S_IMODE(os.stat(file).st_mode) == 0o600 and stat.S_IMODE(os.stat(config.DATA_DIR / "tls").st_mode) == 0o700
    text = open(file).read()
    assert text.index("PRIVATE KEY") < text.index("BEGIN CERTIFICATE") and certs.LOADED == certs.certificate()["fingerprint"]
    assert certs.named("Home.example.com") and not certs.named("192.168.1.151") and not certs.named("")
    # the addresses that said http:// for a name it holds for say https:// now; the others are left alone
    stored = {(r["app"], r["name"]): r["value"] for r in db.q("SELECT app, name, value FROM ios_settings WHERE name LIKE '%%\\_URL'")}
    assert stored == {("", "PUBLIC_URL"): "https://home.example.com", ("", "SYNC_URL"): "https://home.example.com:8443",
                      ("", "MCP_URL"): "http://home.example.com:9999",  # a port something in front of the suite maps
                      ("iocalendar", "PUBLIC_URL"): "https://calendar.example.com", ("iopix", "PUBLIC_URL"): "http://photos.lan"}
    assert certs.status()["serving"] and len(certs.status()["moved"]) == 3
    # switched off: plain again, and the addresses say what they said, but for one somebody changed since
    db.set_setting("PUBLIC_URL", "https://kalender.example.com", "iocalendar")
    certs.save({"on": False})
    certs.start(free=lambda port: True)
    assert not certs.serving() and certs.bundle()  # the certificate is kept, for when it is switched on again
    stored = {(r["app"], r["name"]): r["value"] for r in db.q("SELECT app, name, value FROM ios_settings WHERE name LIKE '%%\\_URL'")}
    assert stored[("", "PUBLIC_URL")] == "http://home.example.com" and stored[("", "SYNC_URL")] == "http://home.example.com:8443"
    assert stored[("iocalendar", "PUBLIC_URL")] == "https://kalender.example.com" and certs.moved() == []


def test_what_keeps_a_copy_plain_or_without_the_pages_port(ca, monkeypatch, tmp_path):
    addresses(suite="http://home.example.com")
    switch_on(ca)
    certs.obtain()
    monkeypatch.setattr(config, "HTTPS_PORT", 0)  # HTTPS_PORT=off in the machine's file
    certs.start(free=lambda port: True)
    assert not certs.serving() and certs.tick() == ""
    monkeypatch.setattr(config, "HTTPS_PORT", 443)
    certs.start(free=lambda port: False)  # something else holds 443 on this machine: a reverse proxy, another copy
    assert certs.serving() and certs.PAGES_PORT == 0 and "port 443 is taken" in certs.NOTE and certs.status()["note"] == certs.NOTE
    assert db.get_setting("PUBLIC_URL") == "http://home.example.com"  # the pages are not over HTTPS here: their address stays
    monkeypatch.setattr(config, "PORT", 443)  # the pages' one port is the HTTPS one
    certs.start(free=lambda port: False)
    assert certs.PAGES_PORT == 443 and certs.NOTE == ""
    monkeypatch.setattr(config, "PORT", 80)
    # a stored certificate whose key is not its own, or that ran out, is as good as none
    key, chain = certs.bundle()
    credentials.put("", certs.BUNDLE, acme.new_key() + chain)
    certs.start(free=lambda port: True)
    assert not certs.serving()
    old_key, old = ca.issue(["home.example.com"], lifetime=3600, start=datetime(2020, 1, 1, tzinfo=timezone.utc))
    credentials.put("", certs.BUNDLE, old_key + old)
    certs.start(free=lambda port: True)
    assert not certs.serving() and certs.due() == "it runs out on 2020-01-01"
    # one the web server cannot load does not send the copy round in circles
    credentials.put("", certs.BUNDLE, key + chain)
    monkeypatch.setattr("iosuite_shared.serve.context", lambda *a: (_ for _ in ()).throw(OSError("no such cipher")))
    restarts = []
    certs.start(free=lambda port: True)
    assert not certs.serving() and "could not be loaded" in certs.NOTE and certs.UNUSABLE
    certs.tick(restart=lambda: restarts.append(1))
    assert not restarts


def test_the_machine_s_own_files(ca, monkeypatch, tmp_path):
    key, chain = ca.issue(["nas.example.com"])
    (tmp_path / "c.pem").write_text(chain)
    (tmp_path / "k.pem").write_text(key)
    monkeypatch.setattr(config, "TLS_CERT_FILE", str(tmp_path / "c.pem"))
    monkeypatch.setattr(config, "TLS_KEY_FILE", str(tmp_path / "k.pem"))
    addresses(suite="http://nas.example.com")
    certs.start(free=lambda port: True)
    assert certs.SERVING == (str(tmp_path / "c.pem"), str(tmp_path / "k.pem")) and certs.LOADED == "files" and certs.NAMES == ("nas.example.com",)
    assert certs.PAGES_PORT == 443 and certs.status()["ownFiles"]
    assert db.get_setting("PUBLIC_URL") == "http://nas.example.com"  # the addresses are the admin's, as before
    restarts, reloads = [], []
    switch_on(ca)  # the suite's certificate beside: asked for and kept, and this machine goes on with its own
    assert certs.tick(lambda *a: reloads.append(a), lambda: restarts.append(1)).startswith("asked for a certificate")
    assert certs.bundle() and not restarts and not reloads and certs.LOADED == "files"
    (tmp_path / "k.pem").write_text(acme.new_key())  # a key that is not the certificate's
    certs.start(free=lambda port: True)
    assert not certs.serving() and "could not be loaded" in certs.NOTE


def test_a_running_copy_is_brought_in_line(ca):
    addresses(suite="https://home.example.com")
    restarts, reloads = [], []
    certs.attach(lambda file, key: reloads.append((file, key)), lambda: restarts.append(1))
    certs.start(free=lambda port: True)
    assert certs.tick() == "" and not restarts  # nothing switched on: nothing to do
    switch_on(ca)
    assert certs.tick().startswith("asked for a certificate (there is none yet)")
    assert restarts == [1] and not reloads  # the HTTPS doors have to be opened: the copy starts again
    certs.start(free=lambda port: True)
    first = certs.LOADED
    assert certs.tick() == "" and restarts == [1]
    # renewed (by this copy or another): loaded into the open doors, no restart
    certs.obtain()
    assert certs.tick() == "loaded the renewed certificate" and reloads == [(str(config.DATA_DIR / "tls" / "suite.pem"), None)]
    assert certs.LOADED == certs.certificate()["fingerprint"] != first and restarts == [1]
    written = open(reloads[0][0]).read()
    assert acme.describe(written[written.index("-----BEGIN CERTIFICATE"):])["fingerprint"] == certs.LOADED  # the file holds the new one
    # switched off: the doors have to be closed
    certs.save({"on": False})
    assert certs.tick() == "starting again" and restarts == [1, 1]
    # the button: asked now, whatever tick() would wait for
    certs.save({"on": True})
    certs.start(free=lambda port: True)
    before = certs.LOADED
    assert certs.ask_now()["names"] == ["home.example.com"] and certs.LOADED != before and len(reloads) == 2


# ---- the panel and the command
def test_the_panel_s_routes(ca):
    from iosuite_shared.tests.test_admin import make_app, signed_in
    app = make_app()
    users.create("alex", "secret123", suite_admin=True)
    users.create("ann", "secret123", "admin", "iostart")
    c = signed_in(app, "alex", "secret123")
    at = "/api/suite-admin/certificate"
    assert c.get(at).json()["on"] is False
    addresses(suite="http://home.example.com")
    r = c.put(at, json={"on": True, "ca": ca.directory, "email": "alex@example.com", "token": "cf-secret"})
    d = r.json()
    assert r.status_code == 200 and d["on"] and d["wanted"] == ["home.example.com"] and d["due"] == "there is none yet" and d["tokenSet"]
    assert "cf-secret" not in r.text and "cf-secret" not in c.get(at).text  # a key goes in and never comes back
    r = c.put(at, json={"proof": "smoke"})
    assert r.status_code == 400 and r.json()["detail"] == "The proof is http or cloudflare"
    restarts = []
    certs.attach(None, lambda: restarts.append(1))
    r = c.post(at)
    assert r.status_code == 200 and r.json()["certificate"]["names"] == ["home.example.com"] and r.json()["due"] == ""
    assert restarts == [1]  # this server has its HTTPS ports to open
    ca.fail["home.example.com"] = "Timeout during connect (likely firewall problem)"
    r = c.post(at)
    assert r.status_code == 502 and r.json()["detail"] == "The certificate was not given. home.example.com: Timeout during connect (likely firewall problem)"
    assert c.get(at).json()["state"]["ok"] is False
    ca.fail.clear()
    c.put(at, json={"on": False})
    r = c.post(at)
    assert r.status_code == 200 and r.json()["state"]["ok"]  # asked for by hand: also while it is off, to have one ready
    db.set_setting("PUBLIC_URL", None, "")
    assert c.post(at).status_code == 400
    other = signed_in(app, "ann", "secret123")  # an app's admin is not the suite's
    assert other.get(at).status_code == 403 and other.put(at, json={"on": True}).status_code == 403 and other.post(at).status_code == 403


def test_the_command(ca, capsys, tmp_path):
    from iosuite_shared import cli
    cli.main(["cert"])
    out = capsys.readouterr().out
    assert "the suite's certificate: off" in out and "no name yet" in out and "stored       none" in out
    addresses(suite="http://home.example.com")
    (tmp_path / "token").write_text("cf-secret\n")
    cli.main(["cert", "--on", "--ca", ca.directory, "--email", "alex@example.com", "--names", "photos.example.com", "--token-file", str(tmp_path / "token")])
    out = capsys.readouterr().out
    assert "certificate: on" in out and "for          home.example.com, photos.example.com" in out and "due          there is none yet" in out
    assert credentials.get("", certs.CF_TOKEN) == "cf-secret" and "cf-secret" not in out
    cli.main(["cert", "--now"])
    out = capsys.readouterr().out
    assert "stored       for home.example.com, photos.example.com; from ioSuite test authority; holds until " in out and ": given" in out
    assert "due   " not in out
    ca.fail["photos.example.com"] = "No valid IP addresses found for photos.example.com"
    with pytest.raises(SystemExit) as e:
        cli.main(["cert", "--now"])
    assert str(e.value) == "error: the certificate was not given. photos.example.com: No valid IP addresses found for photos.example.com"
    with pytest.raises(SystemExit) as e:
        cli.main(["cert", "--names", "*.example.com"])
    assert "star" in str(e.value)
    cli.main(["cert", "--names", "", "--staging", "--cloudflare", "--off"])
    s = certs.settings()
    assert s == {"on": False, "email": "alex@example.com", "ca": "staging", "proof": "cloudflare", "names": []}
    assert "test authority" in capsys.readouterr().out
