"""Holdings and the portfolio: what an investment account holds (a fund, a share, cash), what each is worth with the
day's quote, and the portfolio they make together. Who sees an account sees its holdings; who may change the account
changes them (iomoney/model.py has the accounts and those rules)."""
import datetime as dt
from decimal import Decimal

from iosuite_shared.errors import Invalid

from iomoney import db, model


def holding_row(hid) -> dict | None:
    try:
        hid = int(hid)
    except (TypeError, ValueError):
        return None
    return db.one("SELECT h.*, a.owner_id, a.name AS account_name, a.source AS account_source, a.currency AS account_currency "
                  "FROM mny_holdings h JOIN mny_accounts a ON a.id = h.account_id WHERE h.id = %s", (hid,))


def holding(u: dict, hid) -> dict:
    h = holding_row(hid)
    if not h or not model.can_read(u, h):
        raise model.NotFound("No such holding")
    return h


def holdings(u: dict, account_id: int = None) -> list[dict]:
    where, args = model._visible(u)
    if account_id:
        where += " AND h.account_id = %s"
        args.append(int(account_id))
    return db.q(f"SELECT h.*, a.owner_id, a.name AS account_name, a.source AS account_source, a.currency AS account_currency, "
                f"q.price AS q_price, q.previous_close AS q_prev, q.currency AS q_currency, q.name AS q_name, q.market_time AS q_time, "
                f"q.error AS q_error FROM mny_holdings h JOIN mny_accounts a ON a.id = h.account_id "
                f"LEFT JOIN mny_quotes q ON q.symbol = h.symbol WHERE {where} AND a.hidden = 0 AND a.closed = 0 "
                f"ORDER BY h.symbol, h.name", args)


def priced(h: dict) -> dict:
    """A holding with its price (the quote's, else the one kept with it), value, the day's change and the gain, in
    the currency it is quoted in and in the household's."""
    quoted = h.get("q_price") is not None
    price = Decimal(h["q_price"]) if quoted else (Decimal(h["price"]) if h.get("price") is not None else None)
    cur = (h.get("q_currency") if quoted else None) or h.get("account_currency") or model.home_currency()
    shares = Decimal(h["shares"])
    if h["kind"] == "cash" and price is None:
        price = Decimal(1)
    value = shares * price if price is not None else None
    fx = model.rate(cur)
    change = None
    if quoted and h.get("q_prev"):
        change = (Decimal(h["q_price"]) - Decimal(h["q_prev"])) * shares
    basis = Decimal(h["cost_basis"]) if h.get("cost_basis") is not None else None
    return {"id": h["id"], "accountId": h["account_id"], "account": h["account_name"], "symbol": h["symbol"],
            "name": h["name"] or h.get("q_name"), "kind": h["kind"], "shares": float(shares),
            "price": None if price is None else float(price), "currency": cur, "quoted": quoted,
            "quoteError": h.get("q_error"), "value": model.n2(value), "homeValue": model.n2(value * fx) if value is not None else None,
            "dayChange": model.n2(change * fx) if change is not None else None,
            "dayChangePct": float(((Decimal(h["q_price"]) / Decimal(h["q_prev"])) - 1) * 100) if quoted and h.get("q_prev") else None,
            "costBasis": model.n2(basis), "gain": model.n2((value - basis) * fx) if value is not None and basis is not None else None,
            "source": h["source"], "writable": None}


def portfolio(u: dict, account_id: int = None) -> dict:
    """Every holding the person sees, priced, with the totals and the same symbol across accounts added up."""
    items = []
    for h in holdings(u, account_id):
        p = priced(h)
        p["writable"] = model.can_write(u, h) and h["source"] == "manual"
        items.append(p)
    total = sum((Decimal(str(p["homeValue"])) for p in items if p["homeValue"] is not None), Decimal(0))
    change = sum((Decimal(str(p["dayChange"])) for p in items if p["dayChange"] is not None), Decimal(0))
    basis_items = [p for p in items if p["gain"] is not None]
    gain = sum((Decimal(str(p["gain"])) for p in basis_items), Decimal(0))
    by_symbol: dict = {}
    for p in items:
        k = p["symbol"] or f"#{p['id']}"
        s = by_symbol.setdefault(k, {"symbol": p["symbol"], "name": p["name"], "kind": p["kind"], "shares": 0.0, "price": p["price"],
                                     "currency": p["currency"], "homeValue": 0.0, "dayChange": 0.0, "dayChangePct": p["dayChangePct"],
                                     "accounts": []})
        s["shares"] += p["shares"]
        s["homeValue"] = round(s["homeValue"] + (p["homeValue"] or 0), 2)
        s["dayChange"] = round(s["dayChange"] + (p["dayChange"] or 0), 2)
        if p["account"] not in s["accounts"]:
            s["accounts"].append(p["account"])
    alloc: dict = {}
    for p in items:
        alloc[p["kind"]] = alloc.get(p["kind"], 0.0) + (p["homeValue"] or 0)
    prev = total - change
    return {"currency": model.home_currency(), "value": model.n2(total), "dayChange": model.n2(change),
            "dayChangePct": float(change / prev * 100) if prev else None, "gain": model.n2(gain) if basis_items else None,
            "items": items, "bySymbol": sorted(by_symbol.values(), key=lambda s: -s["homeValue"]),
            "allocation": [{"kind": k, "value": round(v, 2)} for k, v in sorted(alloc.items(), key=lambda x: -x[1])]}


def _holding_fields(b: dict, partial: bool) -> dict:
    out = {}
    if "symbol" in b or not partial:
        out["symbol"] = model.symbol(b.get("symbol"))
    if "name" in b:
        out["name"] = model.text(b.get("name"), 255, "The name")
    if "kind" in b or not partial:
        k = str(b.get("kind") or "stock")
        if k not in model.HOLDING_KINDS:
            raise Invalid("The kind: " + ", ".join(model.HOLDING_KINDS))
        out["kind"] = k
    if "shares" in b or not partial:
        out["shares"] = model.number(b.get("shares"), "The number of shares", 8, required=True)
    if "costBasis" in b:
        out["cost_basis"] = model.money(b.get("costBasis"), "The cost basis", required=False)
    if "price" in b:
        out["price"] = model.number(b.get("price"), "The price", 6)
        out["price_at"] = dt.datetime.now() if out["price"] is not None else None
    if not partial and not out.get("symbol") and not out.get("name"):
        raise Invalid("Give the symbol (AAPL, VWCE.DE, BTC-USD) or, for something without one, a name and a price")
    return out


def create_holding(u: dict, a: dict, b: dict) -> dict:
    model._need(model.can_write(u, a))
    if a["kind"] != "investment":
        raise Invalid("Holdings go in an investment account")
    if a["source"] == "monarch":
        raise model.Forbidden("The holdings of a Monarch Money account come from Monarch")
    f = _holding_fields(b, False)
    cols = ", ".join(f)
    hid = db.ex(f"INSERT INTO mny_holdings (account_id, source, {cols}) VALUES (%s, 'manual', {db.marks(len(f))})",
                (a["id"], *f.values()))
    return holding_row(hid)


def update_holding(u: dict, h: dict, b: dict) -> dict:
    model._need(model.can_write(u, h))
    if h["source"] != "manual":
        raise model.Forbidden("This holding comes from Monarch Money")
    f = _holding_fields(b, True)
    if f:
        db.ex(f"UPDATE mny_holdings SET {', '.join(k + ' = %s' for k in f)} WHERE id = %s", (*f.values(), h["id"]))
    return holding_row(h["id"])


def delete_holding(u: dict, h: dict) -> None:
    model._need(model.can_write(u, h))
    if h["source"] != "manual":
        raise model.Forbidden("This holding comes from Monarch Money")
    db.ex("DELETE FROM mny_holdings WHERE id = %s", (h["id"],))


def revalue_manual_investments(account_id: int = None) -> int:
    """A manual investment account is worth what it holds: its balance follows the quotes (today's row). One that
    holds nothing keeps the balance typed in, unless it is the account named (its last holding just went)."""
    n = 0
    for a in db.q("SELECT * FROM mny_accounts WHERE kind = 'investment' AND source = 'manual'"):
        rows = db.q("SELECT h.*, a.currency AS account_currency, a.name AS account_name, q.price AS q_price, "
                    "q.previous_close AS q_prev, q.currency AS q_currency, q.name AS q_name, q.error AS q_error "
                    "FROM mny_holdings h JOIN mny_accounts a ON a.id = h.account_id LEFT JOIN mny_quotes q ON q.symbol = h.symbol "
                    "WHERE h.account_id = %s", (a["id"],))
        if not rows and a["id"] != account_id:
            continue
        total = Decimal(0)
        for h in rows:
            p = priced(h)
            if p["value"] is not None:
                total += Decimal(str(p["value"])) * model.rate(p["currency"]) / model.rate(a["currency"])
        model.set_balance(a["id"], dt.date.today(), total.quantize(model.CENT), "sync")
        n += 1
    return n


def write_estimates() -> int:
    """Today's estimated value of each house and car with a yearly change, as a point of its history."""
    n = 0
    for a in db.q("SELECT * FROM mny_accounts WHERE kind IN ('property', 'vehicle', 'other_asset') AND source = 'manual'"):
        a = model._acct(a)
        today = dt.date.today()
        row = db.one("SELECT source FROM mny_balances WHERE account_id = %s AND day = %s", (a["id"], today))
        if row and row["source"] != "estimate":
            continue
        e = model.estimate(a, today)
        if e is not None:
            model.set_balance(a["id"], today, e, "estimate")
            n += 1
    return n
