"""ioMoney: the application (what is its own: its tables and jobs, its body limits, its routes; the rest is every
app's: iosuite_shared.application).

Who may call a route is declared on the route (iomoney/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, chores, mcp as shared_mcp

from iomoney import __version__, api, config, db, history, holdings, mcp, model, monarch, quotes, suiteitems, users
from iomoney.auth import auth, updater

# Settings › Apps › MCP: this app's switch in the Shared ioSuite database, the suite's one unless it says otherwise
mcp_switch = shared_mcp.Switch(config.APP,
                               "Lets an AI assistant read the accounts, the transactions, the portfolio and the net worth, and keep them, as you.")
mcp_enabled = mcp_switch.enabled


def background() -> None:
    """Every five minutes: Monarch Money when its sync is due, the quotes that are old, the manual investment accounts
    revalued, today's estimates of the house and the cars, and the kept changes that are too old dropped."""
    if monarch.due():
        monarch.sync()
    quotes.refresh()
    holdings.revalue_manual_investments()
    holdings.write_estimates()
    history.prune()


def _jobs() -> list:
    return [chores.start(background, every_s=300, first_s=30, name="Monarch sync and quotes", app=config.APP)] if config.SYNC else []


def _limit_for(path: str, ctype: str) -> int:
    if path.endswith(("/import", "/statement/read")):
        return config.MAX_IMPORT_BYTES
    return config.MAX_RECEIPT_BYTES if path.endswith("/receipts") else config.MAX_JSON_BYTES


def _status_extra(request) -> dict:
    """ioMoney's own fields of GET /api/status, beside the suite's."""
    u = request.state.user
    return {"mcp": mcp_enabled() if u else None}


app = application.create(
    auth, updater, __version__, config,
    description="The household's finances: accounts and transactions from Monarch Money, a portfolio with its "
                "quotes, the house and the cars, the net worth. Also served to AI assistants over MCP (/mcp).",
    prepare=(db.migrate, users.init, monarch.declare),  # the Monarch sign-in is kept with the suite's keys and tokens
    jobs=_jobs,
    mcp=mcp, mcp_enabled=mcp_enabled,
    limit_for=_limit_for, not_found=(model.NotFound,), forbidden=(model.Forbidden,),
    status=_status_extra, suite=suiteitems.PROVIDER, routers=(api.router,))
