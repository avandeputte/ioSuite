"""Who sees each account: the household's (everyone with a role here) or a private one, seen by its owner and the
people they name, and by nobody else: an admin or a suite admin is not let in by their role, anywhere the account
shows (the list, the transactions, the totals, the estate PDF)."""
import datetime as dt

from iosuite_shared import users

from iomoney import db, model, monarch
from conftest import sign_in
from test_api import add


def names(client):
    return sorted(a["name"] for a in client.get("/api/accounts").json()["items"])


def people(a):
    return [p["name"] for p in a["people"]]


def test_a_private_account_shown_to_some_people_only(client, as_user):
    add(client, name="Joint", balance=100)
    for n, role in (("jo", "member"), ("kid", "viewer"), ("sam", "member")):
        sign_in(client, "alex")
        as_user(n, role)
    jo, kid, sam = (users.find(n)["id"] for n in ("jo", "kid", "sam"))
    sign_in(client, "alex")
    picks = client.get("/api/people").json()["items"]
    assert picks[0]["name"] == "alex" and {p["name"] for p in picks} == {"alex", "jo", "kid", "sam"}
    ours = add(client, name="Alex and Jo", household=False, people=[jo], balance=1000)
    assert ours["household"] is False and ours["mine"] and people(ours) == ["alex", "jo"]
    mine = add(client, name="Alex alone", household=False, balance=5)
    assert people(mine) == ["alex"]
    today = dt.date.today().isoformat()
    assert client.post(f"/api/accounts/{ours['id']}/transactions", json={"day": today, "amount": -40, "merchant": "Florist"}).status_code == 201
    assert client.get("/api/networth").json()["netWorth"] == 1065

    # Jo sees it, works on it (a member), but only its owner says who sees it, deletes it or gives it to the household
    sign_in(client, "jo")
    assert names(client) == ["Alex and Jo", "Joint"]
    got = client.get(f"/api/accounts/{ours['id']}").json()
    assert got["writable"] and not got["mine"]
    assert client.get("/api/networth").json()["netWorth"] == 1060
    assert [t["merchant"] for t in client.get("/api/transactions?q=florist").json()["items"]] == ["Florist"]
    assert client.post(f"/api/accounts/{ours['id']}/transactions", json={"day": today, "amount": -2, "merchant": "Coffee"}).status_code == 201
    assert client.patch(f"/api/accounts/{ours['id']}", json={"people": [jo, sam]}).status_code == 403
    assert client.patch(f"/api/accounts/{ours['id']}", json={"household": True}).status_code == 403
    assert client.delete(f"/api/accounts/{ours['id']}").status_code == 403
    assert client.get(f"/api/accounts/{mine['id']}").status_code == 404

    # Sam sees neither, nor anything in them, nor in the totals
    sign_in(client, "sam")
    assert names(client) == ["Joint"]
    assert client.get(f"/api/accounts/{ours['id']}").status_code == 404
    assert client.get(f"/api/transactions?account={ours['id']}").json()["items"] == []
    assert client.get("/api/transactions?q=florist").json()["items"] == []
    assert client.get("/api/networth").json()["netWorth"] == 100
    assert client.get("/api/summary").json()["counts"]["accounts"] == 1

    # a viewer named on it looks, and changes nothing
    sign_in(client, "alex")
    r = client.patch(f"/api/accounts/{ours['id']}", json={"people": [jo, kid]})
    assert r.status_code == 200 and people(r.json()) == ["alex", "jo", "kid"]
    sign_in(client, "kid")
    got = client.get(f"/api/accounts/{ours['id']}").json()
    assert got["name"] == "Alex and Jo" and not got["writable"]
    assert client.post(f"/api/accounts/{ours['id']}/transactions", json={"day": today, "amount": -1}).status_code == 403

    # taken off the list: no longer seen
    sign_in(client, "alex")
    assert client.patch(f"/api/accounts/{ours['id']}", json={"people": [kid]}).status_code == 200
    sign_in(client, "jo")
    assert client.get(f"/api/accounts/{ours['id']}").status_code == 404
    assert client.get("/api/transactions?q=florist").json()["items"] == []

    # only people with a role here may be named; the household's are everyone's
    sign_in(client, "alex")
    r = client.post("/api/suite-admin/users", json={"name": "guest", "password": "secret123"})
    assert r.status_code in (200, 201), r.text
    guest = users.find("guest")["id"]
    assert client.patch(f"/api/accounts/{ours['id']}", json={"people": [guest]}).status_code == 400
    joint = next(a for a in client.get("/api/accounts").json()["items"] if a["name"] == "Joint")
    assert client.patch(f"/api/accounts/{joint['id']}", json={"people": [jo]}).status_code == 403
    # given to the household: everyone sees it, the list of people goes
    r = client.patch(f"/api/accounts/{ours['id']}", json={"household": True}).json()
    assert r["household"] and "people" not in r
    assert not db.q("SELECT 1 AS x FROM mny_account_people WHERE account_id = %s", (ours["id"],))
    sign_in(client, "sam")
    assert "Alex and Jo" in names(client)


def test_an_admin_never_sees_someone_elses_private_account(client, as_user):
    as_user("jo", "member")
    jo = users.find("jo")["id"]
    sign_in(client, "alex")
    as_user("sam", "member")
    theirs = add(client, name="Sam and Jo", household=False, people=[jo], balance=70)
    client.post(f"/api/accounts/{theirs['id']}/transactions", json={"amount": -9, "merchant": "Secret gift"})
    sign_in(client, "alex")  # admin here and suite admin
    assert "Sam and Jo" not in names(client)
    assert client.get(f"/api/transactions?account={theirs['id']}").json()["items"] == []
    for path in (f"/api/accounts/{theirs['id']}",
                 f"/api/accounts/{theirs['id']}/forecast", f"/api/accounts/{theirs['id']}/info"):
        assert client.get(path).status_code == 404, path
    assert client.get("/api/transactions?q=secret").json()["items"] == []
    assert client.patch(f"/api/accounts/{theirs['id']}", json={"people": [users.find("alex")["id"]]}).status_code == 404
    assert client.get("/api/networth").json()["netWorth"] == 0
    # and not in Sam's estate PDF made by the admin; Sam's own has it
    sam = users.find("sam")["id"]
    got = client.get(f"/api/auth/estate/{sam}").json()["sections"]
    assert not got or "Sam and Jo" not in [r[0] for r in (got[0]["table"] or {}).get("rows", [])]
    sign_in(client, "sam")
    rows = client.get(f"/api/auth/estate/{sam}").json()["sections"][0]["table"]["rows"]
    assert [r[0] for r in rows] == ["Sam and Jo"] and rows[0][-1] == "Theirs"
    # Jo's own estate PDF lists it as shared with them
    sign_in(client, "jo")
    rows = client.get(f"/api/auth/estate/{jo}").json()["sections"][0]["table"]["rows"]
    assert [r[0] for r in rows] == ["Sam and Jo"] and rows[0][-1] == "Shared with them"


def test_making_the_households_private_and_back(client, as_user):
    as_user("jo", "member")
    jo = users.find("jo")["id"]
    sign_in(client, "alex")
    as_user("ed", "editor")
    hh = add(client, name="Savings")  # an editor's new account: the household's
    assert hh["household"]
    r = client.patch(f"/api/accounts/{hh['id']}", json={"household": False, "people": [jo]}).json()
    assert r["household"] is False and people(r) == ["ed", "jo"] and r["mine"]
    sign_in(client, "alex")
    assert client.get(f"/api/accounts/{hh['id']}").status_code == 404


def test_deleting_the_owner_passes_a_shared_account_on(client, as_user):
    as_user("jo", "member")
    jo = users.find("jo")["id"]
    sign_in(client, "alex")
    as_user("ann", "member")
    ann = users.find("ann")["id"]
    shared = add(client, name="Ann and Jo", household=False, people=[jo])
    alone = add(client, name="Ann alone", household=False)
    sign_in(client, "alex")
    got = {i["what"]: (i["count"], i["kept"]) for i in client.get(f"/api/suite-admin/person-data/{ann}").json()["items"]}
    assert got["private account"] == (1, False)
    assert got["private account they shared, passed on to someone who sees it"] == (1, True)
    assert client.delete(f"/api/suite-admin/users/{ann}").status_code == 200
    assert not db.q("SELECT id FROM mny_accounts WHERE id = %s", (alone["id"],))
    assert db.one("SELECT owner_id FROM mny_accounts WHERE id = %s", (shared["id"],))["owner_id"] == jo
    assert not db.q("SELECT 1 AS x FROM mny_account_people WHERE account_id = %s", (shared["id"],))
    sign_in(client, "jo")
    assert client.get(f"/api/accounts/{shared['id']}").json()["mine"]


def test_a_new_monarch_account_can_come_in_private(client):
    alex = users.find("alex")
    db.ex("INSERT INTO mny_monarch_new (external_id, data) VALUES (%s, %s)", ("m-9", '{"id": "m-9", "displayName": "Brokerage"}'))
    monarch.decide("m-9", "new", by=alex["id"], private=True)
    owner = db.one("SELECT owner_id FROM mny_monarch_new WHERE external_id = 'm-9'")["owner_id"]
    assert owner == alex["id"]
    aid, new = monarch._put_account({"id": "m-9", "displayName": "Brokerage", "type": {"name": "brokerage"}}, dt.date.today(), owner)
    assert new and model.account_row(aid)["owner_id"] == alex["id"]
    # a sync never changes who sees an account already here
    db.ex("UPDATE mny_accounts SET owner_id = NULL WHERE id = %s", (aid,))
    monarch._put_account({"id": "m-9", "displayName": "Brokerage", "type": {"name": "brokerage"}}, dt.date.today(), alex["id"])
    assert model.account_row(aid)["owner_id"] is None
