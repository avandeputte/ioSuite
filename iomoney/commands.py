"""ioMoney's own commands from a shell, beside the migrate and check every app has (iosuite_shared.appcli):

    iosuite iomoney sync [--full]      copy Monarch Money in now (--full: the past two years of transactions again)
    iosuite iomoney quotes             ask Yahoo Finance for every quote now
"""


def add(sub) -> None:
    p = sub.add_parser("sync", help="copy Monarch Money in now")
    p.add_argument("--full", action="store_true", help="the past two years of transactions again")
    p.set_defaults(run=_sync)
    sub.add_parser("quotes", help="ask Yahoo Finance for every quote now").set_defaults(run=_quotes)


def _sync(a) -> int:
    from iomoney import monarch
    monarch.declare()
    r = monarch.sync(full=a.full)
    print(("ok: " if r["ok"] else "failed: ") + r["message"])
    return 0 if r["ok"] else 1


def _quotes(_a) -> None:
    from iomoney import holdings, quotes
    r = quotes.refresh(force=True)
    holdings.revalue_manual_investments()
    print(f"ok: {r['asked']} asked, {r['failed']} failed")
