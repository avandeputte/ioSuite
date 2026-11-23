"""Two-step sign-in (iosuite_shared.twostep) and passkeys (iosuite_shared.passkeys): both off until a person turns
them on. The passkeys here are made by a small authenticator of the test's own (a P-256 key, as a phone makes one)."""
import base64
import hashlib
import json
import struct
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from iosuite_shared import apppasswords, passkeys, twostep, users
from iosuite_shared.tests.test_fastapi import make_app

HOST = "https://photo.example.com"


@pytest.fixture(autouse=True)
def no_waits():
    users._attempts.clear()  # the wrong answers of the test before are not this one's


def now_code(secret: str, ahead: int = 0) -> str:
    return twostep.code_at(secret, int(time.time()) // twostep.PERIOD + ahead)


def basic(name: str, pw: str) -> dict:
    return {"authorization": "Basic " + base64.b64encode(f"{name}:{pw}".encode()).decode()}


def signed_in(app, name="alex", password="secret123"):
    users.create(name, password, "admin", "iopix", suite_admin=not users.any_users())
    c = TestClient(app, base_url=HOST)
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


def test_code_at_is_rfc_6238():
    secret = base64.b32encode(b"12345678901234567890").decode()  # the RFC's test key
    assert twostep.code_at(secret, 59 // 30) == "287082"
    assert twostep.code_at(secret, 1111111109 // 30) == "081804"


def test_nothing_changes_until_it_is_turned_on():
    app, _ = make_app()
    c = signed_in(app)
    ways = c.get("/api/auth/sign-in").json()
    assert ways["available"] and ways["passkeys"] == [] and ways["twoStep"] == {"on": False, "since": None, "recoveryLeft": 0}
    assert c.get("/api/auth/login/passkey").json() == {"available": False}
    assert c.post("/api/auth/login/passkey/begin").status_code == 404
    assert c.get("/api/private", headers=basic("alex", "secret123")).status_code == 200  # the password alone, as before


def test_two_step_on_asks_for_the_code_and_takes_it_once():
    app, _ = make_app()
    c = signed_in(app)
    assert c.post("/api/auth/two-step/begin", json={"password": "wrong"}).status_code == 403
    made = c.post("/api/auth/two-step/begin", json={"password": "secret123"}).json()
    assert made["uri"].startswith("otpauth://totp/ioSuite:alex?secret=" + made["secret"]) and made["qr"].startswith("<svg")
    other = TestClient(app, base_url=HOST)
    assert other.post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 200, "not on before a code came back"
    assert c.post("/api/auth/two-step", json={"code": "000000"}).status_code == 400
    r = c.post("/api/auth/two-step", json={"code": now_code(made["secret"])}).json()
    assert len(r["recovery"]) == twostep.RECOVERY_CODES and r["twoStep"]["on"] and r["twoStep"]["recoveryLeft"] == 8
    assert c.get("/api/private").status_code == 200, "the session it was turned on in goes on"

    n = TestClient(app, base_url=HOST)
    r = n.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert r.status_code == 401 and r.json()["twoStep"] is True and "iothing_session" not in r.cookies
    r = n.post("/api/auth/login", json={"name": "alex", "password": "wrong", "code": now_code(made["secret"], 1)})
    assert r.status_code == 401 and "twoStep" not in r.json(), "a wrong password says nothing about the second step"
    r = n.post("/api/auth/login", json={"name": "alex", "password": "secret123", "code": "123456"})
    assert r.status_code == 401 and r.json()["twoStep"] is True
    used = now_code(made["secret"])
    assert n.post("/api/auth/login", json={"name": "alex", "password": "secret123", "code": used}).status_code == 401, "the code that turned it on was used"
    nxt = now_code(made["secret"], 1)
    assert n.post("/api/auth/login", json={"name": "alex", "password": "secret123", "code": f"{nxt[:3]} {nxt[3:]}"}).status_code == 200
    assert n.get("/api/private").status_code == 200
    again = TestClient(app, base_url=HOST)
    assert again.post("/api/auth/login", json={"name": "alex", "password": "secret123", "code": nxt}).status_code == 401, "a code works once"


def test_recovery_codes_work_once_and_turning_off_needs_the_password():
    app, _ = make_app()
    c = signed_in(app)
    secret = c.post("/api/auth/two-step/begin", json={"password": "secret123"}).json()["secret"]
    codes = c.post("/api/auth/two-step", json={"code": now_code(secret)}).json()["recovery"]
    n = TestClient(app, base_url=HOST)
    assert n.post("/api/auth/login", json={"name": "alex", "password": "secret123", "code": codes[0].upper()}).status_code == 200
    assert TestClient(app, base_url=HOST).post("/api/auth/login", json={"name": "alex", "password": "secret123", "code": codes[0]}).status_code == 401
    assert c.get("/api/auth/sign-in").json()["twoStep"]["recoveryLeft"] == 7
    assert c.post("/api/auth/two-step/off", json={"password": "nope"}).status_code == 403
    assert c.post("/api/auth/two-step/off", json={"password": "secret123"}).json()["twoStep"]["on"] is False
    assert TestClient(app, base_url=HOST).post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 200


def test_with_two_step_the_password_alone_signs_no_client_in():
    app, _ = make_app()
    c = signed_in(app)
    assert c.get("/api/private", headers=basic("alex", "secret123")).status_code == 200
    secret = c.post("/api/auth/two-step/begin", json={"password": "secret123"}).json()["secret"]
    c.post("/api/auth/two-step", json={"code": now_code(secret)})
    n = TestClient(app, base_url=HOST)
    r = n.get("/api/private", headers=basic("alex", "secret123"))  # at once, though the check was remembered a moment ago
    assert r.status_code == 401 and r.json()["twoStep"] is True and "app password" in r.json()["detail"]
    pw = apppasswords.create(users.find("alex")["id"], "iopix", "Phone")
    assert n.get("/api/private", headers=basic("alex", pw)).status_code == 200


def test_a_suite_admin_resets_and_a_one_click_account_has_neither():
    app, _ = make_app()
    c = signed_in(app)
    kid = users.create("kid", "longenough", "member", "iopix")
    k = TestClient(app, base_url=HOST)
    k.post("/api/auth/login", json={"name": "kid", "password": "longenough"})
    secret = k.post("/api/auth/two-step/begin", json={"password": "longenough"}).json()["secret"]
    k.post("/api/auth/two-step", json={"code": now_code(secret)})
    row = next(u for u in c.get("/api/suite-admin").json()["users"] if u["name"] == "kid")
    assert row["twoStep"] is True and row["passkeys"] == 0
    assert c.patch(f"/api/suite-admin/users/{kid['id']}", json={"resetSignIn": True}).json()["twoStep"] is False
    assert TestClient(app, base_url=HOST).post("/api/auth/login", json={"name": "kid", "password": "longenough"}).status_code == 200
    users.update(kid["id"], password="")
    k = TestClient(app, base_url="http://192.168.1.5")
    assert k.post("/api/auth/login", json={"name": "kid"}).status_code == 200
    assert k.get("/api/auth/sign-in").json()["available"] is False
    assert k.post("/api/auth/two-step/begin", json={"password": ""}).status_code == 403
    assert k.post("/api/auth/passkeys/begin", json={"password": ""}).status_code == 403


# ---- passkeys
class Phone:
    """An authenticator: one P-256 key, a credential id, and the answers a browser would send for it."""

    def __init__(self, origin=HOST, counts=False):
        self.key, self.cid, self.origin, self.count, self.counts = ec.generate_private_key(ec.SECP256R1()), b"credential-" + bytes(range(20)), origin, 0, counts

    def _client(self, typ, challenge):
        return json.dumps({"type": typ, "challenge": challenge, "origin": self.origin, "crossOrigin": False}).encode()

    def _auth(self, rp, flags, attested=b""):
        if self.counts:
            self.count += 1
        return hashlib.sha256(rp.encode()).digest() + bytes([flags]) + struct.pack(">I", self.count) + attested

    def create(self, options, label="iPhone", flags=0x45):
        ad = self._auth(options["rp"]["id"], flags, bytes(16) + struct.pack(">H", len(self.cid)) + self.cid + b"\xa5cose-key")
        spki = self.key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return {"clientDataJSON": passkeys.b64(self._client("webauthn.create", options["challenge"])), "authenticatorData": passkeys.b64(ad),
                "publicKey": passkeys.b64(spki), "alg": -7, "label": label}

    def get(self, options, flags=0x05, key=None):
        cd, ad = self._client("webauthn.get", options["challenge"]), self._auth(options["rpId"], flags)
        sig = (key or self.key).sign(ad + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": passkeys.b64(self.cid), "clientDataJSON": passkeys.b64(cd), "authenticatorData": passkeys.b64(ad), "signature": passkeys.b64(sig)}


def with_passkey(app, phone, c=None):
    c = c or signed_in(app)
    assert c.post("/api/auth/passkeys/begin", json={"password": "nope"}).status_code == 403
    options = c.post("/api/auth/passkeys/begin", json={"password": "secret123"}).json()
    r = c.post("/api/auth/passkeys", json=phone.create(options))
    assert r.status_code == 200, r.text
    return c, r.json()


def test_add_a_passkey_and_sign_in_with_it(monkeypatch):
    __import__("iosuite_shared.db").db.set_setting("COOKIE_DOMAIN", "example.com")  # the suite's setting (Settings › Apps › All settings)
    app, _ = make_app()
    notes, _ = make_app("ionote")
    phone = Phone()
    c, ways = with_passkey(app, phone)
    assert ways["rpId"] == "example.com" and [(p["label"], p["here"]) for p in ways["passkeys"]] == [("iPhone", True)]
    n = TestClient(notes, base_url="https://notes.example.com")  # another app under the same domain: the same passkey
    assert n.get("/api/auth/login/passkey").json() == {"available": True}
    options = n.post("/api/auth/login/passkey/begin").json()
    assert options["rpId"] == "example.com" and options["userVerification"] == "required"
    phone.origin = "https://notes.example.com"
    r = n.post("/api/auth/login/passkey", json=phone.get(options))
    assert r.status_code == 200 and r.json()["user"]["name"] == "alex" and "iothing_session" in r.cookies
    me = n.get("/api/auth/me").json()
    assert me["signedIn"] and me["signedInBy"] == "passkey"
    assert c.get("/api/auth/sign-in").json()["passkeys"][0]["lastUsed"]
    # removed: no longer offered, no longer taken
    pid = ways["passkeys"][0]["id"]
    assert c.delete(f"/api/auth/passkeys/{pid}").json()["passkeys"] == []
    assert n.get("/api/auth/login/passkey").json() == {"available": False}


def test_a_passkey_needs_no_code_and_two_step_stays_on_for_the_password():
    app, _ = make_app()
    phone = Phone()
    c, _ = with_passkey(app, phone)
    secret = c.post("/api/auth/two-step/begin", json={"password": "secret123"}).json()["secret"]
    c.post("/api/auth/two-step", json={"code": now_code(secret)})
    n = TestClient(app, base_url=HOST)
    assert n.post("/api/auth/login/passkey", json=phone.get(n.post("/api/auth/login/passkey/begin").json())).status_code == 200
    assert TestClient(app, base_url=HOST).post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 401


@pytest.mark.parametrize("spoil, why", [
    (lambda phone, a: a.update(signature=passkeys.b64(passkeys.unb64(phone.get({"challenge": "x" * 43, "rpId": "photo.example.com"})["signature"]))), "signature"),
    (lambda phone, a: a.update(id=passkeys.b64(b"someone else's")), "not known"),
    (lambda phone, a: a.update(clientDataJSON=passkeys.b64(passkeys.unb64(a["clientDataJSON"]).replace(b"photo.example.com", b"photo.example.com.evil.net"))), "another address"),
    (lambda phone, a: a.update(clientDataJSON=passkeys.b64(passkeys.unb64(a["clientDataJSON"]).replace(b"webauthn.get", b"webauthn.create"))), "not for this"),
])
def test_what_a_passkey_sign_in_refuses(spoil, why):
    app, _ = make_app()
    phone = Phone()
    with_passkey(app, phone)
    n = TestClient(app, base_url=HOST)
    answer = phone.get(n.post("/api/auth/login/passkey/begin").json())
    spoil(phone, answer)
    r = n.post("/api/auth/login/passkey", json=answer)
    assert r.status_code == 401 and why in r.json()["detail"], r.text
    assert "iothing_session" not in r.cookies


def test_a_challenge_works_once_and_the_person_has_to_be_verified():
    app, _ = make_app()
    phone = Phone()
    with_passkey(app, phone)
    n = TestClient(app, base_url=HOST)
    options = n.post("/api/auth/login/passkey/begin").json()
    answer = phone.get(options)
    assert n.post("/api/auth/login/passkey", json=answer).status_code == 200
    assert TestClient(app, base_url=HOST).post("/api/auth/login/passkey", json=answer).status_code == 401, "the same answer again"
    m = TestClient(app, base_url=HOST)
    r = m.post("/api/auth/login/passkey", json=phone.get(m.post("/api/auth/login/passkey/begin").json(), flags=0x01))
    assert r.status_code == 401 and "who you are" in r.json()["detail"]
    r = m.post("/api/auth/login/passkey", json=phone.get(m.post("/api/auth/login/passkey/begin").json(), key=ec.generate_private_key(ec.SECP256R1())))
    assert r.status_code == 401 and "signature" in r.json()["detail"]


def test_a_passkey_that_counts_never_goes_back_and_another_address_has_its_own():
    app, _ = make_app()
    phone = Phone(counts=True)
    c, _ = with_passkey(app, phone)
    n = TestClient(app, base_url=HOST)
    assert n.post("/api/auth/login/passkey", json=phone.get(n.post("/api/auth/login/passkey/begin").json())).status_code == 200
    phone.count -= 2  # a copy of the passkey, behind the real one
    assert n.post("/api/auth/login/passkey", json=phone.get(n.post("/api/auth/login/passkey/begin").json())).status_code == 401
    lan = TestClient(app, base_url="https://nas.home.arpa")
    assert lan.get("/api/auth/login/passkey").json() == {"available": False}
    lan.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert [p["here"] for p in lan.get("/api/auth/sign-in").json()["passkeys"]] == [False]
    # a passkey asked for by one account is not kept for another
    users.create("sam", "secret123", "member", "iopix")
    s = TestClient(app, base_url=HOST)
    s.post("/api/auth/login", json={"name": "sam", "password": "secret123"})
    options = c.post("/api/auth/passkeys/begin", json={"password": "secret123"}).json()
    other = Phone()
    other.cid = b"another credential"
    assert s.post("/api/auth/passkeys", json=other.create(options)).status_code == 400
