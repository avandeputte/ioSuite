"""One home for an app's settings (iosuite_shared.config.live, routers.settings_router): every setting an app
declares is kept in the Shared ioSuite database, read as it is now, and changed in two places that show the same
values (Settings › Apps › All settings for suite admins, Settings › This app for the app's own)."""
import pytest

from iosuite_shared import admin, config, db


@pytest.fixture(autouse=True)
def forget_cached():
    db.settings_cache.clear()
    yield
    db.settings_cache.clear()


def test_a_setting_is_read_as_it_is_now():
    assert config.live("iocalendar", "HOLIDAYS") == ""
    db.set_setting("HOLIDAYS", '[{"country": "BE"}]', "iocalendar")
    db.settings_cache.clear()
    assert config.live("iocalendar", "HOLIDAYS") == '[{"country": "BE"}]'
    db.set_setting("HOLIDAYS", "", "iocalendar")       # back to the default
    db.settings_cache.clear()
    assert config.live("iocalendar", "HOLIDAYS") == ""


def test_the_declaration_says_the_default():
    assert config.live("iothings", "CURRENCY") == "USD"          # iothings/app.json
    assert config.live("iothings", "CURRENCY", "EUR") == "USD"   # the declaration wins over the caller's
    assert config.live("iothings", "NO_SUCH_SETTING", "mine") == "mine"


def test_a_switch_and_a_number():
    assert config.live_flag("iomoney", "MONARCH_AUTO", True) is True
    db.set_setting("MONARCH_AUTO", "0", "iomoney")
    db.settings_cache.clear()
    assert config.live_flag("iomoney", "MONARCH_AUTO", True) is False
    assert config.live_int("iodns", "DDNS_MINUTES", 99) == 5     # the declaration's own default
    db.set_setting("DDNS_MINUTES", "not a number", "iodns")
    db.settings_cache.clear()
    assert config.live_int("iodns", "DDNS_MINUTES", 99) == 99    # nonsense: the caller's


def test_the_apps_own_settings_fall_back_to_the_suites():
    db.set_setting("MCP_USER", "owner")                 # the whole suite's
    db.settings_cache.clear()
    assert config.live("iotask", "MCP_USER") == "owner"
    db.set_setting("MCP_USER", "ava", "iotask")
    db.settings_cache.clear()
    assert config.live("iotask", "MCP_USER") == "ava" and config.live("ionote", "MCP_USER") == "owner"


def test_which_settings_need_a_restart_and_which_are_edited_in_the_app():
    said = {d["name"]: d for d in config.declared("iocalendar")}
    assert said["PUBLIC_URL"]["restart"] is True and said["DB_NAME"]["restart"] is True
    assert "restart" not in said["CONTACT_BIRTHDAYS"]       # read as it is now
    assert said["HOLIDAYS"]["byApp"] is True               # its own screen in the app is the editor
    whole = {d["name"]: d for d in config.declared("")}
    assert whole["COOKIE_DOMAIN"]["restart"] is True and "restart" not in whole["KEEP_DELETED_DAYS"]


def test_every_app_declares_its_own_settings_with_upper_case_names_and_a_default_that_fits():
    from iosuite_shared import catalog
    for key, m in catalog.APPS.items():
        for d in m.get("settings") or []:
            assert d["name"].isupper(), f"{key}: {d['name']}"
            if d["type"] == "choice" and d.get("default"):
                flat = [c[0] if isinstance(c, (list, tuple)) else c for c in d["choices"]]
                assert d["default"] in flat, f"{key}/{d['name']}: {d['default']} is not one of {flat}"
            if d.get("byApp"):
                assert not d.get("restart"), f"{key}/{d['name']}: edited in the app, so read as it is now"


def test_both_screens_write_the_one_home():
    """Settings › This app (the app's own admins) and Settings › Apps › All settings (suite admins) change the same
    rows, so the two screens never disagree."""
    admin.set_setting("iocalendar", "CONTACT_BIRTHDAYS", False)
    assert db.settings_of("iocalendar")["CONTACT_BIRTHDAYS"] == "0"
    db.settings_cache.clear()
    assert config.live_flag("iocalendar", "CONTACT_BIRTHDAYS", True) is False
    shown = {a["app"]: a for a in admin.settings()["apps"]}
    if "iocalendar" in shown:   # it is listed once it has started on this database
        said = {d["name"]: d for d in shown["iocalendar"]["settings"]}
        assert said["CONTACT_BIRTHDAYS"]["value"] == "0"
    with pytest.raises(LookupError):
        admin.set_setting("iocalendar", "NO_SUCH_SETTING", "x")


def test_a_value_is_cleaned_the_same_way_whoever_sets_it():
    from iosuite_shared.errors import Invalid
    assert admin.set_setting("iodns", "DDNS_MINUTES", "7")["value"] == "7"
    with pytest.raises(Invalid):
        admin.set_setting("iodns", "DDNS_MINUTES", "soon")
    assert admin.set_setting("iomoney", "MONARCH_AUTO", True)["value"] == "1"
    assert admin.set_setting("iomoney", "MONARCH_AUTO", "")["value"] == ""   # the default again
    with pytest.raises(Invalid):
        admin.set_setting("iostart", "PHOTO_STRIP", "sometimes")             # not one of its choices
