"""Who added a thing and who changed it (iosuite_shared.stamp)."""


def test_thing_record(client):
    it = client.post("/api/items", json={"name": "Boiler"}).json()
    assert client.patch(f"/api/items/{it['id']}", json={"name": "Boiler (Vaillant)", "notes": "serviced"}).status_code == 200
    rec = client.get(f"/api/changes/item/{it['id']}").json()
    assert rec["added"]["by"] == "alex" and "name" in rec["history"][0]["what"]
