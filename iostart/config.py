"""Settings: ioStart's own are kept in the Shared ioSuite database and read once, as it starts (Settings › Apps ›
All settings changes them; app.json lists them). The settings every app of the suite shares come from
iosuite_shared.config.standard; the machine's file says only where that database is and where the server listens."""
from iosuite_shared import config as shared

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)
env_flag = _own["env_flag"]

# where the apps are: each registers itself in the suite's list in the Shared ioSuite database (see apps.py)

# the weather and Home Assistant are set in Settings (the key and the token with the suite's keys and tokens)
HA_FEED = env_flag("HA_FEED", True)   # HA_FEED=0: no websocket to Home Assistant, the page polls instead
SITE_ICONS = env_flag("SITE_ICONS", True)   # SITE_ICONS=0: the server does not fetch the bookmarked sites' icons
TIMERS_LOOP = env_flag("TIMERS_LOOP", True)   # TIMERS_LOOP=0: no job that sends "timer done" notifications (timers.py; the tests call tick())
NEWS_LOOP = env_flag("NEWS_LOOP", True)   # NEWS_LOOP=0: the server does not fetch the feeds people follow by itself (news.py; the tests call tick())
TRMNL_PUSH = env_flag("TRMNL_PUSH", True)   # TRMNL_PUSH=0: the start page does not push anyone's TRMNL screens (trmnl/push.py)
