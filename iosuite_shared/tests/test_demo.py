"""The demo switch (iosuite_shared.demo) and the demo package beside it (iosuite_demo): the family's accounts, an app
seeded once while the switch is on, a seed that fails logged and left, and the command."""
import sys
import types

from iosuite_shared import cli, demo, family, users


def test_the_family_is_made_once_with_its_colours_and_roles():
    import iosuite_demo
    people = iosuite_demo.ensure()
    assert [p["name"] for p in people.values()] == list(demo.FAMILY_KEYS)
    assert iosuite_demo.ensure()["ava"]["id"] == people["ava"]["id"] and len(users.list_users()) == 4  # again: nobody made twice
    iosuite_demo.give_roles("iocalendar", people)
    assert users.authenticate("riley", demo.DEMO_PASSWORD)
    assert users.get(people["morgan"]["id"])["suiteAdmin"] and not users.get(people["riley"]["id"])["suiteAdmin"]
    fam = {m["name"]: m for m in family.members()}
    assert fam["theo"]["color"] == "#e8710a" and fam["ava"]["displayName"] == "Ava Calloway"
    assert users.roles_of(people["riley"]["id"]) == {"iocalendar": "admin"} and users.roles_of(people["theo"]["id"]) == {"iocalendar": "member"}


def test_an_app_is_seeded_once_while_the_switch_is_on(monkeypatch):
    calls = []
    task = types.ModuleType("iosuite_demo.iotask")  # stand-ins for two apps' seeds: one counts its calls, one fails
    task.seed = lambda people: calls.append(",".join(sorted(people)))
    cal = types.ModuleType("iosuite_demo.iocalendar")
    cal.seed = lambda people: 1 / 0
    monkeypatch.setitem(sys.modules, "iosuite_demo.iotask", task)
    monkeypatch.setitem(sys.modules, "iosuite_demo.iocalendar", cal)
    demo.at_start("iotask")
    assert not calls and not users.any_users()  # the switch is off: nothing at all
    demo.switch(True)
    demo.at_start("iotask")
    demo.at_start("iotask")
    assert calls == ["ava,morgan,riley,theo"] and demo.seeded("iotask")
    demo.at_start("iocalendar")  # a seed that fails is logged, never stops the app, and is not tried again
    assert demo.seeded("iocalendar")


def test_the_command_turns_it_on_and_off(capsys):
    cli.main(["demo"])
    assert demo.wanted() and "calloway" in capsys.readouterr().out
    cli.main(["demo", "--off"])
    assert not demo.wanted()


def test_a_picture_is_drawn():
    import io
    import pytest
    Image = pytest.importorskip("PIL.Image")
    import iosuite_demo
    raw = iosuite_demo.picture("Pancakes", "#e8a100", (300, 200))
    im = Image.open(io.BytesIO(raw))
    assert im.size == (300, 200) and im.format == "JPEG"
