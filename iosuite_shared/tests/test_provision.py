"""`iosuite provision`: the SQL planned from the machine's file and the run against a fake connection; no MariaDB."""
import pytest

from iosuite_shared import provision


@pytest.fixture
def fresh_db():
    """Overrides conftest's autouse database fixture: nothing here needs MariaDB."""
    yield


T = dict(host="db.lan", port=3307, name="iosuite", user="iosuite", password="sh4red")
HERE = lambda host, port: "192.168.1.30"  # noqa: E731  this machine's address towards db.lan


class FakeConn:
    def __init__(self, log, fail=None):
        self.log, self.fail = log, fail

    def cursor(self):
        conn = self

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, args=None):
                if conn.fail and conn.fail in sql:
                    raise OSError("(1044, 'Access denied')")
                conn.log.append((sql, args))
        return Cur()

    def close(self):
        self.log.append(("close", None))


def test_one_login_for_every_database():
    stmts = provision.plan_sql(T, ["iocalendar", "iopix"], here=HERE)
    sql = [s for s, _ in stmts]
    for name in ("iosuite", "iocalendar", "iopix"):
        assert f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" in sql
        assert (f"GRANT ALL PRIVILEGES ON `{name}`.* TO `iosuite`@%s", ("192.168.1.30",)) in stmts
    assert stmts[0] == ("CREATE USER IF NOT EXISTS `iosuite`@%s IDENTIFIED BY %s", ("192.168.1.30", "sh4red"))
    assert sum(s.startswith("CREATE USER") for s in sql) == 1 and sql[-1] == "FLUSH PRIVILEGES"
    assert not any(s.startswith(("ALTER USER", "DROP", "SET PASSWORD")) for s in sql), "an existing login keeps its password; nothing is dropped"
    assert all(a[0] == "192.168.1.30" for _, a in stmts if a), "a remote server: this machine only, never '%' or localhost"


def test_the_login_is_made_for_where_the_suite_connects_from():
    assert {a[0] for _, a in provision.plan_sql(T, ["ionote"], client="192.168.1.%", here=HERE) if a} == {"192.168.1.%"}
    local = provision.plan_sql(dict(T, host="127.0.0.1"), ["ionote"], here=HERE)
    assert {a[0] for _, a in local if a} == {"localhost", "127.0.0.1"}
    assert sum(s.startswith("GRANT") for s, _ in local) == 4


def test_a_database_named_twice_is_made_once_and_a_bad_name_is_refused():
    stmts = provision.plan_sql(T, ["iosuite", "ionote", "ionote"], here=HERE)
    assert sum(s.startswith("CREATE DATABASE") for s, _ in stmts) == 2
    for bad in (dict(T, name="suite; drop"), dict(T, user="io`suite")):
        with pytest.raises(SystemExit, match="letters, digits"):
            provision.plan_sql(bad, [], here=HERE)
    with pytest.raises(SystemExit, match="letters, digits"):
        provision.plan_sql(T, ["io note"], here=HERE)


def test_run_executes_everything_and_signs_in_as_the_login():
    seen, lines, signed = [], [], []
    made = provision.run("root", "rootpw", ["iohealth"], T, connect=lambda h, p: FakeConn(seen), log=lines.append, here=HERE, check=signed.append)
    assert made == ["iohealth", "iosuite"] and seen[-1] == ("close", None) and seen[-2] == ("FLUSH PRIVILEGES", None)
    assert "db.lan:3307: database(s) iohealth, iosuite ready for the login iosuite" in lines[0] and signed == [T]
    assert "rootpw" not in str(seen) and "rootpw" not in str(lines)


def test_run_says_what_went_wrong_in_one_line():
    def connect(h, p):
        raise OSError("refused")
    with pytest.raises(SystemExit, match="could not connect to db.lan:3307 as root"):
        provision.run("root", "x", [], T, connect=connect, log=lambda *_: None, here=HERE)
    seen = []
    with pytest.raises(SystemExit, match="db.lan:3307: CREATE DATABASE IF NOT EXISTS `ionote`.*Access denied"):
        provision.run("root", "x", ["ionote"], T, connect=lambda h, p: FakeConn(seen, fail="`ionote`"), log=lambda *_: None, here=HERE)
    assert seen[-1] == ("close", None)


def test_a_login_that_exists_with_another_password_is_said_not_changed():
    def wrong(t):
        raise OSError("Access denied")
    seen = []
    with pytest.raises(SystemExit, match="login iosuite cannot sign in with the password in the machine's file"):
        provision.run("root", "x", [], T, connect=lambda h, p: FakeConn(seen), log=lambda *_: None, here=HERE, check=wrong)
    assert not any(s.startswith("ALTER USER") for s, _ in seen)


def test_the_command(monkeypatch, capsys):
    from iosuite_shared import cli, config
    for k, v in (("DB_HOST", "127.0.0.1"), ("DB_PORT", 3306), ("DB_NAME", "iosuite"), ("DB_USER", "iosuite"), ("DB_PASSWORD", "sh4red")):
        monkeypatch.setattr(config, k, v)
    monkeypatch.setattr(provision, "databases", lambda apps: list(apps))
    cli.main(["provision", "--admin", "root", "--apps", "iocalendar,iotask", "--client-host", "%", "--dry-run"])
    out = capsys.readouterr().out
    assert "CREATE DATABASE IF NOT EXISTS `iocalendar`" in out and "CREATE DATABASE IF NOT EXISTS `iotask`" in out and "sh4red" not in out
    ran = []
    monkeypatch.setenv("DB_ADMIN_PASSWORD", "r00t")
    monkeypatch.setattr(provision, "run", lambda admin, password, names, t, client=None, log=print: ran.append((admin, password, names, t["user"], client)))
    cli.main(["provision", "--admin", "root", "--apps", "iotask"])
    assert ran == [("root", "r00t", ["iotask"], "iosuite", None)]
    monkeypatch.setattr(config, "DB_PASSWORD", "")
    with pytest.raises(SystemExit, match="IOSUITE_DB_PASSWORD is not set"):
        cli.main(["provision", "--admin", "root", "--dry-run"])
    with pytest.raises(SystemExit, match="no such app"):
        cli.main(["provision", "--admin", "root", "--apps", "nosuchapp", "--dry-run"])
