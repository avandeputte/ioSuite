"""ioThings's part of the estate planning PDF: the things that are the person's, most costly first."""
from iosuite_shared import testing, users


def new(client, **kw):
    r = client.post("/api/items", json={"name": "A thing", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_their_things(client):
    testing.add_account(client, {"name": "emma", "password": "secret123", "role": "member", "displayName": "Emma Smith"})
    emma = users.find("emma")["id"]
    assert client.get(f"/api/auth/estate/{emma}").json() == {"sections": []}
    garage = client.post("/api/locations", json={"name": "Garage"}).json()
    new(client, name="Bike", people=["emma"], locationId=garage["id"], serialNumber="SN-1", purchaseDate="2024-03-01",
        purchasePrice="400", insured=True)
    new(client, name="Watch", people=["emma"], purchasePrice="1200")
    new(client, name="Chairs", people=["emma"], quantity=2)
    new(client, name="Boiler", purchasePrice="5000")  # the household's
    got = client.get(f"/api/auth/estate/{emma}").json()["sections"][0]
    assert got["title"] == "Things" and "3 things, bought for $1,600.00 all together" in got["intro"]
    assert got["table"]["rows"] == [["Watch", "", "", "", "$1,200.00", ""],
                                    ["Bike", "Garage", "SN-1", "Mar 1, 2024", "$400.00", "Yes"],
                                    ["Chairs (2)", "", "", "", "", ""]]
