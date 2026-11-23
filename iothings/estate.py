"""ioThings's part of a person's estate planning PDF (iosuite_shared.estate): the things that are theirs (the ones
marked for them, not the household's), with where they are, their serial number and what they cost. The whole
inventory, with photos and receipts, is ioThings's own PDF (app/pdf.py)."""
import datetime as dt
from decimal import Decimal

from iothings import model

SIGNS = {"USD": "$", "CAD": "$", "AUD": "$", "NZD": "$", "MXN": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "INR": "₹"}


def _money(v, cur: str) -> str:
    if v is None:
        return ""
    v = Decimal(str(v))
    s = f"{v:,.0f}" if cur == "JPY" else f"{v:,.2f}"
    return f"{SIGNS[cur]}{s}" if cur in SIGNS else f"{s} {cur}"


def data(user_id: int) -> list:
    rows = model.find(person=user_id, limit=5000)
    if not rows:
        return []
    cur = model.currency()
    places = {x["id"]: x["path"] for x in model.locations()}
    rows.sort(key=lambda r: (-(r["purchase_price"] or 0) * (r["quantity"] or 1), r["name"].lower()))
    table = [[r["name"] + (f" ({r['quantity']})" if r["quantity"] != 1 else ""), places.get(r["location_id"]) or "",
              r["serial_number"] or "", r["purchase_date"].strftime("%b %-d, %Y") if isinstance(r["purchase_date"], dt.date) else "",
              _money(r["purchase_price"], cur), "Yes" if r["insured"] else ""] for r in rows]
    worth = sum((Decimal(str(r["purchase_price"])) * (r["quantity"] or 1) for r in rows if r["purchase_price"] is not None), Decimal(0))
    return [{"title": "Things", "order": 40,
             "intro": f"What is theirs in ioThings, most costly first: {len(rows)} thing{'s' if len(rows) != 1 else ''}"
                      f"{f', bought for {_money(worth, cur)} all together' if worth else ''}.",
             "table": {"columns": ["Thing", "Where", "Serial number", "Bought", "Price", "Insured"], "rows": table}}]
