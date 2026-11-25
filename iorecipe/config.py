"""Settings: kept in the Shared ioSuite database, the suite's one home for them (Settings › Apps › All settings and
the app's own Settings page change them; app.json lists the app's own). The ones that say where the app answers and
where it keeps what it keeps are read once, as it starts (`env`); every other is read as it is now (`live`), so a
change takes hold without a restart. Everything stored
lives in MariaDB, the photos too. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from iosuite_shared import config as shared

# APP, env, env_flag, env_int, what every app has (APP_DIR, DATA_DIR, PUBLIC_URL...), DB_* and the MAX_<NAME>_BYTES of
# app.json's limits: iosuite_shared.config.of_app says what each is
_own = shared.of_app(__package__)
globals().update(_own)
live, live_flag, live_int = _own["live"], _own["live_flag"], _own["live_int"]
env, env_flag, env_int = _own["env"], _own["env_flag"], _own["env_int"]

# reading a photo of a recipe (iorecipe/ocr.py): the languages Tesseract tries, as its codes with + between (eng+nld+fra);
# empty: every language installed

# reading a web page that has no recipe data with AI (iorecipe/ai.py): a small model that runs on this server, inside the
# app. AI=0 turns it off; AI_MODEL is another model than the one the app fetches (a GGUF file here, or the address of
# one); AI_TIMEOUT is how many seconds one page may take
AI = env_flag("AI", True)
AI_MODEL = env("AI_MODEL")
AI_TIMEOUT = env_int("AI_TIMEOUT", 300)

# MCP_USER (iosuite_shared.config.standard): the account `iosuite mcp iorecipe` (stdio) acts as
