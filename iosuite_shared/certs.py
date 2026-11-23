"""The suite's own certificate: asked for and renewed by the suite (ACME: Let's Encrypt or another authority), kept in
the Shared ioSuite database, and served by every copy, so the suite answers HTTPS without a reverse proxy in front.

What a suite admin sets (Settings › Global settings › Certificate, or `iosuite cert`) is one row of ios_settings
(app '', "certificate"), JSON:

    on      ask for a certificate and serve it
    email   where the authority writes when something is wrong with the account (optional)
    ca      letsencrypt | staging (Let's Encrypt's test authority: certificates browsers do not trust, generous
            limits) | the address of another ACME directory
    proof   http: the authority asks port 80 of each name, which has to reach this suite from the internet
            cloudflare: a TXT record made through Cloudflare's API with the key cloudflare_dns_token; the names need
            not be reachable from outside, and a name with a star (*.example.com) can be asked for
    names   names beside the ones the suite's addresses say

The names are the hosts of every address stored for the suite and its apps (PUBLIC_URL, SYNC_URL, MCP_URL) and
`names`. Beside the row:

    ios_credentials ('', made_certificate)   the certificate: its private key, then the certificate and its chain (PEM)
    ios_credentials ('', made_acme_account)  the account's key at the authority
    ios_credentials ('', cloudflare_dns_token)
    ios_settings ('', certificate_state)     JSON: when it was last asked, by which copy, how it went
    ios_settings ('', certificate_addresses) JSON: the addresses that said http:// and say https:// since (below)
    ios_settings ('', acme_<hash>)           a proof for http, for the minutes the authority looks: any copy answers it

Keys named made_… are the suite's own making: Keys and tokens does not list them and nobody types one.

**Serving.** A copy decides as it starts (start()): with a certificate (the suite's, or the machine's own files
TLS_CERT_FILE and TLS_KEY_FILE) it answers HTTPS: the pages on HTTPS_PORT (443), devices and MCP on the ports they
have. Nothing that worked without HTTPS stops working: PORT (80) stays as it is, and the ports that answer HTTPS go
on answering plain HTTP too (iosuite_shared.serve), so the suite's other servers, a reverse proxy and a device set up
with the server's address are served as before. A browser that asks the pages without HTTPS by one of the
certificate's names is sent on to HTTPS (iosuite_shared.host), and an address stored as http:// for such a name says
https:// from then on (and http:// again when the certificate is switched off). HTTPS_PORT=off in a machine's file
keeps that copy plain. A copy that finds the pages' HTTPS port taken (a reverse proxy on the same machine, another
copy) goes on without it and says so.

**Renewing.** Every copy looks every few minutes (tick()): a certificate is asked for when there is none, when a name
was added, when another authority was chosen, or when a third of its life is left; one copy at a time (a lock in the
database), and after a failure not again within the hour. A copy that serves an older certificate than the stored
one loads the new one without restarting; a copy that has to open or close its HTTPS doors ends, and the service
manager starts it again.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from iosuite_shared import acme, config, credentials, db
from iosuite_shared.errors import Invalid

log = logging.getLogger("iosuite_shared.certs")

ROW, STATE, LOCK, MOVED = "certificate", "certificate_state", "certificate_lock", "certificate_addresses"
BUNDLE, ACCOUNT, CF_TOKEN = "made_certificate", "made_acme_account", "cloudflare_dns_token"
KEYS = [{"name": CF_TOKEN, "label": "Cloudflare API token for the certificate", "hint": "Zone › DNS › Edit for the zones of the suite's names"}]
ADDRESSES = ("PUBLIC_URL", "SYNC_URL", "MCP_URL")
CHALLENGE_PATH = "/.well-known/acme-challenge/"
TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
HOSTNAME = re.compile(r"^(\*\.)?([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]([a-z0-9-]{0,61}[a-z0-9])$")
NOT_PUBLIC = (".local", ".lan", ".internal", ".localhost", ".home.arpa", ".localdomain")
LOCK_S = 900          # a copy that died while asking holds the others up this long at most
AGAIN_S = 3600        # after a failure: the authorities count failures by the hour
EVERY_S = 120         # how often a copy looks (tick)
DEFAULTS = {"on": False, "email": "", "ca": "letsencrypt", "proof": "http", "names": []}

# what this copy serves, settled by start(): (certificate file, key file or None), and which certificate that is
SERVING: tuple | None = None
LOADED: str = ""       # the fingerprint of the certificate loaded ("files": the machine's own)
NAMES: tuple = ()      # its names
PAGES_PORT: int = 0    # the pages' HTTPS port as this copy opens it (0: it serves no certificate, or the port is taken)
UNUSABLE: str = ""     # the fingerprint of a stored certificate this machine could not load: not tried in circles
NOTE: str = ""         # what stands in the way on this machine, for the panel
HOOKS: dict = {}       # reload(certfile, keyfile) and restart(), given by the host (attach())


# ---- what the admin set
def settings() -> dict:
    s = db.json_load(db.get_setting(ROW, "", ""), None)
    out = dict(DEFAULTS)
    if isinstance(s, dict):
        out.update({k: s[k] for k in DEFAULTS if k in s})
    out["names"] = [n for n in out.get("names") or [] if isinstance(n, str)]
    return out


def _hostname(value: str) -> str:
    h = str(value or "").strip().lower().rstrip(".")
    try:
        h = h.encode("idna").decode("ascii") if not h.startswith("*.") else "*." + h[2:].encode("idna").decode("ascii")
    except UnicodeError:
        raise Invalid(f"{value} is not a name a certificate can be for") from None
    if not HOSTNAME.match(h) or len(h) > 253:
        raise Invalid(f"{value} is not a name a certificate can be for (home.example.com)")
    return h


def directory(ca: str) -> str:
    return {"letsencrypt": acme.LETSENCRYPT, "staging": acme.STAGING}.get(ca, ca)


def save(body: dict, by: str = None) -> dict:
    """Store what the admin chose (only the fields given), and the Cloudflare token when one is given."""
    s = settings()
    if "on" in body:
        s["on"] = bool(body["on"])
    if "email" in body:
        email = str(body["email"] or "").strip()
        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise Invalid("That is not an email address")
        s["email"] = email
    if "ca" in body:
        ca = str(body["ca"] or "").strip() or "letsencrypt"
        if ca not in ("letsencrypt", "staging"):
            u = urlsplit(ca)
            inside = u.hostname in ("127.0.0.1", "localhost", "::1")
            if u.scheme not in ("https", "http") or not u.hostname or (u.scheme == "http" and not inside):
                raise Invalid("The authority is Let's Encrypt, its test authority, or the https:// address of an ACME directory")
        s["ca"] = ca
    if "proof" in body:
        if body["proof"] not in ("http", "cloudflare"):
            raise Invalid("The proof is http or cloudflare")
        s["proof"] = body["proof"]
    if "names" in body:
        given = body["names"]
        if isinstance(given, str):
            given = re.split(r"[,\s]+", given)
        s["names"] = list(dict.fromkeys(_hostname(n) for n in given or [] if str(n).strip()))
    if s["proof"] == "http" and any(n.startswith("*.") for n in s["names"]):
        raise Invalid("A name with a star can only be proven through DNS: choose Cloudflare, or name each host")
    if body.get("token"):
        credentials.declare("", KEYS)
        credentials.put("", CF_TOKEN, str(body["token"]).strip(), by=by)
    if s["on"] and s["proof"] == "cloudflare" and not credentials.get("", CF_TOKEN):
        raise Invalid("The proof through Cloudflare needs an API token (Zone › DNS › Edit)")
    db.set_setting(ROW, json.dumps(s), "")
    if not s["on"]:
        _to_http()
    return status()


# ---- the names
def certifiable(host: str) -> bool:
    """A name a public authority can give a certificate for: not an address, not a name of the home network."""
    h = (host or "").lower().rstrip(".")
    if "." not in h or h.endswith(NOT_PUBLIC):
        return False
    try:
        ipaddress.ip_address(h.strip("[]"))
        return False
    except ValueError:
        return bool(HOSTNAME.match(h))


def addresses() -> list:
    """(app, setting, address) of every address stored for the suite ('') and its apps."""
    rows = db.q("SELECT app, name, value FROM ios_settings WHERE name IN %s ORDER BY app, name", (ADDRESSES,))
    return [(r["app"], r["name"], r["value"]) for r in rows if (r["value"] or "").strip()]


def wanted() -> list:
    """The names the certificate is for: the suite's own first, then the others."""
    first, rest = [], []
    for app, name, url in addresses():
        h = (urlsplit(url if "://" in url else "https://" + url).hostname or "").lower()
        if certifiable(h):
            (first if (app, name) == ("", "PUBLIC_URL") else rest).append(h)
    extra = settings()["names"]
    names = list(dict.fromkeys(first + sorted(set(rest)) + extra))
    stars = [n for n in names if n.startswith("*.")]
    return [n for n in names if n in stars or not acme.covers(stars, n)]  # what a star covers is not asked twice


# ---- the certificate
def bundle() -> tuple | None:
    """(private key, certificate and chain), both PEM, as stored; None when there is none."""
    v = credentials.get("", BUNDLE)
    at = v.find("-----BEGIN CERTIFICATE-----")
    return (v[:at].strip() + "\n", v[at:].strip() + "\n") if at > 0 else None


def certificate() -> dict | None:
    """What the stored certificate says (acme.describe): names, from, until, issuer, fingerprint."""
    b = bundle()
    if not b:
        return None
    try:
        return acme.describe(b[1])
    except Exception:  # noqa: BLE001 - not a certificate: as good as none
        return None


def state() -> dict:
    s = db.json_load(db.get_setting(STATE, "", ""), None)
    return s if isinstance(s, dict) else {}


def _say(**what) -> None:
    from iosuite_shared import suite
    db.set_setting(STATE, json.dumps({"at": int(time.time()), "copy": suite.copy_name(), **what}), "")


def due(now: float = None) -> str:
    """Why a certificate should be asked for now; "" when none should."""
    s = settings()
    if not s["on"]:
        return ""
    want = wanted()
    if not want:
        return ""
    have = certificate()
    if not have:
        return "there is none yet"
    missing = [n for n in want if not acme.covers(have["names"], n)]
    if missing:
        return f"it does not hold for {', '.join(missing)}"
    asked = state()
    if asked.get("ok") and asked.get("ca") and asked["ca"] != s["ca"]:
        return "another authority was chosen"
    now = time.time() if now is None else now
    if now >= have["until"] - (have["until"] - have["from"]) / 3:
        return f"it runs out on {acme.when(have['until'])}"
    return ""


def may_try(now: float = None) -> bool:
    """Not within the hour of a failure (the authorities count them)."""
    s = state()
    return bool(s.get("ok", True)) or (time.time() if now is None else now) - (s.get("at") or 0) >= AGAIN_S


def _lock() -> bool:
    """One copy asks at a time. The lock is a row saying who and since when; one older than LOCK_S is taken over."""
    from iosuite_shared import suite
    me = f"{suite.copy_name()}:{os.getpid()}:{secrets.token_hex(4)}:{int(time.time())}"
    old = int(time.time()) - LOCK_S
    db.ex("INSERT INTO ios_settings (app, name, value) VALUES ('', %s, %s) ON DUPLICATE KEY UPDATE "
          "value = IF(CAST(SUBSTRING_INDEX(value, ':', -1) AS UNSIGNED) < %s, VALUES(value), value)", (LOCK, me, old))
    r = db.one("SELECT value FROM ios_settings WHERE app = '' AND name = %s", (LOCK,))
    return (r or {}).get("value") == me


def _unlock() -> None:
    db.ex("DELETE FROM ios_settings WHERE app = '' AND name = %s", (LOCK,))


def obtain(say=None) -> dict:
    """Ask the authority for a certificate for wanted() and store it. Invalid when there is nothing to ask for or
    another copy is asking; acme.Problem with the authority's own words when it says no (kept in state() too)."""
    s, want = settings(), wanted()
    say = say or (lambda text: log.info("%s", text))
    if not want:
        raise Invalid("There is no name to ask a certificate for: give the suite an address (https://home.example.com), or add a name")
    if s["proof"] == "http" and any(n.startswith("*.") for n in want):
        raise Invalid("A name with a star can only be proven through DNS")
    if not _lock():
        raise Invalid("Another server of the suite is asking for the certificate right now")
    try:
        account = credentials.get("", ACCOUNT)
        if not account:
            account = acme.new_key()
            credentials.put("", ACCOUNT, account, by="certificate")
        client = acme.Client(directory(s["ca"]), account, s["email"], cafile=config.ACME_CA_FILE or None, log=say)
        if s["proof"] == "cloudflare":
            dns = Cloudflare(credentials.get("", CF_TOKEN))
            kind, publish, remove = "dns-01", dns.publish, dns.remove
        else:
            kind, publish, remove = "http-01", _publish, _remove
        say(f"asking {urlsplit(directory(s['ca'])).hostname} for a certificate for {', '.join(want)}")
        try:
            key, chain = client.certificate(want, kind, publish, remove)
        except acme.Problem as e:
            _say(ok=False, error=e.detail, kind=e.kind, names=want, ca=s["ca"])
            raise
        credentials.put("", BUNDLE, key.strip() + "\n" + chain, by="certificate")
        credentials.forget()
        have = acme.describe(chain)
        _say(ok=True, names=have["names"], ca=s["ca"], until=have["until"])
        say(f"the certificate holds until {acme.when(have['until'])}")
        return have
    finally:
        _unlock()


def moved() -> list:
    """The addresses that said http:// and say https:// since the suite has its certificate: {app, name, from, to}."""
    v = db.json_load(db.get_setting(MOVED, "", ""), None)
    return [m for m in v if isinstance(m, dict)] if isinstance(v, list) else []


def _to_https(names) -> list:
    """The addresses stored as http:// for a name the certificate holds for say https:// from now on: the pages' at
    the HTTPS port, a device's or MCP's at the port it has, when that is this server's own (an address at another
    port goes through something in front of the suite, and is left as it is). What changed is kept (moved()), so
    that switching the certificate off puts back what was there."""
    changed = []
    for app, name, url in addresses():
        u = urlsplit(url)
        if u.scheme != "http" or not u.hostname or not acme.covers(names, u.hostname):
            continue
        port = u.port or 80
        if name == "PUBLIC_URL" and port in (80, config.PORT):
            port = PAGES_PORT
        elif port != {"SYNC_URL": config.SYNC_PORT, "MCP_URL": config.MCP_PORT}.get(name):
            continue  # a port something in front of the suite maps: left as it is
        host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
        new = f"https://{host}{'' if port == 443 else f':{port}'}{u.path.rstrip('/')}"
        db.set_setting(name, new, app)
        changed.append({"app": app, "name": name, "from": url, "to": new})
        log.info("%s of %s says %s now (it said %s)", name, app or "the suite", new, url)
    if changed:
        keep = [m for m in moved() if (m.get("app"), m.get("name")) not in {(c["app"], c["name"]) for c in changed}]
        db.set_setting(MOVED, json.dumps(keep + changed), "")
    return changed


def _to_http() -> list:
    """The certificate is off: the addresses _to_https() changed say what they said before, unless somebody changed
    them since."""
    back = []
    for m in moved():
        now = db.one("SELECT value FROM ios_settings WHERE app = %s AND name = %s", (m.get("app") or "", m.get("name") or ""))
        if now and now["value"] == m.get("to"):
            db.set_setting(m["name"], m["from"], m.get("app") or "")
            back.append(m)
    db.set_setting(MOVED, None, "")
    return back


# ---- the proof over http: a row any copy answers from
def _row(token: str) -> str:
    return "acme_" + hashlib.sha256(token.encode("ascii", "replace")).hexdigest()[:40]


def _publish(kind: str, name: str, token: str, value: str) -> None:
    db.set_setting(_row(token), value, "")


def _remove(kind: str, name: str, token: str) -> None:
    db.set_setting(_row(token), None, "")


def proof(path: str) -> str | None:
    """What to answer the authority at this path (/.well-known/acme-challenge/<token>); None for a token nobody asked."""
    token = path[len(CHALLENGE_PATH):] if path.startswith(CHALLENGE_PATH) else ""
    if not TOKEN.match(token):
        return None
    r = db.one("SELECT value FROM ios_settings WHERE app = '' AND name = %s", (_row(token),))
    return (r or {}).get("value") or None


# ---- the proof through Cloudflare's DNS
class Cloudflare:
    """TXT records _acme-challenge.<name> in the zone the name is in, made with an API token that may edit its DNS."""
    API = "https://api.cloudflare.com/client/v4"
    DOH = "https://cloudflare-dns.com/dns-query"

    def __init__(self, token: str, api: str = None, doh: str = None, wait: float = 90):
        if not token:
            raise Invalid("The proof through Cloudflare needs an API token (Zone › DNS › Edit)")
        self.token, self.api, self.doh, self.wait = token, (api or self.API).rstrip("/"), doh if doh is not None else self.DOH, wait
        self.made: dict = {}  # (name, token) -> (zone id, record id)

    def _call(self, method: str, path: str, body: dict = None):
        req = urllib.request.Request(self.api + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": acme.AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                answer = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                errors = json.loads(e.read() or b"{}").get("errors") or []
            except ValueError:
                errors = []
            said = "; ".join(str(x.get("message") or x) for x in errors) or f"it answered {e.code}"
            raise acme.Problem(f"Cloudflare: {said}", "dns", e.code) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise acme.Problem(f"Cloudflare could not be reached ({getattr(e, 'reason', e)})", "connection") from None
        return answer.get("result")

    def zone(self, name: str) -> str:
        labels = name.split(".")
        for i in range(len(labels) - 1):
            found = self._call("GET", f"/zones?name={'.'.join(labels[i:])}")
            if found:
                return found[0]["id"]
        raise acme.Problem(f"Cloudflare: the token sees no zone for {name}", "dns")

    def publish(self, kind: str, name: str, token: str, value: str) -> None:
        host = name[2:] if name.startswith("*.") else name
        record = f"_acme-challenge.{host}"
        zone = self.zone(host)
        made = self._call("POST", f"/zones/{zone}/dns_records", {"type": "TXT", "name": record, "content": value, "ttl": 60,
                                                                 "comment": "ioSuite: proof for a certificate; removed after"})
        self.made[(name, token)] = (zone, (made or {}).get("id"))
        self._seen(record, value)

    def _seen(self, record: str, value: str) -> None:
        """Wait until the record is answered (asked over DNS-over-HTTPS), so the authority finds it at its first look."""
        if not self.doh:
            return
        until = time.time() + self.wait
        while time.time() < until:
            try:
                req = urllib.request.Request(f"{self.doh}?name={record}&type=TXT", headers={"Accept": "application/dns-json", "User-Agent": acme.AGENT})
                with urllib.request.urlopen(req, timeout=10) as r:
                    got = [str(a.get("data") or "").strip('"') for a in json.loads(r.read() or b"{}").get("Answer") or []]
                if value in got:
                    time.sleep(2 if self.wait > 5 else 0)
                    return
            except (urllib.error.URLError, OSError, ValueError):
                pass
            time.sleep(3 if self.wait > 5 else 0.05)
        # not seen from here: the authority looks anyway, and says so if it does not find it

    def remove(self, kind: str, name: str, token: str) -> None:
        zone, rid = self.made.pop((name, token), (None, None))
        if zone and rid:
            self._call("DELETE", f"/zones/{zone}/dns_records/{rid}")


# ---- serving
def serving() -> bool:
    """Whether this copy answers HTTPS itself (settled as it started)."""
    return SERVING is not None


def _file() -> Path:
    return Path(config.DATA_DIR) / "tls" / "suite.pem"


def _write(key: str, chain: str) -> Path:
    """The certificate as a file the web server loads: the key and the chain in one, readable by the service only."""
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(f.parent, 0o700)
    except OSError:
        pass
    tmp = f.with_suffix(".new")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as out:
        out.write(key.strip() + "\n" + chain)
    os.replace(tmp, f)
    return f


def _usable(b: tuple) -> dict | None:
    """What the stored certificate says, when its key is the certificate's own and it has not run out."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        cert = x509.load_pem_x509_certificate(b[1].encode("ascii"))
        key = serialization.load_pem_private_key(b[0].encode("ascii"), password=None)
        same = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) == \
            key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        have = acme.describe(b[1])
        return have if same and have["until"] > time.time() else None
    except Exception:  # noqa: BLE001
        return None


def _should() -> tuple:
    """(the certificate this copy should serve as (key, chain), what it says), or (None, None) for plain."""
    if not config.HTTPS_PORT or not settings()["on"]:
        return None, None
    b = bundle()
    have = _usable(b) if b else None
    return (b, have) if have else (None, None)


def start(free=None) -> None:
    """Settle what this copy serves, before it opens its doors: the machine's own files, else the suite's
    certificate, else plain. `free(port)`: whether the pages' HTTPS port can be opened here (by default asked of
    iosuite_shared.serve)."""
    global SERVING, LOADED, NAMES, PAGES_PORT, UNUSABLE, NOTE
    from iosuite_shared import serve
    SERVING, LOADED, NAMES, PAGES_PORT, UNUSABLE, NOTE = None, "", (), 0, "", ""
    if not config.HTTPS_PORT:  # HTTPS_PORT=off: this copy stays plain
        return
    want = ""
    if config.TLS_CERT_FILE and config.TLS_KEY_FILE:
        serving, want = (config.TLS_CERT_FILE, config.TLS_KEY_FILE), "files"
        try:
            names = tuple(acme.describe(Path(config.TLS_CERT_FILE).read_text(encoding="ascii"))["names"])
        except Exception:  # noqa: BLE001 - said below, when it cannot be loaded either
            names = ()
    else:
        try:
            b, have = _should()
        except Exception as x:  # noqa: BLE001 - the database is away: plain, until tick() sees otherwise
            log.warning("the suite's certificate could not be read (%s): answering without HTTPS for now", x)
            return
        if not b:
            return
        serving, want, names = (str(_write(*b)), None), have["fingerprint"], tuple(have["names"])
    try:
        serve.context(*serving)
    except Exception as x:  # noqa: BLE001 - a file that is no certificate, a key that is not its own
        UNUSABLE = want
        NOTE = f"the certificate could not be loaded on this server ({x})"
        log.error("%s: answering without HTTPS", NOTE)
        return
    SERVING, LOADED, NAMES = serving, want, names
    if config.HTTPS_PORT == config.PORT or (free or (lambda port: serve.free(config.HOST, port)))(config.HTTPS_PORT):
        PAGES_PORT = config.HTTPS_PORT
    else:
        NOTE = (f"port {config.HTTPS_PORT} is taken by another program on this server: the pages are not answered over HTTPS here "
                f"(HTTPS_PORT in the machine's file names another port)")
        log.warning("%s; devices and MCP are", NOTE)
    if want != "files" and PAGES_PORT:
        try:
            _to_https(NAMES)
        except Exception as x:  # noqa: BLE001 - the addresses stay as they are: a page asked over http is sent on all the same
            log.warning("the suite's addresses could not be changed to https (%s)", x)


def attach(reload=None, restart=None) -> None:
    """What the host gives tick() to bring a running copy in line with."""
    HOOKS.update(reload=reload, restart=restart)


def named(host: str) -> bool:
    """Whether the certificate this copy serves holds for this name."""
    return bool(host) and acme.covers(NAMES, host.lower())


def tick(reload=None, restart=None) -> str:
    """One look (every EVERY_S seconds, in every copy): ask for a certificate when one is due, then bring this copy
    in line with what is stored. `reload(certfile, keyfile)`: load a renewed certificate into the open HTTPS doors;
    `restart()`: end the copy so that it starts again with or without them (both from attach() when not given).
    Returns what it did, for the log."""
    global LOADED, NAMES
    reload, restart = reload or HOOKS.get("reload"), restart or HOOKS.get("restart")
    did = ""
    why = due()
    if why and may_try():
        try:
            obtain()
            did = f"asked for a certificate ({why})"
        except Invalid as e:  # another copy is at it, or there is nothing to ask for
            did = str(e)
        except acme.Problem as e:
            log.warning("the certificate was not given (%s): %s; tried again in an hour", why, e.detail)
            did = f"not given: {e.detail}"
    if LOADED == "files" or not config.HTTPS_PORT:
        return did
    b, have = _should()
    want = have["fingerprint"] if have else ""
    if want == LOADED or (want and want == UNUSABLE):
        return did
    if want and SERVING and reload:
        f = _write(*b)
        reload(str(f), None)
        LOADED, NAMES = want, tuple(have["names"])
        log.info("the renewed certificate is loaded (it holds until %s)", acme.when(have["until"]))
        return did or "loaded the renewed certificate"
    if restart:
        log.warning("%s: starting again", "the suite has a certificate now: this server answers HTTPS" if want else "the suite's certificate is off: this server answers without HTTPS")
        restart()
    return did or "starting again"


def ask_now() -> dict:
    """Ask for a certificate now, whatever tick() would wait for (the panel's button, `iosuite cert --now`), and bring
    this copy in line. The other copies follow at their next look."""
    have = obtain()
    tick()
    return have


# ---- for the panel and the command
def status() -> dict:
    s = settings()
    have = certificate()
    return {**s, "wanted": wanted(), "certificate": have, "state": state(), "due": due(), "tokenSet": credentials.is_set("", CF_TOKEN),
            "serving": serving(), "ownFiles": LOADED == "files", "httpsPort": config.HTTPS_PORT, "pagesPort": PAGES_PORT, "port": config.PORT,
            "note": NOTE, "moved": moved()}
