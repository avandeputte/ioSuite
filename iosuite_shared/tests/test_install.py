"""`iosuite install`: the machine's file, which apps and packages, the service of each copy, and the command from a
new machine to a second copy (iosuite_shared.install). Nothing is installed: pip, apt and systemctl are stand-ins."""
import os
import types

import pytest

from iosuite_shared import catalog, cli, config, db, install, suite, users

ALL = catalog.install_order()


@pytest.fixture
def machine(tmp_path):
    """An empty program folder. What the command changes in this process (the environment, the settings read from the
    machine's file) is put back afterwards."""
    env = dict(os.environ)
    was = {k: getattr(config, k) for k in dir(config) if k.isupper()}
    for k in ("IOSUITE_DB_HOST", "IOSUITE_DB_PORT", "IOSUITE_DB_NAME", "IOSUITE_DB_USER", "IOSUITE_DB_PASSWORD", "APPS", "HOST", "PORT", "SYNC_PORT",
              "MCP_PORT", "DATA_DIR", "LOG_FILE", "IOSUITE_CONFIG", "DB_ADMIN_PASSWORD", "ADMIN_PASSWORD"):
        os.environ.pop(k, None)
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    yield tmp_path
    os.environ.clear()
    os.environ.update(env)
    for k, v in was.items():
        setattr(config, k, v)


class Ran:
    """Stand-in for subprocess.run: remembers the commands, says each one went well."""

    def __init__(self, failing=()):
        self.cmds, self.failing = [], failing

    def __call__(self, cmd, **kw):
        self.cmds.append(list(cmd))
        return types.SimpleNamespace(returncode=1 if any(f in " ".join(cmd) for f in self.failing) else 0, stdout=b"", stderr=b"")

    def of(self, word):
        return [c for c in self.cmds if word in c[0] or word in c[:3]]


def go(base, *argv, ran=None, said=None, answers=(), **kw):
    a = cli._parser().parse_args(["install", *argv])
    feed = iter(answers)
    said = said if said is not None else []
    return install.main(a, log=lambda *x: said.append(" ".join(str(i) for i in x)), run=ran or Ran(), ask=lambda q: next(feed),
                        secret=lambda q: next(feed), unit_dir=base / "units", base=base, **kw), said


# ---- the machine's file
def test_the_machine_s_file_keeps_its_comments_and_is_its_owner_s_alone(tmp_path):
    f = tmp_path / "config.env"
    install.write_env(f, {"IOSUITE_DB_HOST": "db.lan", "APPS": ""}, install.HEADER)
    assert f.read_text().startswith("# The machine's file") and install.read_env(f) == {"IOSUITE_DB_HOST": "db.lan", "APPS": ""}
    assert oct(f.stat().st_mode & 0o777) == "0o600"
    f.write_text("# mine\nIOSUITE_DB_HOST=db.lan\n  PORT = 8080\nAPPS='iostart'\n# HOST=127.0.0.1\n")
    install.write_env(f, {"PORT": 80, "APPS": "iostart,iotask", "HOST": None, "SYNC_PORT": "off"})
    assert f.read_text() == "# mine\nIOSUITE_DB_HOST=db.lan\nPORT=80\nAPPS=iostart,iotask\n# HOST=127.0.0.1\nSYNC_PORT=off\n"
    install.write_env(f, {"PORT": None})
    assert "PORT=80" not in f.read_text() and install.read_env(f)["APPS"] == "iostart,iotask"
    assert install.read_env(tmp_path / "none") == {}


# ---- which apps, which packages
def test_the_apps_a_list_names():
    assert install.parse_apps("iotask, iostart") == ["iostart", "iotask"] and install.parse_apps("all") == ALL and install.parse_apps("") == []
    with pytest.raises(SystemExit, match="no such app: iowhat"):
        install.parse_apps("iostart,iowhat")
    assert install.apps_of({}) == ALL and install.apps_of({"APPS": "iopix iostart"}) == ["iostart", "iopix"]
    assert install.apps_line(ALL) == "" and install.apps_line(["iostart", "iotask"]) == "iostart,iotask"


def test_the_packages_of_the_apps():
    assert install.extras_for(ALL) == "all" and install.extras_for(["iostart", "iotask"]) == "iostart,iotask"
    assert install.extras_for(["iostart", "iopix"], ["iopix-ai"]) == "iostart,iopix,iopix-ai" and install.extras_for(ALL, ["iopix-ai"]) == "all,iopix-ai"
    with pytest.raises(SystemExit, match="no such set of packages: torch"):
        install.extras_for(["iopix"], ["torch"])
    import tomllib
    known = tomllib.loads((catalog.ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    for k, m in catalog.APPS.items():
        assert k in known, f"pyproject.toml has no extra for {k}"
        for x in m.get("extras") or ():
            assert x in known, f"{k}/app.json names the extra {x}, which pyproject.toml does not have"
    assert install.system_packages(["iodocs", "iorecipe"]) == ["tesseract-ocr", "tesseract-ocr-eng", "poppler-utils"]
    assert "ffmpeg" in install.system_packages(["iopix"]) and install.system_packages(["iostart", "iotask"]) == []


def test_the_service_of_a_copy(tmp_path):
    u = install.unit(tmp_path, "iosuite")
    assert f"ExecStart={tmp_path}/.venv/bin/iosuite serve" in u and "User=iosuite" in u and "Restart=always" in u
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in u and "IOSUITE_CONFIG" not in u and "Nice" not in u
    p = install.unit(tmp_path, "alex", "pix", heavy=True)
    assert f"Environment=IOSUITE_CONFIG={tmp_path}/copies/pix/config.env" in p and "Description=ioSuite (pix)" in p and "OOMPolicy=continue" in p
    assert install.unit_name() == "iosuite" and install.unit_name("pix") == "iosuite-pix"


def test_the_list_to_tick(tmp_path):
    said = []
    feed = iter(["2 13", "x", "1", "a", "1", ""])
    asker = install.Asker(False, ask=lambda q: next(feed))
    asker.quiet = False
    want = install.choose(["iostart", "ionote"], asker, said.append)
    assert want == ALL[1:] and any("(to remove)" in t for t in said) and any("x: a number from 1 to 13" in t for t in said)
    t = install.table(["iostart"], ["iostart", "iocontact"])
    assert " 1 [x] ioStart" in t and "LDAP 3890" in t and "(to add)" in t and t.count("[x]") == 2
    assert install.choose(["iostart"], install.Asker(True), said.append) == ["iostart"]  # --yes: as it is


def test_ports():
    assert install.port_of(None, 80) == 80 and install.port_of("off", 8443) == 0 and install.port_of("8081", 80) == 8081
    with pytest.raises(SystemExit):
        install.port_of("http", 80)


# ---- the command
def test_a_new_machine(machine, monkeypatch):
    os.environ.update(IOSUITE_DB_PASSWORD="sh4red", ADMIN_PASSWORD="long-enough-1")
    ran = Ran()
    rc, said = go(machine, "--yes", "--apps", "iostart,iocalendar,iodocs", "--db", "db.lan:3307", "--admin", "alex",
                  "--address", "https://home.example.com/", "--no-service", ran=ran)
    cfg = install.read_env(machine / "config.env")
    assert rc == 0 and cfg["APPS"] == "iostart,iocalendar,iodocs" and cfg["IOSUITE_DB_HOST"] == "db.lan" and cfg["IOSUITE_DB_PORT"] == "3307"
    assert cfg["IOSUITE_DB_NAME"] == "iosuite" and cfg["IOSUITE_DB_USER"] == "iosuite" and cfg["IOSUITE_DB_PASSWORD"] == "sh4red"
    assert "SYNC_PORT" not in cfg and (machine / "EXTRAS").read_text() == "iostart,iocalendar,iodocs\n"
    pip = [c for c in ran.cmds if "install" in c and "-e" in c]
    assert len(pip) == 1 and pip[0][-1] == f"{machine}[iostart,iocalendar,iodocs]"
    assert not ran.of("systemctl") and not (machine / "SERVICES").exists()
    assert [u["name"] for u in users.list_users()] == ["alex"] and users.list_users()[0]["suiteAdmin"]
    assert db.settings_of("")["PUBLIC_URL"] == "https://home.example.com"
    assert config.APPS == ["iostart", "iocalendar", "iodocs"]  # this process reads the file it wrote
    text = "\n".join(said)
    assert "iosuite: ioStart, ioCalendar, ioDocs" in text and "Start it with:" in text and "sh4red" not in text and "long-enough-1" not in text


def test_the_questions_of_a_new_machine(machine, monkeypatch):
    monkeypatch.setattr(install.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(install, "listening", lambda h, p: True)
    answers = ["a", "",                     # the apps: all, then Enter
               "", "", "",                  # the server, the database, the login: as offered
               "",                          # no administrator: they exist
               "sh4red",                    # the login's password
               "alex", "long-enough-1",     # the first admin
               ""]                          # no address
    rc, said = go(machine, "--no-service", answers=answers)
    cfg = install.read_env(machine / "config.env")
    assert rc == 0 and cfg["APPS"] == "" and cfg["IOSUITE_DB_HOST"] == "127.0.0.1" and cfg["IOSUITE_DB_PASSWORD"] == "sh4red"
    assert (machine / "EXTRAS").read_text() == "all\n" and users.list_users()[0]["name"] == "alex" and "PUBLIC_URL" not in db.settings_of("")


def test_an_administrator_makes_the_databases_and_the_login(machine, monkeypatch):
    seen = {}

    def run(admin, password, names, t, connect=None, log=print, client=None, check=None):
        seen.update(admin=admin, password=password, names=list(names), login=(t["user"], t["password"]), client=client)
    monkeypatch.setattr("iosuite_shared.provision.run", run)
    os.environ["DB_ADMIN_PASSWORD"] = "r00t"
    rc, said = go(machine, "--yes", "--apps", "iostart,iotask", "--db", "db.lan", "--db-admin", "root", "--client-host", "192.168.1.%", "--no-service")
    made = install.read_env(machine / "config.env")["IOSUITE_DB_PASSWORD"]
    assert seen == {"admin": "root", "password": "r00t", "names": ["iostart", "iotask"], "login": ("iosuite", made), "client": "192.168.1.%"}
    assert len(made) >= 20 and any("password was made up" in t for t in said) and made not in "\n".join(said) and "r00t" not in "\n".join(said)


def test_what_is_missing_is_said(machine, monkeypatch):
    with pytest.raises(SystemExit, match="login needs a password"):
        go(machine, "--yes", "--db", "db.lan", "--no-service")
    assert not (machine / "config.env").exists()
    os.environ["IOSUITE_DB_PASSWORD"] = "sh4red"
    monkeypatch.setattr(users, "init", lambda: False)
    monkeypatch.setattr(db, "error", "(1045) Access denied")
    with pytest.raises(SystemExit, match=r"cannot be reached \(db.lan:3306/iosuite\): \(1045\) Access denied"):
        go(machine, "--yes", "--db", "db.lan", "--no-service")
    assert install.read_env(machine / "config.env")["IOSUITE_DB_HOST"] == "db.lan"  # the answers so far are kept
    with pytest.raises(SystemExit, match="needs root on a machine with systemd"):
        go(machine, "--yes", "--service", systemd=False)
    with pytest.raises(SystemExit, match="packages failed"):
        go(machine, "--yes", "--apps", "iostart", "--no-service", ran=Ran(failing=("-e",)))


def installed(machine, *more, ran=None):
    os.environ["IOSUITE_DB_PASSWORD"] = "sh4red"
    return go(machine, "--yes", "--db", "db.lan", "--admin", "", *more, ran=ran, systemd=True)


def test_the_service_is_written_and_started(machine, monkeypatch):
    (machine / "units").mkdir()
    monkeypatch.setattr(install, "owner_of", lambda p: "alex")
    monkeypatch.setattr(install, "ensure_user", lambda user, run=None, log=None: None)
    ran = Ran()
    rc, said = installed(machine, ran=ran)
    unit = (machine / "units" / "iosuite.service").read_text()
    assert "User=alex" in unit and "OOMPolicy=continue" in unit  # ioPix runs here
    assert (machine / "SERVICES").read_text() == "iosuite\n"
    sysd = [" ".join(c) for c in ran.of("systemctl")]
    assert sysd == ["systemctl daemon-reload", "systemctl enable -q iosuite", "systemctl restart iosuite", "systemctl is-active -q iosuite"]
    assert any("iosuite is running" in t for t in said) and any("journalctl -u iosuite" in t for t in said)
    with pytest.raises(SystemExit, match="did not start: journalctl -u iosuite"):
        installed(machine, ran=Ran(failing=("is-active",)))


def test_apps_are_added_and_removed_later(machine, monkeypatch):
    (machine / "units").mkdir()
    monkeypatch.setattr(install, "ensure_user", lambda user, run=None, log=None: None)
    installed(machine, "--apps", "iostart,iocalendar,iodns")
    suite.register("iodns", "ioDNS", copy=suite.copy_name())
    suite.register("iocalendar", "ioCalendar", copy=suite.copy_name())
    ran = Ran()
    rc, said = go(machine, "--yes", "--add", "iotask", "--remove", "iodns", ran=ran, systemd=True)
    cfg = install.read_env(machine / "config.env")
    assert cfg["APPS"] == "iostart,iocalendar,iotask" and cfg["IOSUITE_DB_PASSWORD"] == "sh4red"
    assert (machine / "EXTRAS").read_text() == "iostart,iocalendar,iotask\n" and "systemctl restart iosuite" in [" ".join(c) for c in ran.cmds]
    assert suite.get("iodns") is None and suite.get("iocalendar")  # off the suite's list: nothing answers for it any more
    ran = Ran()
    go(machine, "--yes", ran=ran, systemd=True)  # nothing changed: no packages asked for again
    assert not [c for c in ran.cmds if "-e" in c] and install.read_env(machine / "config.env")["APPS"] == "iostart,iocalendar,iotask"
    go(machine, "--yes", "--apps", "all", "--extras", "iopix-ai", systemd=True)
    assert install.read_env(machine / "config.env")["APPS"] == "" and (machine / "EXTRAS").read_text() == "all,iopix-ai\n"
    go(machine, "--yes", "--remove", "iodns", systemd=True)  # the optional packages chosen before are kept
    assert (machine / "EXTRAS").read_text().endswith(",iopix-ai\n") and "iodns" not in install.read_env(machine / "config.env")["APPS"]
    with pytest.raises(SystemExit, match="no app left"):
        go(machine, "--yes", "--apps", "", systemd=True)


def test_a_second_copy_on_one_machine(machine, monkeypatch):
    (machine / "units").mkdir()
    monkeypatch.setattr(install, "ensure_user", lambda user, run=None, log=None: None)
    with pytest.raises(SystemExit, match="set the main copy up first"):
        go(machine, "--yes", "--copy", "pix", systemd=True)
    installed(machine)
    ran = Ran()
    rc, said = go(machine, "--yes", "--copy", "pix", ran=ran, systemd=True)  # no apps named: the ones that are better apart
    main, pix = install.read_env(machine / "config.env"), install.read_env(machine / "copies" / "pix" / "config.env")
    assert pix["APPS"] == "iopix" and "iopix" not in main["APPS"] and main["APPS"].startswith("iostart,") and main["APPS"].count(",") == 11
    assert (pix["PORT"], pix["SYNC_PORT"], pix["MCP_PORT"]) == ("8081", "8082", "8083")
    assert pix["IOSUITE_DB_HOST"] == "db.lan" and pix["IOSUITE_DB_PASSWORD"] == "sh4red"  # the same suite
    assert pix["LOG_FILE"] == str(machine / "data" / "iosuite-pix.log") and pix["DATA_DIR"] == str(machine / "data")
    assert (machine / "SERVICES").read_text() == "iosuite\niosuite-pix\n" and (machine / "EXTRAS").read_text() == "all\n"
    assert "copies/pix/config.env" in (machine / "units" / "iosuite-pix.service").read_text()
    assert "OOMPolicy" not in (machine / "units" / "iosuite.service").read_text()
    assert {"systemctl restart iosuite", "systemctl restart iosuite-pix"} <= {" ".join(c) for c in ran.cmds}
    assert [k for k in install.copies(machine)] == ["", "pix"] and install.all_apps(machine) == ALL
    # the main copy never takes back what the second one runs; two copies never share a port
    go(machine, "--yes", "--apps", "all", systemd=True)
    assert "iopix" not in install.read_env(machine / "config.env")["APPS"]
    with pytest.raises(SystemExit, match="ports 80, 8443, 8444 are the main copy's"):
        go(machine, "--yes", "--copy", "pix", "--port", "80", "--sync-port", "8443", "--mcp-port", "8444", systemd=True)
    with pytest.raises(SystemExit, match="without an app"):
        go(machine, "--yes", "--copy", "pix", "--apps", "all", systemd=True)
    said = go(machine, "--list")[1]
    assert any(t.startswith("iosuite-pix: ioPix") for t in said) and any("pages 8081" in t for t in said)
    # and away again
    ran = Ran()
    go(machine, "--remove-copy", "pix", ran=ran, systemd=True)
    assert not (machine / "copies" / "pix").exists() and not (machine / "units" / "iosuite-pix.service").exists()
    assert (machine / "SERVICES").read_text() == "iosuite\n" and ["systemctl", "disable", "-q", "--now", "iosuite-pix"] in ran.cmds
    with pytest.raises(SystemExit, match="no copy 'pix' here"):
        go(machine, "--remove-copy", "pix", systemd=True)


def test_the_scripts_are_sound():
    import shutil
    import subprocess
    for name, shell in (("install.sh", "bash"), ("update.sh", "sh")):
        path = catalog.ROOT / name
        assert path.exists() and os.access(path, os.X_OK), name
        if shutil.which(shell):
            assert subprocess.run([shell, "-n", str(path)], capture_output=True).returncode == 0, name
    assert "avandeputte/iosuite2" in (catalog.ROOT / "install.sh").read_text() and "iosuite_shared.install missing-system" in (catalog.ROOT / "update.sh").read_text()
