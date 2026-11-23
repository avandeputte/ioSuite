"""Two-step sign-in: after the password, a 6-digit code from a code app (TOTP, RFC 6238: SHA-1, 30 seconds), or one
of the recovery codes made when it was turned on. Off for every account until its owner turns it on in Settings ›
Account; a suite admin (or `iosuite-shared sign-in-reset NAME`) turns it off for someone who lost their phone.

While it is on, the account password alone signs in nowhere: the sign-in screen asks for the code, and what cannot
type one (a calendar app, a script: HTTP Basic, LDAP) needs an app password. A sign-in at the proxy and a passkey
(iosuite_shared.passkeys) are checks of their own and ask for no code.

A code is taken once: the step it was made for is kept, and that step or an earlier one is refused afterwards.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
import time
from urllib.parse import quote

from iosuite_shared import db
from iosuite_shared.errors import Invalid
from iosuite_shared.passwords import token_hash

PERIOD, DIGITS = 30, 6
WINDOW = 1  # a code of the step before or after is taken too (a phone's clock a little off)
RECOVERY_CODES = 8
ISSUER = "ioSuite"
PENDING_S = 3600  # a secret shown but never confirmed is forgotten after this


def code_at(secret: str, step: int) -> str:
    """The code of a secret (base32) for one 30-second step."""
    mac = hmac.new(base64.b32decode(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    at = mac[-1] & 15
    return f"{(struct.unpack('>I', mac[at:at + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS:0{DIGITS}d}"


def _row(user_id: int):
    return db.one("SELECT * FROM ios_two_step WHERE user_id = %s", (user_id,))


def enabled(user_id: int) -> bool:
    r = db.one("SELECT confirmed_at FROM ios_two_step WHERE user_id = %s", (user_id,))
    return bool(r and r["confirmed_at"])


def status(user_id: int) -> dict:
    """{on, since, recoveryLeft}."""
    r = _row(user_id)
    on = bool(r and r["confirmed_at"])
    return {"on": on, "since": r["confirmed_at"] if on else None, "recoveryLeft": len(db.json_load(r["recovery"], [])) if on else 0}


def uri(secret: str, name: str) -> str:
    """What a code app reads from the QR code."""
    return f"otpauth://totp/{quote(ISSUER)}:{quote(name)}?secret={secret}&issuer={quote(ISSUER)}&digits={DIGITS}&period={PERIOD}"


def begin(user: dict) -> dict:
    """A new secret for the account, not on yet: {secret, uri}. confirm() with a code from it turns it on."""
    if user.get("passwordless"):
        raise Invalid("A one-click account has no password to add a second step to")
    if enabled(user["id"]):
        raise Invalid("Two-step sign-in is already on")
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    db.ex("INSERT INTO ios_two_step (user_id, secret, created_at) VALUES (%s, %s, %s) "
          "ON DUPLICATE KEY UPDATE secret = VALUES(secret), created_at = VALUES(created_at), last_step = 0, recovery = NULL",
          (user["id"], secret, int(time.time())))
    return {"secret": secret, "uri": uri(secret, user["name"])}


def _totp(r, code: str) -> bool:
    """Whether the 6 digits are the code of this step (or the one before or after), and were not used before."""
    now = int(time.time()) // PERIOD
    for step in (now, now - 1, now + 1)[:1 + 2 * WINDOW]:
        if step > r["last_step"] and hmac.compare_digest(code_at(r["secret"], step), code):
            # two requests with the same code: only one moves last_step
            return db.ex("UPDATE ios_two_step SET last_step = %s WHERE user_id = %s AND last_step < %s", (step, r["user_id"], step)) == 1
    return False


def confirm(user_id: int, code: str) -> list:
    """Turn it on with a first code from the code app; the recovery codes, shown this once."""
    r = _row(user_id)
    if not r or r["confirmed_at"] or r["created_at"] < time.time() - PENDING_S:
        raise Invalid("Start again: the setup was not begun, or is too long ago")
    if not _totp(r, _digits(code)):
        raise Invalid("That code is not right. Check the clock of the phone and try the next code")
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(RECOVERY_CODES)]
    db.ex("UPDATE ios_two_step SET confirmed_at = %s, recovery = %s WHERE user_id = %s",
          (int(time.time()), json.dumps([token_hash(_plain(c)) for c in codes]), user_id))
    return codes


def _digits(code: str) -> str:
    return re.sub(r"\s", "", str(code or ""))


def _plain(code: str) -> str:
    return re.sub(r"[^0-9a-f]", "", str(code or "").lower())


def check(user_id: int, code: str) -> bool:
    """Whether the code signs the account in: the code app's 6 digits, or a recovery code (which is then used up)."""
    r = _row(user_id)
    if not r or not r["confirmed_at"]:
        return False
    digits = _digits(code)
    if re.fullmatch(rf"\d{{{DIGITS}}}", digits):
        return _totp(r, digits)
    plain = _plain(code)
    if len(plain) != 12:
        return False
    with db.tx():
        r = db.one("SELECT recovery FROM ios_two_step WHERE user_id = %s FOR UPDATE", (user_id,))
        left = db.json_load(r["recovery"], []) if r else []
        h = token_hash(plain)
        if h not in left:
            return False
        left.remove(h)
        db.ex("UPDATE ios_two_step SET recovery = %s WHERE user_id = %s", (json.dumps(left), user_id))
    return True


def disable(user_id: int) -> bool:
    return db.ex("DELETE FROM ios_two_step WHERE user_id = %s", (user_id,)) > 0


def counts() -> set:
    """The accounts that have it on (the admin's list of people)."""
    return {r["user_id"] for r in db.q("SELECT user_id FROM ios_two_step WHERE confirmed_at IS NOT NULL")}


def qr_svg(text: str) -> str:
    """The QR code of a text as an inline SVG (black on white, so a phone reads it on a dark page too)."""
    import io
    import segno
    out = io.BytesIO()
    segno.make(text, error="m").save(out, kind="svg", scale=5, border=3, xmldecl=False, svgns=True, nl=False, light="#fff", dark="#000")
    return out.getvalue().decode()
