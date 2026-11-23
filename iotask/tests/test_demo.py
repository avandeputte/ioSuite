"""The demo data (this app's module of the iosuite_demo package) goes into a fresh
database with the app's own code, once, and the family signs in to see it."""
from iosuite_shared import demo

from iotask import config, db


def test_the_demo_data_goes_in_once(client):
    demo.switch(True)
    demo.at_start(config.APP)  # what the app does at start: seed, mark
    assert demo.seeded(config.APP)
    assert db.one("SELECT count(*) AS n FROM tsk_tasks")["n"] > 30
    import iosuite_demo
    assert not iosuite_demo.seed(config.APP)  # once
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "riley", "password": demo.DEMO_PASSWORD}).status_code == 200
