"""Passkeys (WebAuthn): sign in with Face ID, Touch ID, a fingerprint, a PIN or a security key instead of the password.
Nobody has one until they add it in Settings › Account; the sign-in screens offer "Sign in with a passkey" only where
one exists.

A passkey belongs to an address (its rp id): the suite's shared cookie domain when the app is reached under it (one
passkey then works in every app there), else the host name. Browsers make passkeys on https pages only (and on
localhost), so an install reached over plain http on the LAN has none.

What is checked is what the standard asks of a server that takes no attestation: the challenge is one this server made
(kept in ios_auth_challenges, used once, a few minutes), the page that asked is under the rp id, the authenticator
says the person was verified (Face ID, PIN...: so a passkey stands for both steps and no code is asked after it), and
at a sign-in the signature fits the public key kept when the passkey was added. The browser hands over that key by
itself (getPublicKey), so no CBOR is read here.
"""
import base64
import hashlib
import json
import secrets
import struct
import time
from urllib.parse import urlsplit

import pymysql
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.serialization import load_der_public_key

from iosuite_shared import db, sessions
from iosuite_shared.errors import Invalid

CHALLENGE_S = 300
MAX_PER_ACCOUNT = 20
ALGS = (-7, -8, -257)  # ES256, EdDSA, RS256: what the page asks for, in this order
UP, UV, AT = 0x01, 0x04, 0x40  # authenticator flags: the person was there, was verified, a new credential is attached


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text) -> bytes:
    try:
        s = str(text or "")
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except (ValueError, TypeError) as e:
        raise Invalid("The passkey's answer could not be read") from e


def rp_id(host: str) -> str:
    """The address passkeys made here belong to: the shared cookie domain when the host is under it, else the host."""
    name = (host or "").strip().lower()
    name = name[:name.index("]") + 1] if name.startswith("[") else name.split(":")[0]
    return sessions.cookie_domain(name) or name


def _origin_ok(origin: str, rp: str) -> bool:
    """The page that asked the browser is at the rp id or under it, over https (http on this computer only)."""
    try:
        u = urlsplit(origin or "")
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme != "https" and not (u.scheme == "http" and (host in ("localhost", "127.0.0.1", "::1"))):
        return False
    return host == rp or host.endswith("." + rp)


# ---- challenges: made here, used once
def challenge(kind: str, rp: str, user_id: int | None = None) -> str:
    now = int(time.time())
    db.ex("DELETE FROM ios_auth_challenges WHERE expires_at < %s", (now,))
    c = b64(secrets.token_bytes(32))
    db.ex("INSERT INTO ios_auth_challenges (challenge, kind, rp_id, user_id, expires_at) VALUES (%s, %s, %s, %s, %s)",
          (c, kind, rp[:191], user_id, now + CHALLENGE_S))
    return c


def _take(c: str, kind: str) -> dict:
    """The challenge's row, taken off the table; Invalid when it is not one of ours, was used, or is too old."""
    with db.tx():
        r = db.one("SELECT * FROM ios_auth_challenges WHERE challenge = %s FOR UPDATE", (str(c or "")[:64],))
        if r:
            db.ex("DELETE FROM ios_auth_challenges WHERE challenge = %s", (r["challenge"],))
    if not r or r["kind"] != kind or r["expires_at"] < time.time():
        raise Invalid("That took too long; try again")
    return r


def _client_data(raw: bytes, kind: str, typ: str) -> dict:
    """The browser's own account of what it did (clientDataJSON): the right kind, our challenge, a page under the rp id."""
    try:
        cd = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Invalid("The passkey's answer could not be read") from e
    if not isinstance(cd, dict) or cd.get("type") != typ:
        raise Invalid("The passkey's answer is not for this")
    ch = _take(cd.get("challenge"), kind)
    if not _origin_ok(cd.get("origin"), ch["rp_id"]):
        raise Invalid("The passkey was asked for by another address")
    return ch


def _auth_data(raw: bytes, rp: str) -> tuple:
    """(flags, counter, the rest) of the authenticator's data, checked: made for this rp id, the person there and verified."""
    if len(raw) < 37 or raw[:32] != hashlib.sha256(rp.encode()).digest():
        raise Invalid("The passkey is for another address")
    flags, count = raw[32], struct.unpack(">I", raw[33:37])[0]
    if not flags & UP or not flags & UV:
        raise Invalid("The passkey did not check who you are (Face ID, Touch ID, a PIN); it needs to")
    return flags, count, raw[37:]


def _key(spki: bytes, alg: int):
    """The public key, when it is of the kind its algorithm number says."""
    try:
        key = load_der_public_key(spki)
    except (ValueError, TypeError) as e:
        raise Invalid("The passkey's key could not be read") from e
    ok = ((alg == -7 and isinstance(key, ec.EllipticCurvePublicKey) and isinstance(key.curve, ec.SECP256R1))
          or (alg == -257 and isinstance(key, rsa.RSAPublicKey) and key.key_size >= 2048)
          or (alg == -8 and isinstance(key, ed25519.Ed25519PublicKey)))
    if not ok:
        raise Invalid("This kind of passkey is not supported")
    return key


def _verify(key, alg: int, signature: bytes, signed: bytes) -> bool:
    try:
        if alg == -7:
            key.verify(signature, signed, ec.ECDSA(hashes.SHA256()))
        elif alg == -257:
            key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
        else:
            key.verify(signature, signed)
    except InvalidSignature:
        return False
    return True


def _cid_hash(cid: bytes) -> str:
    return hashlib.sha256(cid).hexdigest()


# ---- the account's passkeys
def list_for(user_id: int, rp: str = "") -> list:
    """[{id, label, created, lastUsed, rpId, here}]: here is whether it works at the address asked from."""
    return [{"id": r["id"], "label": r["label"], "created": r["created_at"], "lastUsed": r["last_used_at"], "rpId": r["rp_id"],
             "here": r["rp_id"] == rp}
            for r in db.q("SELECT id, label, created_at, last_used_at, rp_id FROM ios_passkeys WHERE user_id = %s ORDER BY created_at", (user_id,))]


def any_at(rp: str) -> bool:
    """Whether anybody has a passkey for this address: the sign-in screen offers them only then."""
    return db.one("SELECT 1 AS x FROM ios_passkeys WHERE rp_id = %s LIMIT 1", (rp,)) is not None


def counts() -> dict:
    return {r["user_id"]: r["n"] for r in db.q("SELECT user_id, count(*) AS n FROM ios_passkeys GROUP BY user_id")}


def begin_add(user: dict, host: str) -> dict:
    """What the page passes to navigator.credentials.create (the byte fields base64url, for the page to decode)."""
    if user.get("passwordless"):
        raise Invalid("A one-click account signs in on the home network only and takes no passkey")
    rp = rp_id(host)
    have = db.q("SELECT credential_id FROM ios_passkeys WHERE user_id = %s AND rp_id = %s", (user["id"], rp))
    if db.one("SELECT count(*) AS n FROM ios_passkeys WHERE user_id = %s", (user["id"],))["n"] >= MAX_PER_ACCOUNT:
        raise Invalid("That is a lot of passkeys; remove one you no longer use first")
    return {"challenge": challenge("add", rp, user["id"]), "rp": {"id": rp, "name": "ioSuite"},
            "user": {"id": b64(str(user["id"]).encode()), "name": user["name"], "displayName": user.get("displayName") or user["name"]},
            "pubKeyCredParams": [{"type": "public-key", "alg": a} for a in ALGS],
            "excludeCredentials": [{"type": "public-key", "id": r["credential_id"]} for r in have],
            "authenticatorSelection": {"residentKey": "required", "userVerification": "required"},
            "attestation": "none", "timeout": CHALLENGE_S * 1000}


def add(user: dict, body: dict) -> dict:
    """Keep the passkey the browser just made: body {clientDataJSON, authenticatorData, publicKey, alg, label}."""
    ch = _client_data(unb64(body.get("clientDataJSON")), "add", "webauthn.create")
    if ch["user_id"] != user["id"]:
        raise Invalid("That passkey was asked for by another account")
    flags, count, rest = _auth_data(unb64(body.get("authenticatorData")), ch["rp_id"])
    if not flags & AT or len(rest) < 18:
        raise Invalid("The passkey's answer could not be read")
    n = struct.unpack(">H", rest[16:18])[0]
    cid = rest[18:18 + n]
    if not n or len(cid) != n or n > 1023:
        raise Invalid("The passkey's answer could not be read")
    try:
        alg = int(body.get("alg"))
    except (TypeError, ValueError) as e:
        raise Invalid("This kind of passkey is not supported") from e
    spki = unb64(body.get("publicKey"))
    _key(spki, alg)
    label = " ".join(str(body.get("label") or "").split())[:128] or "Passkey"
    try:
        pid = db.ex("INSERT INTO ios_passkeys (user_id, credential_hash, credential_id, public_key, alg, sign_count, rp_id, label, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (user["id"], _cid_hash(cid), b64(cid), b64(spki), alg, count, ch["rp_id"], label, int(time.time())))
    except pymysql.err.IntegrityError as e:
        raise Invalid("That passkey is already added") from e
    return {"id": pid, "label": label}


def remove(user_id: int, passkey_id: int) -> bool:
    return db.ex("DELETE FROM ios_passkeys WHERE id = %s AND user_id = %s", (passkey_id, user_id)) > 0


def remove_all(user_id: int) -> int:
    return db.ex("DELETE FROM ios_passkeys WHERE user_id = %s", (user_id,))


# ---- signing in with one
def begin_sign_in(host: str) -> dict:
    """What the page passes to navigator.credentials.get: no list of passkeys, so the browser offers the ones it has
    for this address and the answer says whose it is."""
    rp = rp_id(host)
    return {"challenge": challenge("get", rp), "rpId": rp, "userVerification": "required", "timeout": CHALLENGE_S * 1000}


def sign_in(body: dict) -> int:
    """The id of the account whose passkey answered: body {id, clientDataJSON, authenticatorData, signature}."""
    raw_cd = unb64(body.get("clientDataJSON"))
    ch = _client_data(raw_cd, "get", "webauthn.get")
    r = db.one("SELECT * FROM ios_passkeys WHERE credential_hash = %s", (_cid_hash(unb64(body.get("id"))),))
    if not r or r["rp_id"] != ch["rp_id"]:
        raise Invalid("This passkey is not known here (it may have been removed)")
    raw_ad = unb64(body.get("authenticatorData"))
    _, count, _ = _auth_data(raw_ad, ch["rp_id"])
    if not _verify(_key(unb64(r["public_key"]), r["alg"]), r["alg"], unb64(body.get("signature")), raw_ad + hashlib.sha256(raw_cd).digest()):
        raise Invalid("The passkey's signature is not right")
    if (count or r["sign_count"]) and count <= r["sign_count"]:  # a passkey that counts its uses never goes back: a copy would
        raise Invalid("This passkey answered out of turn; remove it in Settings › Account and add it again")
    db.ex("UPDATE ios_passkeys SET sign_count = %s, last_used_at = %s WHERE id = %s", (count, int(time.time()), r["id"]))
    return r["user_id"]
