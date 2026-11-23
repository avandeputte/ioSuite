"""Who added a task and who changed it (iosuite_shared.stamp), and only to people who may see it."""
from iosuite_shared import testing


def test_task_record(client, family_id):
    t = client.post("/api/tasks", json={"title": "Call the plumber", "listId": family_id}).json()
    assert client.patch(f"/api/tasks/{t['id']}", json={"title": "Call the plumber today", "notes": "before noon"}).status_code == 200
    rec = client.get(f"/api/changes/task/{t['id']}").json()
    assert rec["added"]["by"] == "alex" and rec["history"][0]["what"] == "title, notes"
    testing.add_account(client, {"name": "meg", "password": "secret123", "role": "member"})
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "meg", "password": "secret123"}).status_code == 200
    mine = client.post("/api/tasks", json={"title": "My own"}).json()
    assert client.get(f"/api/changes/task/{t['id']}").json()["added"]["by"] == "alex"  # the family's list: she sees it
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 200
    assert client.get(f"/api/changes/task/{mine['id']}").status_code == 404  # meg's own: not even an admin
