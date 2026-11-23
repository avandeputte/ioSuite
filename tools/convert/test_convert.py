"""The converter's reading of an old install, its plan, and what it does to the services (tools/convert/convert.py).
The move itself, on a real old install and real databases, is rehearse.py."""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert  # noqa: E402


def old(tmp_path, key, lines, data=None, unit=None, version="3.44.0"):
    """An old app as its installer left it: <tmp>/opt/<app>/app with config.env, the shared library, a data folder."""
    folder = tmp_path / "opt" / key / "app"
    (folder / "shared" / "iosuite_shared").mkdir(parents=True)
    (folder / "shared" / "iosuite_shared" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    usual = ["DB_HOST=127.0.0.1", f"DB_NAME={key}", f"DB_USER={key}", "DB_PASSWORD=x", "IOSUITE_DB_PASSWORD=shared", "HOST=127.0.0.1"]
    (folder / "config.env").write_text("\n".join(usual + lines) + "\n")
    for name, text in (data or {}).items():
        (folder / "data" / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / "data" / name).write_text(text)
    units = tmp_path / "units"
    units.mkdir(exist_ok=True)
    if unit:
        (units / f"{key}.service").write_text(f"[Service]\nUser={unit}\n")
    return folder


def found(tmp_path, **kw):
    return convert.find([tmp_path / "opt"], unit_dir=tmp_path / "units", run=lambda cmd, **k: types.SimpleNamespace(returncode=0), **kw)


def planned(tmp_path, **kw):
    olds = found(tmp_path)
    p = convert.plan(olds, tmp_path / "new", **kw)
    convert.check_settings(p)
    return p


def stored(p):
    return {(a, n): v for a, n, v in p["settings"]}


def test_an_old_install_is_read_as_it_was_laid_out(tmp_path):
    old(tmp_path, "iostart", ["PORT=8630", "PUBLIC_URL=https://home.example.com/"], unit="alex")
    old(tmp_path, "iocalendar", ["PORT=8620", "DATA_DIR=/srv/calendar"], data={"x.txt": "1"})
    olds = found(tmp_path)
    assert [o["key"] for o in olds] == ["iostart", "iocalendar"]
    assert olds[0]["unit"] == "iostart" and olds[0]["user"] == "alex" and olds[0]["version"] == "3.44.0"
    assert olds[1]["unit"] is None and olds[1]["data_named"] is True
    assert found(tmp_path, only=["iocalendar"])[0]["key"] == "iocalendar"


def test_the_machines_file_and_the_suites_settings_come_from_the_start_page(tmp_path):
    old(tmp_path, "iostart", ["PORT=8630", "PUBLIC_URL=https://home.example.com", "COOKIE_DOMAIN=example.com", "TZ=Europe/Brussels",
                              "IOSUITE_DB_NAME=suite", "INTERNAL_URL=http://192.168.1.151:8630"])
    old(tmp_path, "iotask", ["PORT=8670", "COOKIE_DOMAIN=example.com", "IOSUITE_DB_NAME=suite", "DB_NAME=tasks", "KEEP_DELETED_DAYS=30"])
    p = planned(tmp_path)
    assert not p["problems"]
    assert p["machine"] == {"IOSUITE_DB_HOST": "127.0.0.1", "IOSUITE_DB_PORT": "3306", "IOSUITE_DB_NAME": "suite", "IOSUITE_DB_USER": "iosuite",
                            "IOSUITE_DB_PASSWORD": "shared", "APPS": "iostart,iotask", "HOST": "127.0.0.1", "INTERNAL_URL": "http://192.168.1.151"}
    s = stored(p)
    assert s[("suite", "PUBLIC_URL")] == "https://home.example.com" and s[("suite", "COOKIE_DOMAIN")] == "example.com" and s[("suite", "TZ")] == "Europe/Brussels"
    assert s[("iotask", "DB_NAME")] == "tasks" and ("iostart", "DB_NAME") not in s
    assert s[("iotask", "KEEP_DELETED_DAYS")] == "30" and ("suite", "KEEP_DELETED_DAYS") not in s  # one app's own, not the suite's
    assert p["databases"] == ["iostart", "tasks"]


def test_an_app_keeps_a_name_of_its_own_and_a_folder_of_the_suite_is_not_one(tmp_path):
    old(tmp_path, "iostart", ["PORT=8630", "PUBLIC_URL=https://home.example.com"])
    old(tmp_path, "iocalendar", ["PORT=8620", "PUBLIC_URL=https://calendar.example.com", "HOLIDAYS_COUNTRY=BE"])
    old(tmp_path, "iotask", ["PORT=8670", "PUBLIC_URL=https://home.example.com/tasks"])
    old(tmp_path, "ionote", ["PORT=8610", "PUBLIC_URL=https://other.example.com/notes"])
    p = planned(tmp_path)
    s = stored(p)
    assert s[("iocalendar", "PUBLIC_URL")] == s[("iocalendar", "SYNC_URL")] == s[("iocalendar", "MCP_URL")] == "https://calendar.example.com"
    assert s[("iocalendar", "HOLIDAYS_COUNTRY")] == "BE"
    assert ("iotask", "PUBLIC_URL") not in s and p["folders"] == [("tasks", "8670")]
    assert ("ionote", "PUBLIC_URL") not in s and any("other.example.com/notes" in n for n in p["notes"])
    table = {r["address"]: r for r in convert.routes(p)}
    assert table["https://calendar.example.com"] == {"address": "https://calendar.example.com", "was": "8620",
                                                     "devices": ["/dav", "/.well-known/", "/ics/"], "mcp": ["/mcp"]}
    home = table["https://home.example.com"]
    assert home["was"] == "8630" and "/dav/" in home["devices"] and "/tasks/dav" in home["devices"] and "/tasks/mcp" in home["mcp"]
    assert not any(x.startswith("/calendar") for x in home["devices"])  # its devices use its own name


def test_an_address_of_their_own_for_devices_replaces_the_apps_own(tmp_path):
    old(tmp_path, "iostart", ["PORT=8630", "PUBLIC_URL=https://home.example.com"])
    old(tmp_path, "iocalendar", ["PORT=8620", "PUBLIC_URL=https://calendar.example.com"])
    s = stored(planned(tmp_path, device_address="https://sync.example.com", mcp_address="https://mcp.example.com"))
    assert s[("suite", "SYNC_URL")] == "https://sync.example.com" and s[("suite", "MCP_URL")] == "https://mcp.example.com"
    assert ("iocalendar", "SYNC_URL") not in s and ("iocalendar", "MCP_URL") not in s


def test_what_is_in_the_way_is_said_and_nothing_is_done(tmp_path):
    old(tmp_path, "iostart", ["PORT=8630"])
    old(tmp_path, "iocalendar", ["PORT=8620", "IOSUITE_DB_NAME=another"])
    old(tmp_path, "iotask", ["PORT=8670"], version="3.20.1")
    folder = old(tmp_path, "ionote", ["PORT=8610"])
    (folder / "config.env").write_text((folder / "config.env").read_text().replace("DB_HOST=127.0.0.1", "DB_HOST=10.0.0.9\nIOSUITE_DB_HOST=127.0.0.1"))
    p = planned(tmp_path)
    text = "\n".join(p["problems"])
    assert "ioCalendar is of another suite" in text and "ioTask is at 3.20.1" in text and "ioNote's database ionote is on 10.0.0.9" in text
    assert convert.plan([], tmp_path / "new")["problems"]


def test_a_port_of_the_program_that_something_else_holds_is_in_the_way_but_not_an_old_apps_own(tmp_path):
    old(tmp_path, "iostart", ["PORT=80"])        # the old start page at port 80: free once it is stopped
    old(tmp_path, "iotask", ["PORT=8670"])
    p = planned(tmp_path)
    assert convert.taken(p, (80, 8443, 8444), port_open=lambda host, port: port in (80, 8443)) == [8443]
    assert convert.taken(p, (80, 0, 8444), port_open=lambda host, port: True) == [8444]  # a port switched off is not asked for


def test_an_old_suite_newer_than_the_one_this_program_was_made_from_is_moved_and_said(tmp_path):
    old(tmp_path, "iostart", ["PORT=8630"], version="3.46.2")
    p = planned(tmp_path)
    assert not p["problems"] and any("3.46.2, newer than" in n for n in p["notes"])


def test_data_is_copied_moved_or_left_and_a_folder_the_old_file_named_stays(tmp_path):
    old(tmp_path, "iostart", ["PORT=8630"], data={"a/b.txt": "hello", "iostart.log": "old lines"})
    named = tmp_path / "srv"
    (named / "thumbs").mkdir(parents=True)
    (named / "thumbs" / "1.jpg").write_text("x")
    old(tmp_path, "ionote", ["PORT=8610", f"DATA_DIR={named}"])
    old(tmp_path, "iotask", ["PORT=8670"])  # no data folder
    p = planned(tmp_path)
    assert [(d[0], d[3]) for d in p["data"]] == [("iostart", "copy"), ("ionote", "named")]
    assert stored(p)[("ionote", "DATA_DIR")] == str(named)
    convert.move_data(p, log=lambda *a: None)
    assert (tmp_path / "new" / "data" / "iostart" / "a" / "b.txt").read_text() == "hello"
    assert not (tmp_path / "new" / "data" / "iostart" / "iostart.log").exists()      # the old log stays behind
    assert (tmp_path / "opt" / "iostart" / "app" / "data" / "a" / "b.txt").exists()  # a copy: the old one is as it was
    assert stored(planned(tmp_path, data="stay"))[("iostart", "DATA_DIR")].endswith("/opt/iostart/app/data")
    moved = convert.move_data(planned(tmp_path / "x") if False else {**planned(tmp_path, data="move"), "data": [
        ("iostart", tmp_path / "opt" / "iostart" / "app" / "data", tmp_path / "moved" / "iostart", "move", 5)]}, log=lambda *a: None)
    assert moved and (tmp_path / "moved" / "iostart" / "a" / "b.txt").exists() and not (tmp_path / "opt" / "iostart" / "app" / "data").exists()


def test_a_folder_inside_the_old_data_folder_is_named_in_the_new_one(tmp_path):
    folder = old(tmp_path, "iobackup", ["PORT=8680"], data={"work/x": "1"})
    (folder / "config.env").write_text((folder / "config.env").read_text() + f"WORK_DIR={folder / 'data' / 'work'}\nBACKUP_DIR=/var/backups/mine\n")
    s = stored(planned(tmp_path))
    assert s[("iobackup", "WORK_DIR")] == str(tmp_path / "new" / "data" / "iobackup" / "work") and s[("iobackup", "BACKUP_DIR")] == "/var/backups/mine"
    assert stored(planned(tmp_path, data="stay"))[("iobackup", "WORK_DIR")] == str(folder / "data" / "work")


def test_what_an_old_file_still_held_is_carried_and_what_is_gone_is_said(tmp_path):
    old(tmp_path, "iostart", ["PORT=8630", "ACCUWEATHER_API_KEY=k1", "HA_URL=http://ha:8123", "UPDATE_CHECK=0", "IOSTART_BRANCH=main"])
    old(tmp_path, "iopix", ["PORT=8600", "GOOGLE_MAPS_API_KEY=k2", "DIGIKAM_DB_PASSWORD=pw", "MCP=1", "PHOTOS_ROOT=/srv/photos"])
    p = planned(tmp_path)
    carried = {(app, name): (where, value, wins) for app, where, value, wins, name in p["carried"]}
    assert carried[("iostart", "ACCUWEATHER_API_KEY")] == (("key", "accuweather_key"), "k1", True)
    assert carried[("iostart", "HA_URL")] == (("own", "prt_settings", "ha_url"), "http://ha:8123", True)
    assert carried[("iopix", "GOOGLE_MAPS_API_KEY")] == (("key", "google_maps_key"), "k2", False)
    assert carried[("iopix", "DIGIKAM_DB_PASSWORD")] == (("own", "pix_settings", "db_password"), "pw", False)
    assert stored(p)[("iopix", "PHOTOS_ROOT")] == "/srv/photos"
    assert any("MCP=1" in n for n in p["notes"])
    gone = {n for ns in p["gone"].values() for n in ns}
    assert {"PORT", "UPDATE_CHECK", "IOSTART_BRANCH", "DB_PASSWORD"} <= gone and "GOOGLE_MAPS_API_KEY" not in gone


def test_the_one_service_runs_as_the_account_the_old_ones_ran_as(tmp_path):
    old(tmp_path, "iostart", ["PORT=8630"], unit="root")
    old(tmp_path, "iotask", ["PORT=8670"], unit="root")
    old(tmp_path, "iopix", ["PORT=8600"], unit="alex")
    p = planned(tmp_path)
    assert p["user"] == "alex" and any("different accounts" in n for n in p["notes"])  # the photos are that account's
    assert p["units"] == [("iostart", True), ("iotask", True), ("iopix", True)]


# ---- what --apply does to the services, with everything it calls replaced
class Fake:
    def __init__(self, tmp_path, monkeypatch, install_code=0, silent=()):
        self.calls, self.base = [], tmp_path / "new"
        self.base.mkdir()
        from iosuite_shared import admin, config, provision, users
        monkeypatch.setattr(convert, "can_use", lambda t, names: [])
        monkeypatch.setattr(convert, "carry", lambda p, log=print: None)
        self.suite = {}  # what the suite has stored already
        monkeypatch.setattr(convert, "suite_says", lambda name: self.suite.get(name, ""))
        monkeypatch.setattr(config, "load_file", lambda f=None: f)
        monkeypatch.setattr(provision, "target", lambda: {"host": "127.0.0.1", "port": 3306, "name": "iosuite", "user": "iosuite", "password": "shared"})
        monkeypatch.setattr(users, "init", lambda: True)
        monkeypatch.setattr(admin, "set_setting", lambda app, name, value: self.calls.append(("set", app, name, value)))
        for k in ("IOSUITE_DB_HOST", "IOSUITE_DB_PORT", "IOSUITE_DB_NAME", "IOSUITE_DB_USER", "IOSUITE_DB_PASSWORD", "APPS", "HOST", "PORT"):
            monkeypatch.setenv(k, "")  # apply puts the machine's file into the environment: taken back after the test
        self.install_code, self.silent = install_code, list(silent)

    def run(self, cmd, **kw):
        installer = "iosuite_shared.cli" in cmd
        self.calls.append(tuple(cmd[:3]) if cmd[0] == "systemctl" else ("install", *cmd[4:]) if installer else ("packages", *cmd))
        return types.SimpleNamespace(returncode=self.install_code if installer else 0)

    def apply(self, p, **options):
        a = types.SimpleNamespace(no_service=False, host=None, port=None, sync_port=None, mcp_port=None, db_admin=None, client_host=None, user=None)
        for k, v in options.items():
            setattr(a, k, v)
        return convert.apply(p, a, self.base, run=self.run, log=lambda *x: None, systemd=options.get("systemd", True),
                             check=lambda p, port, host, wait=120, log=print: self.silent, port_open=lambda host, port: False)


def test_the_old_services_are_stopped_then_switched_off_once_every_app_answers(tmp_path, monkeypatch):
    old(tmp_path, "iostart", ["PORT=8630"], unit="alex", data={"x": "1"})
    old(tmp_path, "iotask", ["PORT=8670"], unit="alex")
    f = Fake(tmp_path, monkeypatch)
    p = convert.plan(found(tmp_path), f.base)
    assert f.apply(p) == 0
    systemctl = [c for c in f.calls if c[0] == "systemctl"]
    assert systemctl == [("systemctl", "stop", "iostart"), ("systemctl", "stop", "iotask"),
                         ("systemctl", "disable", "-q"), ("systemctl", "disable", "-q")]
    installer = next(c for c in f.calls if c[0] == "install")
    assert installer[1:] == ("--apps", "iostart,iotask", "--yes", "--service", "--user", "alex")
    order = [c[0] for c in f.calls if c[0] in ("packages", "systemctl", "install")]
    assert order.index("packages") < order.index("systemctl") < order.index("install")  # the packages while the old apps still run
    assert (f.base / "EXTRAS").read_text().strip() == "iostart,iotask"
    assert (f.base / "data" / "iostart" / "x").read_text() == "1"
    assert "IOSUITE_DB_PASSWORD=shared" in (f.base / "config.env").read_text()


def test_a_machine_without_the_start_page_leaves_what_the_suite_says_already(tmp_path, monkeypatch):
    old(tmp_path, "iopix", ["PORT=8600", "TZ=America/New_York", "COOKIE_DOMAIN=example.com"], unit="alex")
    f = Fake(tmp_path, monkeypatch)
    f.suite = {"TZ": "Europe/Brussels"}  # the machine with the start page was moved first
    assert f.apply(convert.plan(found(tmp_path), f.base)) == 0
    sets = {(c[1], c[2]): c[3] for c in f.calls if c[0] == "set"}
    assert ("_suite", "TZ") not in sets and sets[("_suite", "COOKIE_DOMAIN")] == "example.com"


@pytest.mark.parametrize("how", ["the installer fails", "an app does not answer"])
def test_when_the_program_does_not_come_up_the_old_services_run_again(tmp_path, monkeypatch, how):
    old(tmp_path, "iostart", ["PORT=8630"], unit="alex", data={"x": "1"})
    old(tmp_path, "iotask", ["PORT=8670"], unit="alex")
    f = Fake(tmp_path, monkeypatch, install_code=1 if how == "the installer fails" else 0, silent=["iotask"] if how != "the installer fails" else [])
    p = convert.plan(found(tmp_path), f.base, data="move")
    with pytest.raises(SystemExit) as e:
        f.apply(p)
    assert "The old service(s) run again (iostart, iotask)" in str(e.value)
    systemctl = [c for c in f.calls if c[0] == "systemctl"]
    assert systemctl[:2] == [("systemctl", "stop", "iostart"), ("systemctl", "stop", "iotask")]
    assert systemctl[2:] == [("systemctl", "disable", "-q"), ("systemctl", "start", "iostart"), ("systemctl", "start", "iotask")]
    assert (tmp_path / "opt" / "iostart" / "app" / "data" / "x").read_text() == "1"  # a folder that was moved is back


def test_without_systemd_nothing_is_stopped_and_running_old_apps_are_in_the_way(tmp_path, monkeypatch):
    old(tmp_path, "iostart", ["PORT=8630"])
    f = Fake(tmp_path, monkeypatch)
    p = convert.plan(found(tmp_path), f.base)
    assert f.apply(p, systemd=False) == 0
    assert not [c for c in f.calls if c[0] == "systemctl"] and next(c for c in f.calls if c[0] == "install")[4] == "--no-service"
    a = types.SimpleNamespace(no_service=True, host=None, port=None, sync_port=None, mcp_port=None, db_admin=None, client_host=None, user=None)
    with pytest.raises(SystemExit) as e:
        convert.apply(p, a, f.base, run=f.run, log=lambda *x: None, systemd=False, port_open=lambda host, port: True)
    assert "ioStart of the old install still run(s)" in str(e.value)


def test_a_data_folder_the_old_file_named_inside_the_install_moves_with_the_rest(tmp_path):
    """DATA_DIR=/opt/iopix/data names the old install's own folder: it belongs to the old program (and often to
    another account), so it moves like an unnamed one and nothing is stored. One on a disk of its own stays."""
    folder = old(tmp_path, "iopix", ["PORT=8640", f"DATA_DIR={tmp_path / 'opt' / 'iopix' / 'app' / 'data'}"], data={"index.db": "x"})
    assert folder.name == "app"
    o = found(tmp_path)[0]
    assert o["data"] == folder / "data" and o["data_named"] is False
    p = planned(tmp_path)
    assert [(d[0], d[3]) for d in p["data"]] == [("iopix", "copy")] and ("iopix", "DATA_DIR") not in stored(p)
    convert.move_data(p, log=lambda *a: None)
    assert (tmp_path / "new" / "data" / "iopix" / "index.db").read_text() == "x"
