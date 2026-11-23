"""Around every page: the summary (what this person sees and may do), and the net worth over time."""

from fastapi import APIRouter, Request

from iomoney import access, model, monarch, recurring, review
from iomoney.routes.common import _u

router = APIRouter()


@router.get("/api/summary", dependencies=[access.signed_in])
def summary(request: Request):
    """What the pages need around them: the net worth now, how many accounts, transactions and holdings this person
    sees, the household's currency, the kinds of accounts, whether Monarch Money is set up (with the accounts whose link to
    the bank it reports as broken or more than two days behind: monarch.stale), how many transactions need a look
    (review), and what this person may do."""
    u = _u(request)
    return {"netWorth": model.net_worth(u), "counts": model.counts(u), "currency": model.home_currency(),
            "kinds": [{"kind": k, "label": v[0], "isAsset": v[1], "group": model.GROUP_OF.get(k, "asset"),
                       "track": model.TRACK_DEFAULT.get(k, "value")} for k, v in model.KINDS.items()],
            "groups": [{"group": g, "label": name, "kinds": list(kinds)} for g, name, kinds in model.GROUPS],
            "holdingKinds": list(model.HOLDING_KINDS),
            "monarch": {"configured": monarch.configured(), "lastGood": monarch.status()["lastGood"], "running": monarch.running(),
                        "newAccounts": monarch.held_count() if model.is_admin(u) else 0,
                        "stale": model.stale_accounts(u)} if model.role_rank(u) else None,
            "recurringFlags": len(recurring.flags(u)), "review": review.count(u),
            "may": {"read": model.role_rank(u) >= 1, "own": model.may_add(u, False), "household": model.may_add(u, True),
                    "admin": model.is_admin(u)}}


@router.get("/api/networth", dependencies=[access.signed_in])
def networth(request: Request, days: int = 365, kind: str = None):
    """The net worth now (by kind) and day by day over the past days (kind: one kind's value only)."""
    u = _u(request)
    return {**model.net_worth(u), "history": model.history(u, days, kind=kind)}
