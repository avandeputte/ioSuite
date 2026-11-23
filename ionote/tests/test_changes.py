"""Who added a note and who changed it (iosuite_shared.stamp)."""
NID = "8F6C1E2A-0000-4000-8000-0000000000AB"


def test_note_record(client, admin):
    assert client.put(f"/api/notes/{NID}", json={"title": "Groceries", "body": "milk"}).status_code == 200
    assert client.put(f"/api/notes/{NID}", json={"body": "milk, eggs"}).status_code == 200
    rec = client.get(f"/api/changes/note/{NID}").json()
    assert rec["added"]["by"] == "alex" and rec["history"][0]["what"] == "text"
    assert client.get(f"/api/changes/note/{NID.lower()}").json()["added"]  # the id in either case
