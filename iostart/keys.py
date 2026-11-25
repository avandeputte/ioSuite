"""The start page's keys and tokens, kept with every other app's in the Shared ioSuite database
(iosuite_shared.credentials), so Settings › Keys lists them all. Settings › Home Assistant,
Settings › Weather and Inbox › Mailbox still set them."""
import logging

from iosuite_shared import credentials

from iostart import config

log = logging.getLogger("iostart.keys")
KEYS = [
    {"name": "ha_token", "label": "Home Assistant token",
     "hint": "a long-lived access token (Home Assistant: your profile › Security)"},
    {"name": "accuweather_key", "label": "AccuWeather API key",
     "hint": "from developer.accuweather.com, for the weather card"},
    {"name": "mail_password", "label": "Suite inbox mailbox password",
     "hint": "the password of the mailbox the suite reads (Inbox › Mailbox); an app password for Gmail, Fastmail or iCloud"},
]


def declare() -> None:
    """At start: say which keys the start page keeps."""
    try:
        credentials.declare(config.APP, KEYS)
    except Exception as e:  # noqa: BLE001 - the shared database is away: tried again next start
        log.warning("keys and tokens: %s", e)
