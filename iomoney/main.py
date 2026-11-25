"""ioMoney: the application (what is its own: its tables and jobs, its body limits, its routes; the rest is every
app's: iosuite_shared.application).

Who may call a route is declared on the route (iomoney/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application, chores

from iomoney import api, config, history, holdings, model, monarch, quotes, suite_app


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


app = application.create(
    suite_app,
    description="The household's finances: accounts and transactions from Monarch Money, a portfolio with its "
                "quotes, the house and the cars, the net worth. Also served to AI assistants over MCP (/mcp).",
    prepare=(*suite_app.prepare, monarch.declare),  # the Monarch sign-in is kept with the suite's keys and tokens
    jobs=_jobs,
    not_found=(model.NotFound,), forbidden=(model.Forbidden,),
    routers=(api.router,))
