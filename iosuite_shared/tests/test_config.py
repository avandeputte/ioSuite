"""The machine's file, the on/off values, a copy's three ports and what every app gets from standard(): no database needed."""
import pytest

from iosuite_shared import config

MACHINE = ("IOSUITE_DB_HOST", "IOSUITE_DB_PORT", "IOSUITE_DB_NAME", "IOSUITE_DB_USER", "APPS", "HOST", "PORT", "SYNC_PORT", "MCP_PORT",
           "INTERNAL_URL", "DATA_DIR", "LOG_FILE", "TLS_CERT_FILE", "TLS_KEY_FILE")


@pytest.fixture(autouse=True)
def fresh_db():  # overrides conftest's: nothing here touches a database
    yield


@pytest.fixture
def machine(monkeypatch, tmp_path):
    """The machine's settings read from a file of the test's own; put back as they were afterwards."""
    for k in MACHINE:
        monkeypatch.delenv(k, raising=False)

    def read(text: str):
        (tmp_path / "config.env").write_text(text)
        for k in MACHINE:
            monkeypatch.delenv(k, raising=False)
        config.load_file(tmp_path)
        return config
    yield read
    monkeypatch.undo()
    config.load_file()


def test_load_file_fills_only_what_is_unset(tmp_path, monkeypatch):
    (tmp_path / "config.env").write_text('# a comment\nA_ONE=1\nA_TWO = "two words"\nA_SET=from-file\n\nnot a line\n')
    monkeypatch.delenv("A_ONE", raising=False)
    monkeypatch.delenv("A_TWO", raising=False)
    monkeypatch.setenv("A_SET", "from-env")
    try:
        assert config.load_file(tmp_path) == tmp_path / "config.env"
        import os
        assert os.environ["A_ONE"] == "1" and os.environ["A_TWO"] == "two words" and os.environ["A_SET"] == "from-env"
    finally:
        monkeypatch.delenv("A_ONE"); monkeypatch.delenv("A_TWO")
        monkeypatch.undo()
        config.load_file()


def test_load_file_without_a_file(tmp_path):
    try:
        assert not config.load_file(tmp_path).exists()
    finally:
        config.load_file()


def test_the_machines_file(machine):
    c = machine("IOSUITE_DB_HOST=db.example.lan\nIOSUITE_DB_PORT=3307\nAPPS=iostart, iocalendar iostart\nHOST=127.0.0.1\n"
                "INTERNAL_URL=http://192.168.1.151/\n")
    assert (c.DB_HOST, c.DB_PORT, c.DB_NAME, c.DB_USER) == ("db.example.lan", 3307, "iosuite", "iosuite")
    assert c.APPS == ["iostart", "iocalendar"] and c.HOST == "127.0.0.1" and c.INTERNAL_URL == "http://192.168.1.151"


def test_a_copy_has_three_ports_and_any_can_be_left_closed(machine):
    c = machine("")
    assert (c.PORT, c.SYNC_PORT, c.MCP_PORT) == (80, 8443, 8444)
    c = machine("PORT=8080\nSYNC_PORT=off\nMCP_PORT=0\n")
    assert (c.PORT, c.SYNC_PORT, c.MCP_PORT) == (8080, 0, 0)
    from iosuite_shared import doors
    assert doors.ports() == {8080: "web"}
    with pytest.raises(SystemExit):
        machine("SYNC_PORT=dav\n")
    with pytest.raises(SystemExit):
        machine("MCP_PORT=70000\n")


def test_the_log_is_in_the_data_folder_unless_named_or_off(machine, tmp_path):
    c = machine(f"DATA_DIR={tmp_path}/d\n")
    assert c.LOG_FILE == (tmp_path / "d" / "iosuite.log").resolve()
    assert machine(f"LOG_FILE={tmp_path}/x.log\n").LOG_FILE == (tmp_path / "x.log").resolve()
    assert machine("LOG_FILE=off\n").LOG_FILE is None


@pytest.mark.parametrize("v,want", [("1", True), ("on", True), ("Yes", True), ("TRUE", True), ("0", False), ("off", False),
                                    ("no", False), ("", None), ("maybe", None), (None, None)])
def test_as_flag(v, want):
    assert config.as_flag(v, True) is (True if want is None else want)
    assert config.as_flag(v, False) is (False if want is None else want)


def test_an_apps_setting_else_the_suites_else_the_default():
    s = config.Settings("iocalendar", {"TZ": " Europe/Brussels ", "N": "7", "BAD": "x", "ON": "yes", "EMPTY": "  "})
    assert s.get("TZ") == "Europe/Brussels" and s.get("MISSING", "d") == "d" and s.get("EMPTY", "d") == "d"
    assert s.int("N", 1) == 7 and s.int("BAD", 3) == 3 and s.int("MISSING", 5) == 5
    assert s.flag("ON") is True and s.flag("MISSING", True) is True and s.raw("MISSING") is None
    s.mine, s.suite = {"PUBLIC_URL": "https://calendar.example.com"}, {"PUBLIC_URL": "https://home.example.com", "TZ": "UTC"}
    s.values = {**s.suite, **s.mine}
    assert s.own("PUBLIC_URL") == "https://calendar.example.com" and s.of_suite("PUBLIC_URL") == "https://home.example.com"
    assert s.own("TZ") == "" and s.get("TZ") == "UTC"


def stored(mine: dict, suite: dict) -> config.Settings:
    s = config.Settings("iocalendar", {})
    s.mine, s.suite, s.values = mine, suite, {**suite, **mine}
    return s


def test_standard_gives_an_app_its_folder_and_both_addresses(machine, tmp_path):
    machine(f"DATA_DIR={tmp_path}\nPORT=8080\n")
    c = config.standard("iocalendar", tmp_path / "pkg", stored({}, {}))
    assert c["FOLDER"] == "/calendar" and c["PUBLIC_URL"] == "" and c["PUBLIC_URLS"] == [] and c["BASE_URL"] == "http://localhost:8080/calendar"
    assert c["DATA_DIR"] == (tmp_path / "iocalendar").resolve() and c["DATA_DIR"].is_dir() and c["PORT"] == 8080
    assert c["SYNC_URL"] == "" and c["MCP_URLS"] == []
    # the suite's address: the app in its folder there, at every door
    c = config.standard("iocalendar", tmp_path / "pkg", stored({}, {"PUBLIC_URL": "https://home.example.com/", "SYNC_URL": "https://sync.example.com",
                                                                     "MCP_URL": "https://mcp.example.com"}))
    assert c["PUBLIC_URL"] == "https://home.example.com/calendar" == c["BASE_URL"] and c["OWN_URL"] == ""
    assert c["SYNC_URL"] == "https://sync.example.com/calendar" and c["MCP_URL"] == "https://mcp.example.com/calendar"
    # a name of its own as well: both, its own first
    c = config.standard("iocalendar", tmp_path / "pkg", stored({"PUBLIC_URL": "https://calendar.example.com", "SYNC_URL": "https://caldav.example.com/",
                                                                "DATA_DIR": str(tmp_path / "elsewhere")},
                                                               {"PUBLIC_URL": "https://home.example.com", "SYNC_URL": "https://sync.example.com"}))
    assert c["PUBLIC_URLS"] == ["https://calendar.example.com", "https://home.example.com/calendar"] and c["OWN_URL"] == "https://calendar.example.com"
    assert c["SYNC_URLS"] == ["https://caldav.example.com", "https://sync.example.com/calendar"] and c["SYNC_URL_OWN"] == "https://caldav.example.com"
    assert c["DATA_DIR"] == (tmp_path / "elsewhere").resolve()
    # the start page is at the root of the suite's address
    c = config.standard("iostart", tmp_path / "pkg", stored({}, {"PUBLIC_URL": "https://home.example.com"}))
    assert c["FOLDER"] == "" and c["PUBLIC_URL"] == "https://home.example.com"
    assert config.OF_APP["iostart"] is c


def test_every_app_shares_the_one_database_login(machine):
    machine("IOSUITE_DB_HOST=db.example.lan\nIOSUITE_DB_USER=suite\n")
    d = config.own_db("iocalendar", stored({}, {}))
    assert (d["host"], d["user"], d["database"]) == ("db.example.lan", "suite", "iocalendar")
    assert config.own_db("iocalendar", stored({"DB_NAME": "cal"}, {}))["database"] == "cal"


def test_what_a_person_may_set():
    whole = {d["name"] for d in config.declared("")}
    assert {"PUBLIC_URL", "SYNC_URL", "MCP_URL", "COOKIE_DOMAIN", "TZ"} <= whole
    mine = {d["name"] for d in config.declared("iocalendar")}
    assert {"PUBLIC_URL", "SYNC_URL", "MCP_URL", "DATA_DIR", "DB_NAME"} <= mine and "COOKIE_DOMAIN" not in mine
    assert config.known("iocalendar", "TZ")["name"] == "TZ" and config.known("iocalendar", "NO_SUCH") is None
    for app in ("", "iostart", "iopix"):
        for d in config.declared(app):
            assert d["name"] and d["label"] and d.get("type", "text") in ("text", "number", "switch", "choice"), (app, d)


def test_every_app_has_a_folder_but_the_start_page():
    from iosuite_shared import catalog, suite
    assert set(suite.FOLDERS) | {suite.DOOR} == set(catalog.APPS) and len(set(suite.FOLDERS.values())) == len(suite.FOLDERS)
