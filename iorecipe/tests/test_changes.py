"""Who added a recipe and who changed it (iosuite_shared.stamp)."""


def test_recipe_record(client):
    r = client.post("/api/recipes", json={"title": "Pancakes", "ingredients": ["flour"], "steps": ["Mix."]}).json()
    assert client.patch(f"/api/recipes/{r['id']}", json={"title": "Fluffy pancakes"}).status_code == 200
    rec = client.get(f"/api/changes/recipe/{r['id']}").json()
    assert rec["added"]["by"] == "alex" and rec["history"][0]["what"] == "title"
    assert client.delete(f"/api/recipes/{r['id']}").status_code == 200
    assert client.get(f"/api/changes/recipe/{r['id']}").status_code == 404
