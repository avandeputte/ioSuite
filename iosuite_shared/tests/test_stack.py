"""`iosuite stack`: what a container does before it serves (iosuite_shared.stack)."""
import json

import pytest

from iosuite_shared import cli, config, db, proxyauth, stack, users

QUIET = lambda *_: None  # noqa: E731


@pytest.fixture
def login(monkeypatch):
    monkeypatch.setattr(config, "DB_PASSWORD", "sh4red")
    monkeypatch.setattr("iosuite_shared.host.names", lambda given=None: ["iostart", "iocalendar"])
    monkeypatch.setenv("DB_ADMIN_PASSWORD", "r00t")


def test_the_databases_are_those_of_this_container_s_apps(login):
    seen = {}

    def run(admin, password, names, t, client=None, log=print):
        seen.update(admin=admin, password=password, names=list(names), user=t["user"], client=client)
        return names
    stack.provision_here("root", None, log=QUIET, run=run)
    assert seen == {"admin": "root", "password": "r00t", "names": ["iostart", "iocalendar"], "user": config.DB_USER, "client": "%"}
    db.set_setting("DB_NAME", "kalender", "iocalendar")  # a name stored for it under Settings
    stack.provision_here("root", "10.0.0.%", log=QUIET, run=run)
    assert seen["names"] == ["iostart", "kalender"] and seen["client"] == "10.0.0.%"


def test_a_database_that_is_still_starting_is_waited_for(login):
    calls, logged = [], []

    def run(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise SystemExit("error: could not connect to db:3306 as root: (2003, \"Can't connect\")")
        return ["iostart"]
    assert stack.provision_here("root", "%", run=run, log=logged.append, sleep=lambda s: None) == ["iostart"]
    assert len(calls) == 3 and len(logged) == 2


def test_what_is_wrong_is_said_at_once(login, monkeypatch):
    def denied(*a, **k):
        raise SystemExit("error: db:3306: CREATE DATABASE: (1044, 'Access denied')")
    with pytest.raises(SystemExit, match="Access denied"):  # not a server that is still starting: no waiting
        stack.provision_here("root", "%", run=denied, log=QUIET, sleep=lambda s: pytest.fail("waited"))

    def refused(*a, **k):
        raise SystemExit("error: could not connect to db:3306 as root: (1045, \"Access denied for user 'root'@'10.186.30.10'\")")
    with pytest.raises(SystemExit, match="docker compose down -v"):  # an old volume's root password: no minute of waiting
        stack.provision_here("root", "%", run=refused, log=QUIET, sleep=lambda s: pytest.fail("waited"))
    monkeypatch.setattr(config, "DB_PASSWORD", "")
    with pytest.raises(SystemExit, match="IOSUITE_DB_PASSWORD"):
        stack.provision_here("root", "%", run=lambda *a, **k: 1, log=QUIET)


def test_the_settings_of_a_stack_file():
    assert stack.parse_set(["suite.PUBLIC_URL=https://home.example.com", " ioPix.PHOTOS_ROOT = /photos ", "suite.TZ="]) == {
        "suite.PUBLIC_URL": "https://home.example.com", "iopix.PHOTOS_ROOT": "/photos", "suite.TZ": ""}
    assert stack.parse_set(["iohealth.MAP_TILE_URL=https://tiles.example.com/{z}/{x}/{y}.png?key=a=b"])["iohealth.MAP_TILE_URL"].endswith("key=a=b")
    for bad in ("PUBLIC_URL=https://x", "suite.PUBLIC_URL", ".TZ=UTC", "suite.=UTC"):
        with pytest.raises(SystemExit, match="APP.NAME=VALUE"):
            stack.parse_set([bad])


def test_what_the_stack_says_is_written_once_and_again_only_when_it_changes():
    said = {"suite.PUBLIC_URL": "https://home.example.com", "iopix.PHOTOS_ROOT": "/photos"}
    assert stack.declare(said, "10.186.30.10, 10.186.30.11", log=QUIET) == {"set": said, "proxies": "10.186.30.10,10.186.30.11"}
    assert db.settings_of("")["PUBLIC_URL"] == "https://home.example.com" and db.settings_of("iopix") == {"PHOTOS_ROOT": "/photos"}
    assert proxyauth.Forwarded.allows("10.186.30.10") and not proxyauth.Forwarded.allows("10.186.30.1")
    assert json.loads(db.get_setting(stack.DECLARED, "", ""))["set"] == said
    # a suite admin changes them under Settings; the same stack file started again leaves them alone
    db.set_setting("PUBLIC_URL", "https://family.example.com")
    proxyauth.save_suite({"AUTH_PROXY_TRUSTED": "192.168.1.2"})
    db.settings_cache.clear()
    assert stack.declare(said, "10.186.30.10,10.186.30.11", log=QUIET) == {}
    assert db.settings_of("")["PUBLIC_URL"] == "https://family.example.com" and db.get_setting("auth_proxy_trusted", "", "") == "192.168.1.2"
    # a stack file that says something else is applied; what it no longer says stays as it is
    assert stack.declare({"suite.PUBLIC_URL": "https://new.example.com"}, "", log=QUIET) == {"set": {"suite.PUBLIC_URL": "https://new.example.com"}, "proxies": ""}
    assert db.settings_of("")["PUBLIC_URL"] == "https://new.example.com" and db.get_setting("auth_proxy_trusted", "", "") == ""
    assert db.settings_of("iopix") == {"PHOTOS_ROOT": "/photos"}
    assert stack.declare(None, None, log=QUIET) == {}


def test_a_setting_no_app_has_stops_the_start():
    with pytest.raises(SystemExit, match="--set iopix.NOPE: No such setting: NOPE"):
        stack.declare({"iopix.NOPE": "1"}, None, log=QUIET)
    with pytest.raises(SystemExit, match="whole number"):
        stack.declare({"iopix.THUMB_HEIGHT": "tall"}, None, log=QUIET)
    assert db.get_setting(stack.DECLARED, "", "") == ""


def test_the_command_makes_the_tables_and_the_first_admin(monkeypatch, capsys):
    monkeypatch.setattr(config, "ADMIN_USER", "alex")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "long-enough-1")
    cli.main(["stack", "--set", "suite.TZ=Europe/Brussels", "--proxies", "10.186.30.10"])
    assert [u["name"] for u in users.list_users()] == ["alex"] and users.list_users()[0]["suiteAdmin"]
    assert db.settings_of("")["TZ"] == "Europe/Brussels"
    out = capsys.readouterr().out
    assert "1 account(s)" in out and out.rstrip().endswith("ok")
    cli.main(["stack", "--set", "suite.TZ=Europe/Brussels", "--proxies", "10.186.30.10"])  # again: nothing to do, nobody made twice
    assert len(users.list_users()) == 1


def test_the_program_after_the_dashes_is_started_without_the_passwords_only_the_setup_needs(monkeypatch):
    ran = []
    monkeypatch.setenv("DB_ADMIN_PASSWORD", "r00t")
    monkeypatch.setenv("ADMIN_PASSWORD", "long-enough-1")
    monkeypatch.setenv("IOSUITE_DB_PASSWORD", "kept")
    monkeypatch.setattr(stack.os, "execvp", lambda f, argv: ran.append((f, argv, dict(stack.os.environ))))
    cli.main(["stack", "--set", "suite.TZ=UTC", "--proxies", "", "--", "iosuite", "serve", "--apps", "iopix"])
    (f, argv, env), = ran
    assert (f, argv) == ("iosuite", ["iosuite", "serve", "--apps", "iopix"])
    assert "DB_ADMIN_PASSWORD" not in env and "ADMIN_PASSWORD" not in env and env["IOSUITE_DB_PASSWORD"] == "kept"
    assert db.settings_of("")["TZ"] == "UTC"  # the options before the dashes were read as before


def test_nothing_is_started_without_the_dashes(monkeypatch):
    monkeypatch.setattr(stack.os, "execvp", lambda *_: pytest.fail("started something"))
    cli.main(["stack"])


def test_the_demo_is_for_a_new_suite_only():
    from iosuite_shared import demo
    users.create("alex", "secret123", suite_admin=True)
    assert stack.demo_once(log=QUIET) and demo.wanted()
    assert stack.demo_once(log=QUIET)  # there already: stays
    demo.switch(False)
    users.create("kim", "secret123")
    said = []
    assert not stack.demo_once(log=said.append) and not demo.wanted() and "accounts of its own" in said[0]
