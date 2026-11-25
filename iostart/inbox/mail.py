"""The suite's mailbox: reading it over IMAP, and taking one message apart into what the Inbox keeps.

    with Mailbox(host, port, user, password, folder) as box:
        for uid, raw in box.unread(limit):
            ...                   # keep it (iostart/inbox/__init__.py)
            box.seen(uid)         # only then marked read, so a message is never lost between the two

Port 993 is IMAP over TLS, any other port starts TLS on a plain connection (STARTTLS), and a server that offers no TLS
there is refused: the password never goes out in the clear. The messages are left in the mailbox, marked read.

parse() turns a message into {from, name, to, subject, sent, id, text, files, invite, trusted, forwarded}: the plain
text (an HTML-only message made into text; no HTML is ever kept or shown), the attachments (PDF, pictures, calendar
files; a forwarded message's own attachments too), and whether the mail server that took it in vouched for the
sender (trusted: see vouched()).
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import hashlib
import html
import imaplib
import re
import ssl
import time

MAX_MESSAGE = 30 << 20     # a larger message is not fetched (its size is asked first)
MAX_TEXT = 200_000         # characters of a message's text that are kept
MAX_FILES = 20             # attachments kept of one message
TIMEOUT = 30
KEPT = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic", "image/heif", "text/calendar"}
EXT = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
       ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif", ".ics": "text/calendar"}


class MailError(Exception):
    """The mailbox could not be read: the words say why, for the person setting it up."""


class Mailbox:
    def __init__(self, host: str, port: int, user: str, password: str, folder: str = "INBOX"):
        self.host, self.port, self.user, self.password, self.folder = host, int(port or 993), user, password, folder or "INBOX"
        self.imap = None

    def __enter__(self):
        ctx = ssl.create_default_context()
        try:
            if self.port == 993:
                self.imap = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx, timeout=TIMEOUT)
            else:
                self.imap = imaplib.IMAP4(self.host, self.port, timeout=TIMEOUT)
                if "STARTTLS" not in self.imap.capabilities:
                    raise MailError("The mail server offers no encryption on this port; use port 993")
                self.imap.starttls(ssl_context=ctx)
        except MailError:
            self._drop()
            raise
        except ssl.SSLError as e:
            self._drop()
            raise MailError(f"The mail server's certificate was not accepted ({e.reason or e})") from None
        except (OSError, imaplib.IMAP4.error) as e:
            self._drop()
            raise MailError(f"Could not reach {self.host}:{self.port} ({e})") from None
        try:
            self.imap.login(self.user, self.password)
        except imaplib.IMAP4.error:
            self._drop()
            raise MailError("The mail server did not take this user name and password") from None
        typ, _ = self.imap.select(_quote(self.folder))
        if typ != "OK":
            self._drop()
            raise MailError(f"The mailbox has no folder {self.folder}")
        return self

    def __exit__(self, *exc):
        self._drop()

    def _drop(self):
        if self.imap is not None:
            try:
                self.imap.logout()
            except Exception:  # noqa: BLE001 - going anyway
                pass
            self.imap = None

    def unread(self, limit: int = 25):
        """(uid, the message's bytes or None when it is too large to fetch) of the messages not read yet, the oldest
        first, at most limit of them."""
        typ, data = self.imap.uid("SEARCH", None, "UNSEEN")
        if typ != "OK":
            raise MailError("The mail server would not list the unread messages")
        uids = (data[0] or b"").split()[:limit]
        for uid in uids:
            typ, got = self.imap.uid("FETCH", uid, "(RFC822.SIZE)")
            m = re.search(rb"RFC822\.SIZE (\d+)", got[0] if got and isinstance(got[0], bytes) else b"")
            if m and int(m.group(1)) > MAX_MESSAGE:
                yield uid.decode(), None
                continue
            typ, got = self.imap.uid("FETCH", uid, "(BODY.PEEK[])")
            raw = next((p[1] for p in got or [] if isinstance(p, tuple) and len(p) > 1), None)
            if typ == "OK" and raw:
                yield uid.decode(), raw

    def seen(self, uid: str) -> None:
        self.imap.uid("STORE", uid, "+FLAGS", "(\\Seen)")


def _quote(folder: str) -> str:
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ------------------------------------------------------------------ taking a message apart

def _addr(v) -> tuple[str, str]:
    name, addr = email.utils.parseaddr(str(v or ""))
    return name.strip().strip('"')[:200], addr.strip().lower()[:320]


def _text_of_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table)>", "\n", s)
    s = re.sub(r"(?i)</t[dh]>", "  ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", "\n".join(ln.strip() for ln in s.splitlines())).strip()


def _decoded(part) -> str:
    try:
        return part.get_content()
    except (LookupError, UnicodeError, AssertionError, KeyError):
        raw = part.get_payload(decode=True) or b""
        return raw.decode("utf-8", "replace")


def _mime_of(part) -> str | None:
    """A kept attachment's type (by what it says, else by its name), or None for one that is not kept."""
    mime = (part.get_content_type() or "").lower()
    if mime in KEPT:
        return mime
    name = (part.get_filename() or "").lower()
    for ext, m in EXT.items():
        if name.endswith(ext):
            return m
    return None


def vouched(msg, sender: str) -> bool:
    """Whether the mail server that took the message in says the sender is who the From line says: in its own
    Authentication-Results line, the topmost one (each server puts its line above the ones that came with the message,
    so the topmost is the last server's: the mailbox's own), DMARC passed, or DKIM passed for the sender's own domain
    (or one it is part of). A sender's address alone is easy to make up; this is what Gmail, Fastmail and other
    providers check for their spam filter."""
    results = msg.get_all("Authentication-Results") or []
    if not results or "@" not in sender:
        return False
    top = re.sub(r"\([^)]*\)", " ", str(results[0])).lower()
    domain = sender.rsplit("@", 1)[1]
    if re.search(r"\bdmarc\s*=\s*pass\b", top):
        m = re.search(r"\bheader\.from\s*=\s*([a-z0-9.-]+)", top)
        if not m or m.group(1) == domain:
            return True
    for m in re.finditer(r"\bdkim\s*=\s*pass\b([^;]*)", top):
        d = re.search(r"\bheader\.(?:d|i)\s*=\s*@?([a-z0-9.-]+)", m.group(1))
        if d and (domain == d.group(1) or domain.endswith("." + d.group(1))):
            return True
    return False


_FWD = re.compile(r"(?im)^[>\s]*(?:-{2,}\s*(?:Forwarded message|Original Message)\s*-{2,}|Begin forwarded message:)\s*$")
_FWD_FROM = re.compile(r"(?im)^[>\s*]*From:\*?\s*(.+)$")


def forwarded_from(text: str) -> tuple[str, str] | None:
    """(name, address) of the original sender of a message forwarded inline (Gmail's "Forwarded message", Apple
    Mail's "Begin forwarded message:", Outlook's "Original Message"), or None."""
    m = _FWD.search(text or "")
    if not m:
        return None
    f = _FWD_FROM.search(text, m.end())
    if not f or f.start() - m.end() > 400:
        return None
    line = f.group(1).replace("*", "").strip()
    name, addr = _addr(line)
    if not addr and "[mailto:" in line:  # Outlook: Name [mailto:a@b]
        name, addr = line.split("[mailto:")[0].strip(), line.split("[mailto:")[1].rstrip("]").strip().lower()
    return (name or (addr.split("@")[0] if addr else line[:200]), addr) if (name or addr) else None


def parse(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    name, sender = _addr(msg.get("From"))
    to = []
    for h in ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To"):
        for _, a in email.utils.getaddresses([str(v) for v in msg.get_all(h) or []]):
            if a and a.lower() not in to:
                to.append(a.lower())
    try:
        sent = email.utils.parsedate_to_datetime(str(msg.get("Date"))).timestamp()
    except (TypeError, ValueError, IndexError):
        sent = None
    mid = str(msg.get("Message-ID") or "").strip()
    texts, htmls, files, invite = [], [], [], None
    fwd = None
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        disp = part.get_content_disposition()
        mime = _mime_of(part)
        if mime == "text/calendar":
            body = part.get_payload(decode=True) or b""
            if invite is None and b"BEGIN:VCALENDAR" in body[:4096].upper():
                invite = body.decode("utf-8", "replace")
            if disp == "attachment" and len(files) < MAX_FILES:
                files.append({"name": _file_name(part, "invite.ics"), "mime": mime, "data": body})
            continue
        if mime and (disp in ("attachment", "inline") or part.get_filename() or not ctype.startswith("text/")):
            if len(files) < MAX_FILES:
                data = part.get_payload(decode=True) or b""
                if data:
                    files.append({"name": _file_name(part, "attachment"), "mime": mime, "data": data})
            continue
        if disp == "attachment":
            continue
        if ctype == "text/plain":
            texts.append(_decoded(part))
        elif ctype == "text/html":
            htmls.append(_text_of_html(_decoded(part)))
    text = "\n\n".join(t.strip() for t in texts if t.strip()) or "\n\n".join(t for t in htmls if t)
    # a message forwarded as an attachment (message/rfc822) is walked above; its sender is the original one
    for part in msg.walk():
        if part.get_content_type() == "message/rfc822":
            inner = part.get_payload()
            inner = inner[0] if isinstance(inner, list) and inner else inner
            if hasattr(inner, "get"):
                fwd = _addr(inner.get("From"))
                if not text:
                    text = f"Subject: {inner.get('Subject') or ''}"
            break
    if fwd is None:
        fwd = forwarded_from(text)
    return {"from": sender, "name": name, "to": to, "subject": str(msg.get("Subject") or "").strip()[:500],
            "sent": sent, "id": mid[:998], "key": hashlib.sha256(mid.encode() if mid else raw).hexdigest(),
            "text": text[:MAX_TEXT], "files": files, "invite": invite, "trusted": vouched(msg, sender),
            "forwarded": {"name": fwd[0], "from": fwd[1]} if fwd else None, "at": time.time()}


def _file_name(part, fallback: str) -> str:
    n = re.sub(r"[\x00-\x1f/\\]+", " ", str(part.get_filename() or "")).strip()
    return n[:255] or fallback
