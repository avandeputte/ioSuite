"""A certificate authority for the tests: enough of ACME (RFC 8555) to ask a certificate from, on this machine, with
a root of its own that nothing trusts. It checks what a real one checks: every request is signed by the account's
key, carries a nonce it gave out and names the address it was sent to; a proof is looked for where the client put
it; the signing request names exactly what was ordered.

    with Authority(fetch=lambda name, path: ...) as ca:      # what http://<name><path> answers, None for nothing
        acme.Client(ca.directory, acme.new_key()).certificate(["home.example.com"], "http-01", publish)
    key, chain = ca.issue(["home.example.com"])              # a certificate without the asking

`fetch`: where an http-01 proof is looked for (by default a real request to 127.0.0.1:`http_port` with the name as
Host). `txt(record)`: what DNS answers for a TXT record. `fail`: {name: why} refuses a name's proof; `slow`: how many
times a proof and an order are still "processing" when asked; `bad_nonces`: refuse that many requests with badNonce;
`offer`: the proofs it offers.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.x509.oid import NameOID

ERR = "urn:ietf:params:acme:error:"
NAME = "ioSuite test authority"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Refused(Exception):
    def __init__(self, status: int, kind: str, detail: str):
        super().__init__(detail)
        self.status, self.kind, self.detail = status, kind, detail


class Authority:
    def __init__(self, fetch=None, http_port: int = 80, txt=None, lifetime: float = 90 * 86400):
        self.key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, NAME), x509.NameAttribute(NameOID.COMMON_NAME, NAME + " root")])
        now = datetime.now(timezone.utc)
        self.root = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(self.key.public_key())
                     .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=3650))
                     .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                     .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                                  key_encipherment=False, data_encipherment=False, key_agreement=False,
                                                  encipher_only=False, decipher_only=False), critical=True)
                     .add_extension(x509.SubjectKeyIdentifier.from_public_key(self.key.public_key()), critical=False)
                     .sign(self.key, hashes.SHA256()))
        self.fetch = fetch or self._fetch
        self.http_port, self.txt, self.lifetime = http_port, txt or (lambda record: []), lifetime
        self.fail: dict = {}
        self.slow = 0
        self.bad_nonces = 0
        self.offer = ("http-01", "dns-01")
        self.accounts: dict = {}   # kid -> {jwk, contact}
        self.orders: dict = {}
        self.authzs: dict = {}
        self.certs: dict = {}
        self.nonces: set = set()
        self.seen: list = []       # (path, payload) of every signed request
        self.looked: list = []     # (kind, name) of every proof it looked for
        self._lock = threading.RLock()
        self._n = 0
        self.server: ThreadingHTTPServer | None = None
        self.url = ""

    # ---- running
    def __enter__(self):
        ca = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _answer(self, status: int, body=b"", kind: str = "application/json", headers: dict = None):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Replay-Nonce", ca.nonce())
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)

            def do_HEAD(self):
                self._answer(200 if self.path == "/nonce" else 404)

            def do_GET(self):
                if self.path == "/dir":
                    self._answer(200, {"newNonce": ca.url + "/nonce", "newAccount": ca.url + "/acct", "newOrder": ca.url + "/order",
                                       "meta": {"termsOfService": ca.url + "/terms"}})
                elif self.path == "/nonce":
                    self._answer(204)
                else:
                    self._answer(404, {"type": ERR + "malformed", "detail": "no such page"}, "application/problem+json")

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    with ca._lock:
                        status, body, headers = ca.signed(self.path, raw, self.headers.get("Content-Type") or "")
                except Refused as e:
                    return self._answer(e.status, {"type": ERR + e.kind, "detail": e.detail, "status": e.status}, "application/problem+json")
                if isinstance(body, str):
                    return self._answer(status, body.encode(), "application/pem-certificate-chain", headers)
                self._answer(status, body, "application/json", headers)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, name="test-authority", daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    @property
    def directory(self) -> str:
        return self.url + "/dir"

    def root_pem(self) -> str:
        return self.root.public_bytes(serialization.Encoding.PEM).decode("ascii")

    def nonce(self) -> str:
        n = secrets.token_urlsafe(16)
        self.nonces.add(n)
        return n

    def _id(self) -> str:
        self._n += 1
        return str(self._n)

    # ---- a signed request
    def signed(self, path: str, raw: bytes, content_type: str) -> tuple:
        if content_type.split(";")[0].strip() != "application/jose+json":
            raise Refused(415, "malformed", "a request is application/jose+json")
        try:
            jws = json.loads(raw)
            head = json.loads(unb64(jws["protected"]))
            signature = unb64(jws["signature"])
        except (ValueError, KeyError, TypeError):
            raise Refused(400, "malformed", "not a signed request") from None
        if head.get("alg") != "ES256" or head.get("url") != self.url + path:
            raise Refused(400, "malformed", "signed for another address, or with another algorithm")
        if head.get("nonce") not in self.nonces:
            raise Refused(400, "badNonce", "a nonce this authority did not give, or gave before")
        self.nonces.discard(head["nonce"])
        if self.bad_nonces > 0:
            self.bad_nonces -= 1
            raise Refused(400, "badNonce", "that nonce is no longer taken")
        if ("jwk" in head) == ("kid" in head):
            raise Refused(400, "malformed", "a request names its key or its account, one of the two")
        if "jwk" in head:
            if path != "/acct":
                raise Refused(400, "malformed", "only a new account names its key")
            key = head["jwk"]
        else:
            account = self.accounts.get(head["kid"])
            if not account:
                raise Refused(400, "accountDoesNotExist", "no such account")
            key = account["jwk"]
        try:
            public = ec.EllipticCurvePublicNumbers(int.from_bytes(unb64(key["x"]), "big"), int.from_bytes(unb64(key["y"]), "big"), ec.SECP256R1()).public_key()
            public.verify(utils.encode_dss_signature(int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")),
                          f"{jws['protected']}.{jws['payload']}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
        except (InvalidSignature, ValueError, KeyError):
            raise Refused(400, "malformed", "the signature is not this key's") from None
        payload = json.loads(unb64(jws["payload"])) if jws["payload"] else None  # None: a POST that only asks
        self.seen.append((path, payload))
        return self.answer(path, payload, key, head.get("kid"))

    @staticmethod
    def thumbprint(key: dict) -> str:
        return b64(hashlib.sha256(json.dumps({k: key[k] for k in ("crv", "kty", "x", "y")}, sort_keys=True, separators=(",", ":")).encode()).digest())

    def answer(self, path: str, payload, key: dict, kid) -> tuple:
        part = path.strip("/").split("/")
        if path == "/acct":
            mark = self.thumbprint(key)
            for url, a in self.accounts.items():
                if self.thumbprint(a["jwk"]) == mark:
                    return 200, {"status": "valid"}, {"Location": url}
            if not (payload or {}).get("termsOfServiceAgreed"):
                raise Refused(400, "userActionRequired", "the terms have to be agreed to")
            url = f"{self.url}/acct/{self._id()}"
            self.accounts[url] = {"jwk": key, "contact": (payload or {}).get("contact") or []}
            return 201, {"status": "valid", "contact": self.accounts[url]["contact"]}, {"Location": url}
        if path == "/order":
            names = [i["value"] for i in (payload or {}).get("identifiers") or [] if i.get("type") == "dns"]
            if not names:
                raise Refused(400, "malformed", "an order names what it is for")
            oid = self._id()
            authzs = []
            for n in names:
                aid = self._id()
                star = n.startswith("*.")
                token = secrets.token_urlsafe(24)
                self.authzs[aid] = {"name": n[2:] if star else n, "star": star, "status": "pending", "token": token, "kid": kid, "polls": 0,
                                    "kinds": [k for k in self.offer if not (star and k == "http-01")], "error": None, "asked": None}
                authzs.append(aid)
            self.orders[oid] = {"names": names, "authzs": authzs, "status": "pending", "kid": kid, "cert": None, "polls": 0}
            return 201, self._order(oid), {"Location": f"{self.url}/order/{oid}"}
        if part[0] == "authz" and len(part) == 2 and part[1] in self.authzs:
            a = self.authzs[part[1]]
            if a["status"] == "processing":
                a["polls"] += 1
                if a["polls"] > self.slow:
                    self._look(a, key)
            return 200, self._authz(part[1]), {"Retry-After": "1"}
        if part[0] == "chall" and len(part) == 3 and part[1] in self.authzs and part[2] in self.authzs[part[1]]["kinds"]:
            a = self.authzs[part[1]]
            if a["status"] == "pending":
                a["status"], a["asked"] = "processing", part[2]
                if not self.slow:
                    self._look(a, key)
            return 200, self._challenge(part[1], part[2]), {}
        if part[0] == "order" and len(part) == 3 and part[2] == "finalize" and part[1] in self.orders:
            return 200, self._finalize(part[1], payload or {}), {"Location": f"{self.url}/order/{part[1]}"}
        if part[0] == "order" and len(part) == 2 and part[1] in self.orders:
            o = self.orders[part[1]]
            if o["status"] == "processing":
                o["polls"] += 1
                if o["polls"] > self.slow:
                    o["status"] = "valid"
            return 200, self._order(part[1]), {"Retry-After": "1"}
        if part[0] == "cert" and len(part) == 2 and part[1] in self.certs:
            return 200, self.certs[part[1]], {}
        raise Refused(404, "malformed", "no such page")

    def _order(self, oid: str) -> dict:
        o = self.orders[oid]
        if o["status"] == "pending" and all(self.authzs[a]["status"] == "valid" for a in o["authzs"]):
            o["status"] = "ready"
        if o["status"] == "pending" and any(self.authzs[a]["status"] == "invalid" for a in o["authzs"]):
            o["status"] = "invalid"
        out = {"status": o["status"], "identifiers": [{"type": "dns", "value": n} for n in o["names"]],
               "authorizations": [f"{self.url}/authz/{a}" for a in o["authzs"]], "finalize": f"{self.url}/order/{oid}/finalize"}
        if o["status"] == "valid":
            out["certificate"] = f"{self.url}/cert/{o['cert']}"
        return out

    def _challenge(self, aid: str, kind: str) -> dict:
        a = self.authzs[aid]
        mine = a["asked"] == kind
        out = {"type": kind, "url": f"{self.url}/chall/{aid}/{kind}", "token": a["token"],
               "status": a["status"] if mine and a["status"] != "pending" else "pending"}
        if mine and a["error"]:
            out["error"] = a["error"]
        return out

    def _authz(self, aid: str) -> dict:
        a = self.authzs[aid]
        out = {"identifier": {"type": "dns", "value": a["name"]}, "status": "pending" if a["status"] == "processing" else a["status"],
               "challenges": [self._challenge(aid, k) for k in a["kinds"]]}
        if a["star"]:
            out["wildcard"] = True
        return out

    def _look(self, a: dict, key: dict) -> None:
        """Look for the proof where the client was to put it."""
        kind, name = a["asked"], a["name"]
        proof = f"{a['token']}.{self.thumbprint(key)}"
        self.looked.append((kind, name))
        why = self.fail.get(name)
        if not why:
            if kind == "http-01":
                got = self.fetch(name, f"/.well-known/acme-challenge/{a['token']}")
                if (got or "").strip() != proof:
                    why = f"The key authorization file from the server did not match this challenge: {(got or 'nothing')[:60]!r}"
            else:
                want = b64(hashlib.sha256(proof.encode("ascii")).digest())
                if want not in list(self.txt(f"_acme-challenge.{name}")):
                    why = f"No TXT record found at _acme-challenge.{name} with the expected value"
        if why:
            a["status"], a["error"] = "invalid", {"type": ERR + "unauthorized", "detail": why, "status": 403}
        else:
            a["status"] = "valid"

    def _fetch(self, name: str, path: str):
        req = urllib.request.Request(f"http://127.0.0.1:{self.http_port}{path}", headers={"Host": name})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.read().decode("utf-8", "replace")
        except OSError:
            return None

    def _finalize(self, oid: str, payload: dict) -> dict:
        o = self.orders[oid]
        self._order(oid)
        if o["status"] != "ready":
            raise Refused(403, "orderNotReady", "the names of this order are not all proven")
        try:
            csr = x509.load_der_x509_csr(unb64(payload["csr"]))
            asked = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        except Exception:  # noqa: BLE001
            raise Refused(400, "badCSR", "not a signing request") from None
        if not csr.is_signature_valid or sorted(asked) != sorted(o["names"]):
            raise Refused(400, "badCSR", "the signing request names something else than the order")
        cid = self._id()
        self.certs[cid] = self._sign(csr.public_key(), o["names"])
        o["cert"], o["status"] = cid, "processing" if self.slow else "valid"
        return self._order(oid)

    # ---- certificates
    def _sign(self, public_key, names: list, lifetime: float = None, start: datetime = None) -> str:
        start = start or datetime.now(timezone.utc) - timedelta(minutes=5)
        cert = (x509.CertificateBuilder().subject_name(x509.Name([])).issuer_name(self.root.subject).public_key(public_key)
                .serial_number(x509.random_serial_number()).not_valid_before(start)
                .not_valid_after(start + timedelta(seconds=self.lifetime if lifetime is None else lifetime))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=True)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=False, crl_sign=False, content_commitment=False,
                                             key_encipherment=False, data_encipherment=False, key_agreement=False,
                                             encipher_only=False, decipher_only=False), critical=True)
                .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()), critical=False)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
                .sign(self.key, hashes.SHA256()))
        return cert.public_bytes(serialization.Encoding.PEM).decode("ascii") + self.root_pem()

    def issue(self, names: list, lifetime: float = None, start: datetime = None) -> tuple:
        """(private key, certificate and chain), both PEM, without the asking: what a test starts from."""
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode("ascii")
        return pem, self._sign(key.public_key(), names, lifetime, start)
