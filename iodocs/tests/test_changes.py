"""Who added a document and who changed it (iosuite_shared.stamp): the names of the fields, never what they hold."""


def test_document_record(client):
    d = client.post("/api/documents", json={"title": "Passport", "kind": "passport"}).json()
    assert client.patch(f"/api/documents/{d['id']}", json={"number": "P1234567"}).status_code == 200
    rec = client.get(f"/api/changes/document/{d['id']}").json()
    assert rec["added"]["by"] == "alex" and rec["history"][0]["what"] == "number"
    assert "P1234567" not in str(rec)
