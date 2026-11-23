"""The REST API (JSON) the web app uses. OpenAPI docs at /api/docs. Who may call a route is declared on it
(iomoney/access.py); what an account may see and change is the account's business (iomoney/model.py): nobody without a role
in ioMoney gets anything but empty lists.

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`.

The routes are kept by subject in iomoney/routes/ (overview, accounts, transactions, rules, holdings, recurring, tidy,
settings); this module puts them together, in the order they are looked up.
"""
from fastapi import APIRouter

from iomoney.routes import accounts, holdings, overview, recurring, rules, settings, tidy, transactions

router = APIRouter()
for _part in (overview, accounts, transactions, rules, holdings, recurring, tidy, settings):
    router.include_router(_part.router)
