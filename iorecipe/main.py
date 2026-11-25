"""ioRecipe: the application (what is its own: its tables and jobs, its body limits, its routes; the rest is every
app's: iosuite_shared.application).

Who may call a route is declared on the route (iorecipe/access.py); iosuite_shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
from iosuite_shared import application

from iorecipe import ai, api, model, suite_app


app = application.create(
    suite_app,
    description="The family's recipes: ingredients, steps, a photo, and import from a web page. Also served "
                "to AI assistants over MCP (/mcp).",
    start=(ai.start,),  # the AI model on its way, where it is wanted and not there yet
    not_found=(model.NotFound,), forbidden=(model.Forbidden,),
    routers=(api.router,))
