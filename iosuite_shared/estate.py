"""The estate planning PDF: everything the suite knows about one person that the family needs when that person dies,
gathered from every app into one PDF to print or keep somewhere safe.

What goes in is each app's to say. An app sets `auth.estate_data = fn(user_id)`, which returns its sections:

    [{"title": "Documents", "order": 20, "intro": "…",
      "table": {"columns": ["Account", "Bank", "Balance"], "rows": [["Checking", "Chase", "$1,200.00"]]},
      "items": [{"title": "Passport", "subtitle": "Belgium", "rows": [["Number", "EM123456"]], "notes": "…",
                 "files": [{"ref": "12-34", "name": "front.jpg", "mime": "image/jpeg"}]}]}]

Every value is text the app wrote out already (its money in its currency, its dates). `order` places the section
(10 contacts, 20 documents, 30 money, 40 things; 50 by default). A file an item names is fetched from the same app
with `auth.estate_file = fn(user_id, ref) -> (bytes, mime, name)` (LookupError: no such file of theirs) and put at
the end of the PDF: a picture as it is (made smaller), a PDF whole.

Who may make it (Alex, 2026-11-21): a suite admin, for anyone (their private papers included: after a death those
are what the family needs), and each person for themselves. Private ioMoney accounts are the exception (Alex,
2026-11-22): nobody but the people their owner named sees them, so a PDF made by someone else lists only those of the
person's accounts the asker sees too. Every app serves its part at
GET /api/auth/estate/{id} (and the files at …/files/{ref}) under that rule; a person with no role in an app gets
nothing from it. The PDF is made by whichever app it is asked of, at GET /api/auth/estate/{id}/pdf: it answers its
own part and asks the others with the asker's own sign-in, as the panel that deletes an account does
(iosuite_shared.persondata, links.as_viewer). An app that cannot be reached is named on the first page, so nobody
takes the PDF for complete when it is not.

Text: DejaVu Sans when the system has it, else Liberation or FreeSans; without any, Helvetica, which writes Western
European languages, with anything else replaced.
"""
import datetime as dt
import io
import logging
import os
import re
import urllib.error
from concurrent.futures import ThreadPoolExecutor

from iosuite_shared import helper, links, suite, users

log = logging.getLogger("iosuite_shared.estate")
PATH = "/api/auth/estate/"
UA = "ioSuite estate"
ASK_S = 60            # seconds an app may take to gather its part
FILE_S = 60           # and to send one file
FILE_BYTES = 40 << 20  # a file larger than this is named, not put in
PICTURE_SIDE = 2000   # pixels on a picture's long side: scans keep their small print
MAX_SECTIONS, MAX_ITEMS, MAX_ROWS, MAX_FILES, MAX_TEXT = 20, 2000, 200, 40, 20000
FONTS = [(f"{d}/DejaVuSans.ttf", f"{d}/DejaVuSans-Bold.ttf") for d in
         ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF", "/usr/local/share/fonts")] + [
         ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
         ("/usr/share/fonts/truetype/freefont/FreeSans.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
         ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")]


# ---- who may
def may(me: dict | None, user_id: int) -> bool:
    """A suite admin for anyone, a person for themselves."""
    return bool(me) and (users.is_suite_admin(me) or me.get("id") == int(user_id))


# ---- an app's part, cleaned
def _s(v, n: int = 500) -> str:
    return "" if v is None else str(v).strip()[:n]


def clean(sections) -> list:
    """An app's sections as the PDF takes them: only text, nothing empty, within bounds."""
    out = []
    for s in (sections if isinstance(sections, list) else [])[:MAX_SECTIONS]:
        if not isinstance(s, dict) or not _s(s.get("title")):
            continue
        sec = {"title": _s(s["title"], 120), "order": s.get("order") if isinstance(s.get("order"), int) else 50,
               "intro": _s(s.get("intro"), 2000), "items": [], "table": None}
        t = s.get("table")
        if isinstance(t, dict) and isinstance(t.get("columns"), list) and isinstance(t.get("rows"), list):
            cols = [_s(c, 60) for c in t["columns"]][:8]
            rows = [[_s(c, 200) for c in r][:len(cols)] for r in t["rows"][:MAX_ITEMS] if isinstance(r, list)]
            if cols and rows:
                sec["table"] = {"columns": cols, "rows": rows}
        for i in (s.get("items") if isinstance(s.get("items"), list) else [])[:MAX_ITEMS]:
            if not isinstance(i, dict) or not _s(i.get("title")):
                continue
            rows = [[_s(r[0], 80), _s(r[1], 2000)] for r in (i.get("rows") or [])[:MAX_ROWS]
                    if isinstance(r, (list, tuple)) and len(r) == 2 and _s(r[1])]
            files = [{"ref": _s(f.get("ref"), 64), "name": _s(f.get("name"), 200) or "file", "mime": _s(f.get("mime"), 100)}
                     for f in (i.get("files") or [])[:MAX_FILES] if isinstance(f, dict) and _s(f.get("ref"))]
            sec["items"].append({"title": _s(i["title"], 300), "subtitle": _s(i.get("subtitle"), 300), "rows": rows,
                                 "notes": _s(i.get("notes"), MAX_TEXT), "files": files})
        if sec["items"] or sec["table"] or sec["intro"]:
            out.append(sec)
    return out


def local(auth, user_id: int, me: dict | None = None) -> list:
    """This app's part. An app whose estate_data takes `asker` is told who asks (the account making the PDF), to
    leave out what that person may not see even as a suite admin (ioMoney: someone's private accounts)."""
    fn = getattr(auth, "estate_data", None)
    if not fn:
        return []
    import inspect
    takes = "asker" in inspect.signature(fn).parameters
    return clean(fn(int(user_id), asker=me) if takes else fn(int(user_id)))


def local_file(auth, user_id: int, ref: str) -> tuple[bytes, str, str]:
    fn = getattr(auth, "estate_file", None)
    if not fn:
        raise LookupError("No such file")
    return fn(int(user_id), str(ref))


# ---- asking the other apps, with the asker's own sign-in
def _ask(request, app: str, user_id: int) -> list:
    try:
        got = links.as_viewer(request, app, f"{PATH}{int(user_id)}", user_agent=UA, patient=True, timeout=ASK_S)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError("it is on an older version that cannot do this")
        if e.code in (401, 403):
            raise RuntimeError(f"it did not take your sign-in ({e.code}); open it once and sign in there")
        raise RuntimeError(f"it answered {e.code}")
    except links.Unreachable as e:
        if e.why is None:
            raise RuntimeError("it has no address to reach it at (PUBLIC_URL or INTERNAL_URL)")
        raise RuntimeError(f"it did not answer ({type(e.why).__name__})")
    return clean(got.get("sections") if isinstance(got, dict) else None)


def _ask_file(request, app: str, user_id: int, ref: str) -> tuple[bytes, str]:
    return links.as_viewer(request, app, f"{PATH}{int(user_id)}/files/{ref}", raw=True, user_agent=UA, patient=True,
                           timeout=FILE_S, limit=FILE_BYTES + 1)


def gather(auth, request, user_id: int, me: dict | None = None) -> list:
    """Every app's part: [{app, name, sections, error}] in the suite's order (admin tools keep nothing per person).
    A person making their own is asked only of the apps they have a role in: the others have nothing of theirs."""
    mine = me is not None and not users.is_suite_admin(me)
    entries = [a for a in (suite.visible(me) if mine else suite.apps()) if not a.get("adminTool")]
    if not any(a["app"] == auth.app for a in entries) and not suite.is_admin_tool(auth.app) and not (mine and not users.is_signed_in(me)):
        entries.insert(0, {"app": auth.app, "name": auth.label})

    def one(a):
        out = {"app": a["app"], "name": a.get("name") or a["app"], "sections": [], "error": None}
        try:
            out["sections"] = local(auth, user_id, me) if a["app"] == auth.app else _ask(request, a["app"], user_id)
        except Exception as e:  # noqa: BLE001  one app's trouble never stops the others
            if a["app"] == auth.app:
                log.exception("%s: the estate part of account %s", auth.app, user_id)
            out["error"] = str(e) or type(e).__name__
        return out
    if not entries:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(entries)), thread_name_prefix="estate") as pool:
        return list(pool.map(one, entries))


# ---- the PDF
def _fpdf():
    from fpdf import FPDF  # imported here: only this page needs it

    class Doc(FPDF):
        def __init__(self, title: str, foot: str):
            super().__init__(format="letter", unit="mm")
            self.foot = foot
            self.set_margins(18, 18, 18)
            self.set_auto_page_break(True, 18)
            self.set_title(title)
            self.set_creator("ioSuite")
            self.uni = False
            for path, bold in FONTS:
                if os.path.exists(path):
                    try:
                        self.add_font("Body", "", path)
                        self.add_font("Body", "B", bold if os.path.exists(bold) else path)
                        self.uni = True
                        break
                    except Exception:  # noqa: BLE001  a font it cannot read: the next one, or Helvetica
                        continue
            self.face = "Body" if self.uni else "Helvetica"

        def t(self, s) -> str:
            s = "" if s is None else str(s)
            if self.uni:
                return s
            s = s.translate({0x2019: "'", 0x2018: "'", 0x201c: '"', 0x201d: '"', 0x2013: "-", 0x2014: "-", 0x2026: "...",
                             0x203a: ">", 0x20ac: "EUR ", 0x20b9: "INR ", 0x00b7: "-"})
            return s.encode("latin-1", "replace").decode("latin-1")

        def font(self, size: float, bold: bool = False, grey: bool = False):
            self.set_font(self.face, "B" if bold else "", size)
            self.set_text_color(*((105, 105, 105) if grey else (20, 20, 20)))

        def footer(self):
            self.set_y(-12)
            self.font(7.5, grey=True)
            self.cell(0, 5, self.t(f"{self.foot} · page {self.page_no()}"), align="C")

        def para(self, text: str, size: float = 10, bold: bool = False, grey: bool = False, h: float = 5.2):
            self.font(size, bold, grey)
            self.multi_cell(0, h, self.t(text), align="L", new_x="LMARGIN", new_y="NEXT")

        def room(self, mm: float) -> None:
            if self.get_y() + mm > self.h - self.b_margin:
                self.add_page()

    return Doc


def _picture(raw: bytes):
    """(JPEG, width, height), upright and at most PICTURE_SIDE on its long side; None when it is no picture."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        im = Image.open(io.BytesIO(raw))
        if im.width * im.height > 120_000_000:
            return None
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            back = Image.new("RGB", im.size, (255, 255, 255))
            back.paste(im, mask=im.split()[-1])
            im = back
        else:
            im = im.convert("RGB")
        im.thumbnail((PICTURE_SIDE, PICTURE_SIDE), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=82, optimize=True)
        return out.getvalue(), im.width, im.height
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def _rows(pdf, rows: list) -> None:
    key = 44
    for k, v in rows:
        pdf.room(6)
        y = pdf.get_y()
        pdf.font(9, grey=True)
        tall = 4.8 * len(pdf.multi_cell(key - 2, 4.8, pdf.t(k), align="L", dry_run=True, output="LINES"))
        pdf.multi_cell(key - 2, 4.8, pdf.t(k), align="L", new_x="RIGHT", new_y="TOP")
        pdf.set_x(pdf.l_margin + key)
        pdf.font(9.5)
        pdf.multi_cell(0, 4.8, pdf.t(v), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(max(pdf.get_y(), y + tall) + 0.6)


def _table(pdf, t: dict) -> None:
    pdf.font(9)
    with pdf.table(text_align="LEFT", line_height=5, padding=1.2, first_row_as_headings=True,
                   borders_layout="HORIZONTAL_LINES") as table:
        head = table.row()
        for c in t["columns"]:
            head.cell(pdf.t(c))
        for r in t["rows"]:
            row = table.row()
            for c in r + [""] * (len(t["columns"]) - len(r)):
                row.cell(pdf.t(c))
    pdf.ln(3)


def render(person: dict, parts: list, made_by: str, fetch, today: dt.date | None = None) -> bytes:
    """The PDF. person: {displayName, name, email}; parts: gather()'s list; fetch(app, ref) -> (bytes, mime) for the
    files the items name."""
    from pypdf import PdfReader, PdfWriter
    today = today or dt.date.today()
    who = person.get("displayName") or person.get("name") or "?"
    made = today.strftime("%B %-d, %Y")
    Doc = _fpdf()
    pdf = Doc(f"Estate planning: {who}", f"Estate planning: {who} · made {made} · confidential")
    sections = sorted(((s, p) for p in parts for s in p["sections"]), key=lambda x: (x[0]["order"], x[1]["name"].lower()))
    away = [p for p in parts if p["error"]]

    # the first page
    pdf.add_page()
    pdf.font(22, bold=True)
    pdf.multi_cell(0, 10, pdf.t(who), new_x="LMARGIN", new_y="NEXT")
    pdf.para("Estate planning: what the family needs to know", 13, grey=True, h=7)
    pdf.ln(4)
    _rows(pdf, [["Account", person.get("name") or ""], ["Email", person.get("email") or ""],
                ["Made", f"{made}, by {made_by}"]])
    pdf.ln(3)
    pdf.para("This holds private information: account details, document numbers and scans. Keep it somewhere safe and "
             "share it only with the people who settle the estate.", 9.5, grey=True)
    pdf.ln(4)
    pdf.para("In this PDF", 12, bold=True, h=7)
    if sections:
        for s, p in sections:
            n = len(s["items"]) or len((s["table"] or {}).get("rows") or [])
            pdf.para(f"{s['title']} ({p['name']}){f': {n}' if n else ''}", 10)
    else:
        pdf.para("Nothing was found for this person in any app.", 10, grey=True)
    if away:
        pdf.ln(3)
        pdf.para("Not complete: these apps could not be asked", 11, bold=True, h=6)
        for p in away:
            pdf.para(f"{p['name']}: {p['error']}", 9.5, grey=True)
        pdf.para("Make the PDF again once they can be reached.", 9.5, grey=True)

    # the sections
    files: list = []  # (app, item title, file)
    for s, p in sections:
        pdf.add_page()
        pdf.start_section(pdf.t(s["title"]))
        pdf.font(16, bold=True)
        pdf.multi_cell(0, 8, pdf.t(s["title"]), new_x="LMARGIN", new_y="NEXT")
        pdf.para(f"From {p['name']}", 9, grey=True)
        pdf.ln(2)
        if s["intro"]:
            pdf.para(s["intro"], 9.5)
            pdf.ln(2)
        if s["table"]:
            _table(pdf, s["table"])
        for i in s["items"]:
            pdf.room(18)
            pdf.font(11.5, bold=True)
            pdf.multi_cell(0, 6, pdf.t(i["title"]), new_x="LMARGIN", new_y="NEXT")
            if i["subtitle"]:
                pdf.para(i["subtitle"], 9, grey=True, h=4.6)
            pdf.ln(1)
            rows = list(i["rows"])
            if i["files"]:
                rows.append(["Scans", ", ".join(f["name"] for f in i["files"]) + " (at the end)"])
                files += [(p["app"], i["title"], f) for f in i["files"]]
            _rows(pdf, rows)
            if i["notes"]:
                pdf.ln(0.5)
                pdf.para(i["notes"], 9.5)
            pdf.ln(2)
            pdf.set_draw_color(225, 225, 225)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)

    # the files: pictures here, PDFs whole after the rest
    pdfs: list = []
    if files:
        pdf.add_page()
        pdf.start_section("Scans")
        pdf.font(16, bold=True)
        pdf.multi_cell(0, 8, pdf.t("Scans"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        for app, title, f in files:
            try:
                raw, mime = fetch(app, f["ref"])
            except Exception as e:  # noqa: BLE001  named, so it can be found in the app
                log.warning("estate: %s file %s: %s", app, f["ref"], e)
                raw, mime = None, ""
            label = f"{title}: {f['name']}"
            if raw is not None and len(raw) > FILE_BYTES:
                raw = None
            if raw and (mime or f["mime"]).split(";")[0].strip() == "application/pdf":
                pdfs.append((label, raw))
                pdf.room(8)
                pdf.para(f"{label}: its pages follow at the end", 9.5, grey=True)
                continue
            pic = _picture(raw) if raw else None
            if not pic:
                pdf.room(8)
                pdf.para(f"{label}: not included here (open it in the app)", 9.5, grey=True)
                continue
            jpeg, w, h = pic
            width = pdf.epw
            height = width * h / w
            if height > 190:
                height, width = 190, 190 * w / h
            pdf.room(height + 10)
            pdf.para(label, 9.5, bold=True)
            pdf.image(io.BytesIO(jpeg), x=pdf.l_margin, w=width, h=height)
            pdf.ln(5)
    out = bytes(pdf.output())
    if not pdfs:
        return out
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(out)))
    for label, raw in pdfs:
        try:
            start = len(writer.pages)
            writer.append(PdfReader(io.BytesIO(raw)))
            writer.add_outline_item(label, start)
        except Exception as e:  # noqa: BLE001  a PDF pypdf cannot read is left out
            log.warning("estate: could not put in %s: %s", label, e)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _render_fetched(person: dict, parts: list, made_by: str, got: dict) -> bytes:
    """render(), in the helper (iosuite_shared.helper), with the files fetched beforehand by the copy: got[(app, ref)]
    is (bytes, mime), or the text of why it could not be had."""
    def fetch(app, ref):
        v = got.get((app, ref))
        if v is None or isinstance(v, str):
            raise LookupError(v or "not fetched")
        return v
    return render(person, parts, made_by, fetch)


def filename(person: dict, today: dt.date | None = None) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "-", person.get("displayName") or person.get("name") or "person").strip("-") or "person"
    return f"Estate-planning-{name}-{(today or dt.date.today()).isoformat()}.pdf"


def build(auth, request, me: dict, user_id: int) -> tuple[bytes, str]:
    """(the PDF, its file name) for the person, made as `me` (may() said yes)."""
    person = users.get(int(user_id))
    if not person:
        raise LookupError("No such person")
    parts = gather(auth, request, user_id, me)

    def fetch(app, ref):
        if app == auth.app:
            raw, mime, _name = local_file(auth, user_id, ref)
            return raw, mime
        return _ask_file(request, app, user_id, ref)
    made_by = me.get("displayName") or me.get("name") or "?"
    log.info("%s: estate PDF of account %s made by %s", auth.app, user_id, me.get("name"))
    # the scans are asked for here (as the viewer, from the apps that keep them); the PDF is put together in the
    # helper, where decoding the scans and reading the PDFs among them cannot take the copy down
    got: dict = {}
    for p in parts:
        for s in p["sections"]:
            for i in s["items"]:
                for f in i["files"]:
                    key = (p["app"], f["ref"])
                    if key in got:
                        continue
                    try:
                        got[key] = fetch(*key)
                    except Exception as e:  # noqa: BLE001  named in the PDF, so it can be found in the app
                        got[key] = f"{type(e).__name__}: {e}"
    return helper.call(_render_fetched, person, parts, made_by, got, timeout=600), filename(person)
