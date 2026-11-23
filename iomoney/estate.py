"""ioMoney's part of a person's estate planning PDF (iosuite_shared.estate): the accounts they see (their private
ones, those others showed them, the household's), open ones only; made by someone else (a suite admin), only those of
them the asker sees too: a private account is never shown to anyone its owner did not name. Each account with its
bank, the last digits of its number (ioMoney keeps no more than that), its balance and when that was; then the house,
the cars and other things of value with what is known about them and the loan against them; and the bills whose
provider is kept, with the account number they have there (under the same rule: the household's, and those paid from an
account shown)."""
import json
from decimal import Decimal

from iomoney import db, model, recurring

SIGNS = {"USD": "$", "CAD": "$", "AUD": "$", "NZD": "$", "MXN": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "INR": "₹"}
DETAILS = (("address", "Address"), ("year", "Year"), ("make", "Make"), ("model", "Model"), ("vin", "VIN"),
           ("mileage", "Mileage"), ("boughtOn", "Bought on"), ("boughtFor", "Bought for"), ("notes", "Notes"))


def _money(v, cur: str, owed: bool = False) -> str:
    v = Decimal(str(v or 0))
    s = f"{v:,.0f}" if cur == "JPY" else f"{v:,.2f}"
    s = f"{SIGNS[cur]}{s}" if cur in SIGNS else f"{s} {cur}"
    return f"{s} owed" if owed else s


def _whose(a: dict, user_id: int, long: bool = False) -> str:
    if a["owner_id"] is None:
        return "The household’s" if long else "Household"
    return "Theirs" if a["owner_id"] == user_id else "Shared with them"


def _sees(alias: str, uid: int) -> tuple[str, list]:
    return (f"({alias}.owner_id IS NULL OR {alias}.owner_id = %s OR EXISTS (SELECT 1 FROM mny_account_people ap "
            f"WHERE ap.account_id = {alias}.id AND ap.user_id = %s))"), [uid, uid]


def data(user_id: int, asker: dict | None = None) -> list:
    where, args = _sees("a", user_id)
    if asker is not None and asker.get("id") != user_id:
        w2, a2 = _sees("a", int(asker["id"]))
        where, args = f"{where} AND {w2}", args + a2
    rows = db.q(f"SELECT a.* FROM mny_accounts a WHERE a.closed = 0 AND {where} "
                "ORDER BY a.owner_id IS NULL, a.position, a.name", args)
    out = _accounts(rows, user_id)
    bills = _bills(where, args)
    if bills:
        out.append(bills)
    return out


def _bills(where: str, args: list) -> dict | None:
    """The bills whose provider is kept (the account number with the power company, the water board...): those for
    any account (the household's), and those paid from an account they (and the asker) see."""
    rs = db.q(f"SELECT r.* FROM mny_recurring r LEFT JOIN mny_accounts a ON a.id = r.account_id "
              f"WHERE r.flow = 'out' AND (r.account_id IS NULL OR {where}) ORDER BY r.name", args)
    acct = {a["id"]: a["name"] for a in db.q("SELECT id, name FROM mny_accounts")} if rs else {}
    table = []
    for r in rs:
        p = recurring.provider(r)
        if not p:
            continue
        table.append([r["name"], p.get("accountNumber", ""), p.get("phone", ""),
                      (p.get("website") or "").removeprefix("https://").removeprefix("http://").rstrip("/"),
                      acct.get(r["account_id"], "Any account") if r["account_id"] else "Any account", p.get("note", "")])
    if not table:
        return None
    return {"title": "Bills and providers", "order": 31,
            "intro": "The bills kept in ioMoney with the account number they have with the provider, to call or close them.",
            "table": {"columns": ["Provider", "Account number", "Phone", "Website", "Paid from", "Note"], "rows": table}}


def _accounts(rows: list, user_id: int) -> list:
    if not rows:
        return []
    order = {k: i for i, k in enumerate(model.KINDS)}
    rows.sort(key=lambda a: (order.get(a["kind"], 99), a["owner_id"] is None, (a["name"] or "").lower()))
    by_id = {a["id"]: a for a in rows}
    table = [[a["name"], a["institution"] or "", model.KINDS.get(a["kind"], (a["kind"],))[0],
              f"…{a['mask']}" if a["mask"] else "", _money(a["balance"], a["currency"], not a["is_asset"]),
              a["balance_at"].strftime("%b %-d, %Y") if a["balance_at"] else "",
              _whose(a, user_id)] for a in rows if a["kind"] not in model.THINGS]
    items = []
    for a in rows:
        if a["kind"] not in model.THINGS:
            continue
        try:
            det = json.loads(a["details"]) if a["details"] else {}
        except ValueError:
            det = {}
        det = det if isinstance(det, dict) else {}
        out = [["Kind", model.KINDS.get(a["kind"], (a["kind"],))[0]], ["Value", _money(a["balance"], a["currency"])]]
        out += [[label, str(det[k])] for k, label in DETAILS if det.get(k) not in (None, "")]
        loan = by_id.get(a["loan_id"])  # only a loan listed here too (never one they or the asker do not see)
        if loan:
            held = f" ({loan['institution']})" if loan["institution"] else ""
            out.append(["Loan against it", f"{loan['name']}{held}: {_money(loan['balance'], loan['currency'], True)}"])
        items.append({"title": a["name"], "subtitle": _whose(a, user_id, True), "rows": out})
    return [{"title": "Accounts and assets", "order": 30,
             "intro": "Their accounts in ioMoney and the household’s, as last seen. Numbers show only their last digits: "
                      "the bank statements have the rest.",
             "table": {"columns": ["Account", "Bank", "Kind", "Number", "Balance", "As of", "Whose"], "rows": table} if table else None,
             "items": items}]
