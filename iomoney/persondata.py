"""What a person keeps in ioMoney, counted or removed when their account is deleted (iosuite_shared.persondata):
their private accounts that nobody else sees, with everything in them (balances, transactions with their receipts,
holdings), and their saved searches. A private account they showed to others is kept, passed on to the first of
those people, who owns it from then on; the accounts others showed them are no longer shown to anyone of that id. The
household's accounts stay, whoever added them or changed their transactions: they are everyone's."""
from iosuite_shared import related

from iomoney import db, receipts, searches


def of(user_id: int, remove: bool) -> list:
    owned = [r["id"] for r in db.q("SELECT id FROM mny_accounts WHERE owner_id = %s", (user_id,))]
    heirs = {}  # a private account shown to others: the first of them, who will own it
    if owned:
        for r in db.q(f"SELECT account_id, user_id FROM mny_account_people WHERE account_id IN ({db.marks(len(owned))}) "
                      "ORDER BY added_at, user_id", owned):
            heirs.setdefault(r["account_id"], r["user_id"])
    accts = [a for a in owned if a not in heirs]
    shown = db.one("SELECT count(*) AS n FROM mny_account_people WHERE user_id = %s", (user_id,))["n"]
    if remove:
        with db.tx():
            for aid, heir in heirs.items():
                db.ex("UPDATE mny_accounts SET owner_id = %s WHERE id = %s", (heir, aid))
                db.ex("DELETE FROM mny_account_people WHERE account_id = %s AND user_id = %s", (aid, heir))
            db.ex("DELETE FROM mny_account_people WHERE user_id = %s", (user_id,))
    marks = db.marks(len(accts))
    tx = db.one(f"SELECT count(*) AS n FROM mny_transactions WHERE account_id IN ({marks})", accts)["n"] if accts else 0
    hold = db.one(f"SELECT count(*) AS n FROM mny_holdings WHERE account_id IN ({marks})", accts)["n"] if accts else 0
    added = db.one("SELECT count(*) AS n FROM mny_accounts WHERE owner_id IS NULL AND created_by = %s", (user_id,))["n"]
    if remove and accts:
        tids = [r["id"] for r in db.q(f"SELECT id FROM mny_transactions WHERE account_id IN ({marks})", accts)]
        with db.tx():
            db.ex(f"UPDATE mny_accounts SET loan_id = NULL WHERE loan_id IN ({marks})", accts)
            db.ex(f"DELETE FROM mny_accounts WHERE id IN ({marks})", accts)  # balances, transactions, holdings go with them
        related.forget_many("asset", accts)  # their links to other items of the suite go too
        receipts.forget(tids)                # and those of their transactions (the receipts go with the transactions)
    saved = searches.forget(user_id) if remove else db.one("SELECT count(*) AS n FROM mny_searches WHERE user_id = %s", (user_id,))["n"]
    return [{"what": "private accounts", "one": "private account", "count": len(accts)},
            {"what": "transactions in them", "one": "transaction in them", "count": tx},
            {"what": "holdings in them", "one": "holding in them", "count": hold},
            {"what": "saved searches", "one": "saved search", "count": saved},
            {"what": "private accounts they shared, passed on to someone who sees them", "one": "private account they shared, passed on to someone who sees it", "count": len(heirs), "kept": True},
            {"what": "private accounts others showed them", "one": "private account someone showed them", "count": shown, "kept": True},
            {"what": "household accounts they added", "one": "household account they added", "count": added, "kept": True}]
