"""ioMoney's part of the estate planning PDF: the person's accounts (private ones too, when they make it themselves)
and the household's, open ones, with the last digits of their number; the house and the cars with the loan against
them. Made by a suite admin for someone else, their private accounts stay out (test_account_people)."""
from iosuite_shared import users

from conftest import sign_in


def add(client, **f):
    r = client.post("/api/accounts", json={"name": "Checking", "kind": "cash", "balance": "1,000.50", **f})
    assert r.status_code == 201, r.text
    return r.json()


def test_their_accounts_and_the_households(client, as_user):
    add(client, name="Joint checking", institution="Chase", mask="1234")
    loan = add(client, name="Mortgage", kind="loan", institution="Wells", balance=200000)
    add(client, name="House", kind="property", balance=500000, loanId=loan["id"], details={"address": "12 Oak St"})
    old = add(client, name="Old savings")
    assert client.patch(f"/api/accounts/{old['id']}", json={"closed": True}).status_code == 200
    as_user("sam", "member")
    add(client, name="Sam's savings", institution="Ally", mask="9876", balance=50)
    sam = users.find("sam")["id"]
    sign_in(client, "alex")
    add(client, name="Alex's own", household=False)
    sign_in(client, "sam")
    got = client.get(f"/api/auth/estate/{sam}").json()["sections"][0]
    assert got["title"] == "Accounts and assets"
    assert [r[:5] + r[6:] for r in got["table"]["rows"][:2]] == [  # their own first
        ["Sam's savings", "Ally", "Cash", "…9876", "$50.00", "Theirs"],
        ["Joint checking", "Chase", "Cash", "…1234", "$1,000.50", "Household"]]
    assert ["Mortgage", "Wells", "Loans", "", "$200,000.00 owed"] == got["table"]["rows"][2][:5]
    names = [r[0] for r in got["table"]["rows"]]
    assert "Old savings" not in names and "Alex's own" not in names and "House" not in names
    house = got["items"][0]
    assert house["title"] == "House" and ["Address", "12 Oak St"] in house["rows"]
    assert ["Loan against it", "Mortgage (Wells): $200,000.00 owed"] in house["rows"]
