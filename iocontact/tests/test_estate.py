"""ioContact's part of the estate planning PDF: the person's own card and their closest family, implied ones too."""
from iosuite_shared import users


def mk(client, book, **kw):
    r = client.post(f"/api/contacts?book={book}", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def test_their_card_and_closest_family(client, family_id):
    me = users.find("alex")["id"]
    assert client.get(f"/api/auth/estate/{me}").json()["sections"][0]["intro"].startswith("No ioContact card is linked")
    mom = mk(client, family_id, fn="Mary Doe", gender="F", phones=[{"label": "mobile", "value": "+1 555 0100"}])
    mk(client, family_id, fn="Sue Doe", gender="F", relations=[{"type": "parent", "relatedId": mom["id"]}])
    joe = mk(client, family_id, fn="Joe Friend")
    ann = mk(client, family_id, fn="Ann Doe", birthday={"year": 1970, "month": 3, "day": 3},
             emails=[{"label": "home", "value": "ann@example.com"}],
             addresses=[{"label": "home", "street": "12 Oak St", "city": "Springfield", "region": "IL", "postcode": "62701"}],
             relations=[{"type": "parent", "relatedId": mom["id"]}, {"type": "friend", "relatedId": joe["id"]},
                        {"type": "child", "relatedName": "Baby Doe"}])
    assert client.put("/api/me-contact", json={"contactId": ann["id"]}).status_code == 200
    sec = client.get(f"/api/auth/estate/{me}").json()["sections"]
    assert [s["title"] for s in sec] == ["Contact details and family"]
    items = sec[0]["items"]
    assert [(i["title"], i["subtitle"]) for i in items] == [
        ("Ann Doe", "Their own card"), ("Mary Doe", "Mother"), ("Sue Doe", "Sister (through Mary Doe)"), ("Baby Doe", "Child")]
    assert ["Birthday", "March 3, 1970"] in items[0]["rows"] and ["Email (home)", "ann@example.com"] in items[0]["rows"]
    assert ["Address (home)", "12 Oak St, Springfield IL 62701"] in items[0]["rows"]
    assert ["Phone (mobile)", "+1 555 0100"] in items[1]["rows"]
