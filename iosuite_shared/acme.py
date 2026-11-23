"""An ACME client (RFC 8555): asks a certificate authority such as Let's Encrypt for a certificate for some names,
proving the suite answers for each of them.

    client = acme.Client(acme.LETSENCRYPT, account_key_pem, contact="me@example.com")
    key_pem, chain_pem = client.certificate(["home.example.com"], "http-01", publish, remove)

`publish(kind, name, token, value)` puts the proof where the authority looks for it, and `remove(kind, name, token)`
takes it away again:

    http-01   the authority asks http://<name>/.well-known/acme-challenge/<token> on port 80 and wants `value` back
    dns-01    it asks DNS for the TXT record _acme-challenge.<name> and wants `value` in it (the only proof for a
              name with a star, and for a name the internet cannot reach)

Only this file talks to the authority; which names, where the proof goes and where the certificate is kept is
iosuite_shared.certs. Nothing but the standard library and `cryptography`.
"""
from __future__ import annotations

import base64
import hashlib
import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

LETSENCRYPT = "https://acme-v02.api.letsencrypt.org/directory"
STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
AGENT = "ioSuite (ACME client)"
BAD_NONCE = "urn:ietf:params:acme:error:badNonce"
PAUSE = (1.0, 10.0)  # between two looks at something the authority is still busy with: at least, at most (seconds)


class Problem(Exception):
    """What the authority (or the way to it) said no with: `kind` is its error type's last word (rateLimited,
    unauthorized, connection, …), `detail` its own sentence."""

    def __init__(self, detail: str, kind: str = "", status: int = 0):
        super().__init__(detail)
        self.detail, self.kind, self.status = detail, kind, status


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def new_key() -> str:
    """A new private key (ECDSA P-256), as PEM."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode("ascii")


def _load(pem: str):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(pem.encode("ascii"), password=None)


def jwk(key) -> dict:
    """The public half of an account key, the way the authority is told it."""
    n = key.public_key().public_numbers()
    return {"crv": "P-256", "kty": "EC", "x": b64(n.x.to_bytes(32, "big")), "y": b64(n.y.to_bytes(32, "big"))}


def thumbprint(key) -> str:
    """RFC 7638: the account key's fingerprint, part of every proof."""
    return b64(hashlib.sha256(json.dumps(jwk(key), sort_keys=True, separators=(",", ":")).encode()).digest())


def txt_value(key_authorization: str) -> str:
    """What the TXT record of a dns-01 proof holds."""
    return b64(hashlib.sha256(key_authorization.encode("ascii")).digest())


def request(names: list, key_pem: str) -> bytes:
    """The certificate signing request for these names (DER), signed with the certificate's own key."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    csr = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
           .sign(_load(key_pem), hashes.SHA256()))
    return csr.public_bytes(serialization.Encoding.DER)


def describe(chain_pem: str) -> dict:
    """What a certificate says: its names, from when until when it holds, who signed it, its fingerprint."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    cert = x509.load_pem_x509_certificate(chain_pem.encode("ascii"))
    try:
        names = list(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        names = []
    issuer = next((a.value for a in cert.issuer if a.oid == x509.NameOID.ORGANIZATION_NAME), "") or cert.issuer.rfc4514_string()
    return {"names": names, "from": int(cert.not_valid_before_utc.timestamp()), "until": int(cert.not_valid_after_utc.timestamp()),
            "issuer": str(issuer), "fingerprint": cert.fingerprint(hashes.SHA256()).hex()}


def covers(cert_names: list, name: str) -> bool:
    """Whether a certificate with these names holds for `name` (a star stands for exactly one label)."""
    name = name.lower()
    for c in cert_names:
        c = c.lower()
        if c == name or (c.startswith("*.") and "." in name and name.split(".", 1)[1] == c[2:]):
            return True
    return False


class Client:
    """One account at one authority. `account_key`: the account's private key (PEM, new_key()): the same key is the
    same account, made at the authority the first time it is used. `cafile`: the authority's own certificate, for a
    test authority that is not signed by a public one."""

    def __init__(self, directory: str, account_key: str, contact: str = "", cafile: str = None, timeout: float = 30, log=None):
        self.directory_url, self.contact, self.timeout = directory, (contact or "").strip(), timeout
        self.key = _load(account_key)
        self.log = log or (lambda *a: None)
        self._tls = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
        self._dir: dict = {}
        self._nonce: str | None = None
        self.kid: str | None = None

    # ---- the wire
    def _open(self, req: urllib.request.Request):
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._tls) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except (urllib.error.URLError, OSError, ssl.SSLError) as e:
            raise Problem(f"the certificate authority could not be reached ({getattr(e, 'reason', e)})", "connection") from e

    def _directory(self) -> dict:
        if not self._dir:
            status, _h, body = self._open(urllib.request.Request(self.directory_url, headers={"User-Agent": AGENT}))
            if status != 200:
                raise Problem(f"{self.directory_url} is not an ACME directory (it answered {status})", "directory", status)
            try:
                self._dir = json.loads(body)
            except ValueError:
                raise Problem(f"{self.directory_url} is not an ACME directory", "directory", status) from None
        return self._dir

    def _fresh_nonce(self) -> str:
        if self._nonce:
            n, self._nonce = self._nonce, None
            return n
        _s, headers, _b = self._open(urllib.request.Request(self._directory()["newNonce"], method="HEAD", headers={"User-Agent": AGENT}))
        n = headers.get("Replay-Nonce")
        if not n:
            raise Problem("the certificate authority gave no nonce", "nonce")
        return n

    def _sign(self, url: str, payload, nonce: str) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        head = {"alg": "ES256", "nonce": nonce, "url": url}
        if self.kid:
            head["kid"] = self.kid
        else:
            head["jwk"] = jwk(self.key)
        protected = b64(json.dumps(head).encode())
        body = "" if payload is None else b64(json.dumps(payload).encode())  # None: a POST that only asks (POST-as-GET)
        r, s = utils.decode_dss_signature(self.key.sign(f"{protected}.{body}".encode("ascii"), ec.ECDSA(hashes.SHA256())))
        return json.dumps({"protected": protected, "payload": body, "signature": b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}).encode()

    def _post(self, url: str, payload=None, ok=(200, 201)) -> tuple:
        """A signed request: (status, headers, the answer as JSON or text). A nonce the authority no longer takes is
        tried again with a new one."""
        for attempt in range(5):
            data = self._sign(url, payload, self._fresh_nonce())
            status, headers, body = self._open(urllib.request.Request(url, data=data, method="POST", headers={
                "Content-Type": "application/jose+json", "User-Agent": AGENT}))
            self._nonce = headers.get("Replay-Nonce")
            kind = (headers.get("Content-Type") or "").split(";")[0].strip()
            try:
                answer = json.loads(body) if "json" in kind else body.decode("utf-8", "replace")
            except ValueError:
                answer = body.decode("utf-8", "replace")
            if status in ok:
                return status, headers, answer
            problem = answer if isinstance(answer, dict) else {}
            if problem.get("type") == BAD_NONCE and attempt < 4:
                continue
            raise Problem(_said(problem) or f"the certificate authority answered {status}", str(problem.get("type") or "").rsplit(":", 1)[-1], status)
        raise Problem("the certificate authority kept refusing the request", "nonce")

    # ---- the account
    def account(self) -> str:
        """The account's address at the authority: found by its key, made when it is new."""
        if not self.kid:
            payload: dict = {"termsOfServiceAgreed": True}
            if self.contact:
                payload["contact"] = [f"mailto:{self.contact}"]
            _s, headers, _a = self._post(self._directory()["newAccount"], payload)
            self.kid = headers.get("Location")
            if not self.kid:
                raise Problem("the certificate authority named no account", "account")
        return self.kid

    # ---- a certificate
    def certificate(self, names: list, kind: str, publish, remove=None, wait: float = 180, settle: float = 0) -> tuple:
        """(the certificate's private key, the certificate with its chain), both PEM, for these names. `kind`: http-01
        or dns-01. `settle`: seconds to wait after the proofs are published and before the authority is told to look
        (DNS that takes a moment to be everywhere)."""
        names = list(dict.fromkeys(n.strip().lower() for n in names if n and n.strip()))
        if not names:
            raise Problem("no name to ask a certificate for", "names")
        if kind == "http-01" and any(n.startswith("*.") for n in names):
            raise Problem("a name with a star can only be proven through DNS", "names")
        self.account()
        _s, headers, order = self._post(self._directory()["newOrder"], {"identifiers": [{"type": "dns", "value": n} for n in names]})
        order_url = headers.get("Location")
        mark = thumbprint(self.key)
        published, waiting = [], []
        try:
            for url in order.get("authorizations") or []:
                _s, _h, authz = self._post(url)
                name = (authz.get("identifier") or {}).get("value") or ""
                if authz.get("status") == "valid":
                    continue
                ch = next((c for c in authz.get("challenges") or [] if c.get("type") == kind), None)
                if ch is None:
                    offered = ", ".join(c.get("type", "?") for c in authz.get("challenges") or [])
                    raise Problem(f"the certificate authority does not take this proof for {name} (it offers: {offered})", "challenge")
                proof = f"{ch['token']}.{mark}"
                publish(kind, name, ch["token"], proof if kind == "http-01" else txt_value(proof))
                published.append((kind, name, ch["token"]))
                waiting.append((url, ch["url"], name))
                self.log(f"proof for {name} is in place ({kind})")
            if waiting and settle:
                time.sleep(settle)
            for _url, ch_url, _name in waiting:  # "look now"
                self._post(ch_url, {})
            until = time.time() + wait
            for url, _ch_url, name in waiting:
                while True:
                    _s, headers, authz = self._post(url)
                    if authz.get("status") == "valid":
                        break
                    if authz.get("status") in ("invalid", "deactivated", "expired", "revoked"):
                        failed = next((c for c in authz.get("challenges") or [] if c.get("error")), {})
                        raise Problem(f"{name}: " + (_said(failed.get("error") or {}) or "the certificate authority did not find the proof"),
                                      str((failed.get("error") or {}).get("type") or "").rsplit(":", 1)[-1] or "unauthorized")
                    if time.time() > until:
                        raise Problem(f"{name}: the certificate authority had not looked after {int(wait)} seconds", "timeout")
                    time.sleep(_pause(headers))
            key_pem = new_key()
            _s, headers, order = self._post(order["finalize"], {"csr": b64(request(names, key_pem))})
            until = time.time() + wait
            while order.get("status") in ("processing", "pending", "ready"):
                if time.time() > until:
                    raise Problem(f"the certificate was not made after {int(wait)} seconds", "timeout")
                time.sleep(_pause(headers))
                _s, headers, order = self._post(order_url)
            if order.get("status") != "valid" or not order.get("certificate"):
                raise Problem(_said(order.get("error") or {}) or f"the order ended as {order.get('status')}", "order")
            _s, _h, chain = self._post(order["certificate"])
            if not isinstance(chain, str) or "BEGIN CERTIFICATE" not in chain:
                raise Problem("the certificate authority sent no certificate", "order")
            return key_pem, chain.strip() + "\n"
        finally:
            for item in published:
                try:
                    if remove:
                        remove(*item)
                except Exception:  # noqa: BLE001 - a proof left behind does no harm
                    pass


def _pause(headers) -> float:
    try:
        return min(PAUSE[1], max(PAUSE[0], float(headers.get("Retry-After") or 2)))
    except (TypeError, ValueError):
        return min(PAUSE[1], 2.0)


def _said(problem: dict) -> str:
    """An authority's problem document as one sentence: its own, with those of the names it is about."""
    if not isinstance(problem, dict):
        return ""
    parts = [str(problem.get("detail") or "").strip()]
    for sub in problem.get("subproblems") or []:
        d = str(sub.get("detail") or "").strip()
        if d and d not in parts:
            parts.append(d)
    return " ".join(p for p in parts if p)


def when(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
