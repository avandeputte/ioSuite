"""The estate planning PDF (iosuite_shared.estate): every app's part in one PDF, a suite admin for anyone and a person
for themselves, scans put in, and an app that could not be asked named on the first page."""
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from iosuite_shared import estate, links, suite, users
from iosuite_shared.fastapi import Auth


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 30, 30)).save(out, "PNG")
    return out.getvalue()


def _pdf() -> bytes:
    from fpdf import FPDF
    p = FPDF()
    p.add_page()
    p.set_font("Helvetica", size=12)
    p.cell(0, 10, "Last will and testament")
    return bytes(p.output())


def make_app(key, data=None, files=None):
    auth = Auth(key, app_label=key.capitalize(), register=False)
    if data:
        auth.estate_data = data
    if files:
        def one(uid, ref):
            if ref not in files:
                raise LookupError(ref)
            return files[ref]
        auth.estate_file = one
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())
    app.include_router(auth.admin_router())
    return auth, app


@pytest.fixture
def suite_of_three(monkeypatch):
    """ioStart (where the PDF is made, nothing of its own), ioDocs (a document with two scans) and ioMoney (away)."""
    def docs(uid):
        return [{"title": "Documents", "order": 20, "items": [
            {"title": "Will", "rows": [["Kind", "Will or legal paper"], ["Number", ""]], "notes": "With the notary",
             "files": [{"ref": "1-1", "name": "will.pdf", "mime": "application/pdf"}, {"ref": "1-2", "name": "page.png", "mime": "image/png"},
                       {"ref": "1-3", "name": "gone.png", "mime": "image/png"}]},
            {"title": "", "rows": []}]}]  # an item without a title is dropped
    _start_auth, start_app = make_app("iostart")
    _docs_auth, docs_app = make_app("iodocs", docs, {"1-1": (_pdf(), "application/pdf", "will.pdf"), "1-2": (_png(), "image/png", "page.png")})
    suite.register("iodocs", name="ioDocs", url="https://docs.example.com")
    suite.register("iomoney", name="ioMoney", url="https://money.example.com")

    def client_for(request):
        return TestClient(docs_app, base_url="http://docs.example.com", headers=links.viewer_headers(request))

    def ask(request, app, uid):
        if app == "iomoney":
            raise RuntimeError("it did not answer (URLError)")
        r = client_for(request).get(f"{estate.PATH}{uid}")
        if r.status_code != 200:
            raise RuntimeError(f"it answered {r.status_code}")
        return estate.clean(r.json()["sections"])

    def ask_file(request, app, uid, ref):
        r = client_for(request).get(f"{estate.PATH}{uid}/files/{ref}")
        r.raise_for_status()
        return r.content, r.headers["content-type"]
    monkeypatch.setattr(estate, "_ask", ask)
    monkeypatch.setattr(estate, "_ask_file", ask_file)
    return {"start_app": start_app, "docs_app": docs_app}


def signed_in(app, name, password="secret123"):
    c = TestClient(app, base_url="http://home.example.com")
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


def test_a_suite_admin_makes_anyones_pdf_from_every_app(suite_of_three):
    users.create("alex", "secret123", suite_admin=True)
    ann = users.create("ann", "secret123", display_name="Ann Smith")
    c = signed_in(suite_of_three["start_app"], "alex")
    r = c.get(f"/api/auth/estate/{ann['id']}/pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert "Estate-planning-Ann-Smith-" in r.headers["content-disposition"]
    pdf = PdfReader(io.BytesIO(r.content))
    text = "\n".join(p.extract_text() for p in pdf.pages)
    assert "Ann Smith" in text and "Documents (ioDocs): 1" in text
    assert "Not complete" in text and "ioMoney: it did not answer" in text  # the away app is named
    assert "With the notary" in text and "will.pdf, page.png, gone.png (at the end)" in text
    assert "page.png" in text and "gone.png: not included here" in text
    assert "Last will and testament" in pdf.pages[-1].extract_text()  # the PDF scan, whole, at the end
    assert [o.title for o in pdf.outline] == ["Documents", "Scans", "Will: will.pdf"]


def test_a_person_makes_their_own_and_nobody_elses(suite_of_three):
    users.create("alex", "secret123", suite_admin=True)
    ann = users.create("ann", "secret123")
    bob = users.create("bob", "secret123")
    c = signed_in(suite_of_three["start_app"], "ann")
    assert c.get(f"/api/auth/estate/{ann['id']}/pdf").status_code == 200
    assert c.get(f"/api/auth/estate/{bob['id']}/pdf").status_code == 403
    d = signed_in(suite_of_three["docs_app"], "ann")
    assert d.get(f"/api/auth/estate/{bob['id']}").status_code == 403
    assert d.get(f"/api/auth/estate/{bob['id']}/files/1-1").status_code == 403
    assert d.get(f"/api/auth/estate/{ann['id']}").json()["sections"][0]["items"][0]["title"] == "Will"
    assert d.get(f"/api/auth/estate/{ann['id']}/files/9-9").status_code == 404
    assert TestClient(suite_of_three["docs_app"]).get(f"/api/auth/estate/{ann['id']}").status_code == 401


def test_nothing_from_an_app_where_the_person_has_no_role(suite_of_three):
    users.create("alex", "secret123", suite_admin=True)
    ann = users.create("ann", "secret123")
    users.set_role(ann["id"], "iodocs", "none")
    c = signed_in(suite_of_three["start_app"], "ann")
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(c.get(f"/api/auth/estate/{ann['id']}/pdf").content)).pages)
    assert "Documents" not in text and "ioDocs" not in text  # not asked: nothing of hers there, and no "could not be asked"
    assert "ioMoney: it did not answer" in text


def test_clean_keeps_only_text_within_bounds():
    got = estate.clean([{"title": "A", "table": {"columns": ["x", "y"], "rows": [["1", "2", "3"], "no"]},
                         "items": [{"title": "i", "rows": [["k", ""], ["k2", 5], ["bad"]], "files": [{"ref": ""}, {"ref": "r"}]}]},
                        {"title": ""}, "nonsense"])
    assert got == [{"title": "A", "order": 50, "intro": "", "table": {"columns": ["x", "y"], "rows": [["1", "2"]]},
                    "items": [{"title": "i", "subtitle": "", "rows": [["k2", "5"]], "notes": "", "files": [{"ref": "r", "name": "file", "mime": ""}]}]}]


def test_nothing_anywhere_still_makes_a_pdf():
    out = estate.render({"displayName": "Bob"}, [{"app": "iotask", "name": "ioTask", "sections": [], "error": None}], "Alex", lambda a, r: None)
    assert "Nothing was found" in PdfReader(io.BytesIO(out)).pages[0].extract_text()


def test_an_app_may_be_told_who_asks():
    """estate_data that takes `asker` is given the account making the PDF (ioMoney leaves out private accounts the
    asker does not see); one that does not is called as before."""
    class A:
        pass
    seen = []
    a = A()
    a.estate_data = lambda uid, asker=None: seen.append((uid, asker)) or [{"title": "T", "intro": "x"}]
    assert estate.local(a, 7, {"id": 1})[0]["title"] == "T" and seen == [(7, {"id": 1})]
    a.estate_data = lambda uid: [{"title": "Old", "intro": "x"}]
    assert estate.local(a, 7, {"id": 1})[0]["title"] == "Old"
