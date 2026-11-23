"""ioDocs's part of the estate planning PDF: the person's papers (private ones too) and the household's, with scans."""
import io

from PIL import Image

from iosuite_shared import testing, users

from conftest import sign_in


def new(client, **kw):
    r = client.post("/api/documents", json={"title": "Passport", "kind": "passport", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 80, 20)).save(out, "PNG")
    return out.getvalue()


def test_their_papers_and_the_households(client):
    testing.add_account(client, {"name": "ava", "password": "secret123", "role": "member", "displayName": "Ava Calloway"})
    ava = users.find("ava")["id"]
    will = new(client, title="Ava's will", kind="legal", people=["ava"], visibility="private", issuer="Notary Jones",
               notes="The original is at the notary", fields={"Executor": "Riley"})
    scan = client.post(f"/api/documents/{will['id']}/files", params={"ext": "png", "read": "false"}, content=png(),
                       headers={"content-type": "image/png"}).json()["file"]
    new(client, title="Ava's passport", people=["ava", "alex"], number="X1")
    new(client, title="Home insurance", kind="insurance", visibility="family", number="HO-55")
    new(client, title="Alex's license", kind="driver_license", people=["alex"])
    new(client, title="Old passport", people=["ava"], archived=True)
    got = client.get(f"/api/auth/estate/{ava}").json()["sections"][0]
    assert [(i["title"], i["subtitle"]) for i in got["items"]] == [
        ("Ava's will", "Theirs"), ("Home insurance", "The household’s"), ("Ava's passport", "Theirs")]
    w = got["items"][0]
    assert ["Issued by", "Notary Jones"] in w["rows"] and ["Executor", "Riley"] in w["rows"] and w["notes"] == "The original is at the notary"
    assert ["Also for", users.find("alex")["displayName"]] in got["items"][2]["rows"]
    ref = w["files"][0]["ref"]
    assert ref == f"{will['id']}-{scan['id']}"
    assert client.get(f"/api/auth/estate/{ava}/files/{ref}").content == png()
    lic = next(d for d in client.get("/api/documents").json()["items"] if d["title"] == "Alex's license")
    assert client.get(f"/api/auth/estate/{ava}/files/{lic['id']}-1").status_code == 404  # not one of hers
    # Ava makes her own: the same; Alex's is not hers to ask for
    sign_in(client, "ava")
    assert len(client.get(f"/api/auth/estate/{ava}").json()["sections"][0]["items"]) == 3
    assert client.get(f"/api/auth/estate/{users.find('alex')['id']}").status_code == 403
