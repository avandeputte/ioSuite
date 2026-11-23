"""What every group of routes uses: who is asking, and a month's first and last day."""
import datetime as dt

from fastapi import Request
from iosuite_shared.errors import Invalid


def _u(request: Request) -> dict:
    return request.state.user


def month_bounds(month: str | None) -> tuple[dt.date, dt.date]:
    today = dt.date.today()
    if month:
        try:
            y, m = (int(x) for x in month.split("-")[:2])
            first = dt.date(y, m, 1)
        except (ValueError, TypeError):
            raise Invalid("month: YYYY-MM")
    else:
        first = today.replace(day=1)
    nxt = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return first, nxt - dt.timedelta(days=1)
