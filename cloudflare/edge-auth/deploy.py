"""Send worker.js to the Worker that is already set up (README.md, "After an update of the suite"), and nothing else:
its routes, its KV namespace and its variables (APPS, MODE) stay as they are, so no wrangler.toml is needed and no
host is named here. The workflow .github/workflows/edge.yml runs this; by hand:

    export CLOUDFLARE_API_TOKEN=…  CLOUDFLARE_ACCOUNT_ID=…
    python3 deploy.py [--name iosuite-edge-auth] [--dry-run]

It stops before sending when there is no Worker of that name, or when the one there has no KV namespace bound as
APP_PASSWORDS (then it is not this Worker, or it was never set up: setup.py does that). After sending it reads the
script back and says whether Cloudflare has what is in this folder.

It also says how the Worker is set up, without naming a host (a run's log may be public): its mode, the apps APPS
names and its routes, with a warning for what turns every device of a host away: a route on a host APPS does not
name, a host named for something that is no app of the suite.

The token needs Account › Workers Scripts: Edit; with Zone › Workers Routes it reads the routes too. Standard library
only.
"""
import argparse
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
import uuid

API = "https://api.cloudflare.com/client/v4"
HERE = pathlib.Path(__file__).resolve().parent
MAIN = "worker.js"
NAMESPACE = "APP_PASSWORDS"


def call(method: str, path: str, data: bytes | None = None, content_type: str = "application/json", raw: bool = False):
    """One Cloudflare API call: (status, the answer's result, or its bytes with raw). An answer that is not a
    success is (status, what Cloudflare said went wrong)."""
    req = urllib.request.Request(API + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + os.environ["CLOUDFLARE_API_TOKEN"], "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return r.status, body if raw else json.loads(body).get("result")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            said = "; ".join(x.get("message", "") for x in json.loads(body).get("errors", [])) or body[:300].decode("utf-8", "replace")
        except ValueError:
            said = body[:300].decode("utf-8", "replace")
        return e.code, said


def apps_named(text: str) -> dict | None:
    """How many hosts APPS gives each app ({"calendar.example.com": "iocalendar"} is {"iocalendar": 1}); None when it
    is not what the Worker can read. The hosts themselves are not printed: a run's log may be public."""
    try:
        apps = json.loads(text or "{}")
    except ValueError:
        return None
    if not isinstance(apps, dict):
        return None
    named: dict = {}
    for app in apps.values():
        named[str(app)] = named.get(str(app), 0) + 1
    return named


def suite_apps() -> set:
    """The names the suite publishes app passwords under: each app's key (its app.json), where devices sign in."""
    found = set()
    for manifest in HERE.parent.parent.glob("*/app.json"):
        try:
            app = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if app.get("sync"):
            found.add(app.get("key"))
    return found


def routes(name: str) -> list | None:
    """The Worker's routes as (host, path) pairs, from every zone the token sees; None when the token may not look
    (it needs Zone › Workers Routes: Read or Edit; sending the script does not)."""
    status, zones = call("GET", "/zones?per_page=50")
    if status != 200 or not isinstance(zones, list):
        return None
    found, looked = [], False
    for z in zones:
        status, rs = call("GET", f"/zones/{z['id']}/workers/routes")
        if status != 200 or not isinstance(rs, list):
            continue
        looked = True
        for r in rs:
            if r.get("script") == name:
                host, _, path = (r.get("pattern") or "").partition("/")
                found.append((host.lower(), "/" + path))
    return found if looked else None


def form(script: bytes) -> tuple[bytes, str]:
    """The script as Cloudflare takes it: a form with what the main module is called, and the module."""
    edge = "ioSuite" + uuid.uuid4().hex
    parts = [
        ('Content-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n', json.dumps({"main_module": MAIN}).encode()),
        (f'Content-Disposition: form-data; name="{MAIN}"; filename="{MAIN}"\r\nContent-Type: application/javascript+module\r\n\r\n', script),
    ]
    body = b"".join(f"--{edge}\r\n{head}".encode() + data + b"\r\n" for head, data in parts) + f"--{edge}--\r\n".encode()
    return body, f"multipart/form-data; boundary={edge}"


def main():
    p = argparse.ArgumentParser(description="Send worker.js to the Worker that is already set up; its routes, namespace and variables stay.")
    p.add_argument("--name", default="iosuite-edge-auth", help="the Worker's name (setup.py's)")
    p.add_argument("--dry-run", action="store_true", help="look at the Worker, send nothing")
    a = p.parse_args()
    for v in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if not os.environ.get(v):
            sys.exit(f"{v} is not set")
    scripts = f"/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}/workers/scripts/{a.name}"
    script = (HERE / MAIN).read_bytes()
    mark = hashlib.sha256(script).hexdigest()[:10]

    status, settings = call("GET", scripts + "/settings")
    if status == 404:
        sys.exit(f"There is no Worker named {a.name} on this account: nothing sent. setup.py sets it up (README.md).")
    if status != 200:
        sys.exit(f"Reading the Worker {a.name}: HTTP {status} {settings}")
    bindings = {b.get("name"): b for b in (settings or {}).get("bindings", [])}
    if (bindings.get(NAMESPACE) or {}).get("type") != "kv_namespace":
        sys.exit(f"The Worker {a.name} has no KV namespace bound as {NAMESPACE}: nothing sent. setup.py sets it up (README.md).")
    mode = (bindings.get("MODE") or {}).get("text") or "monitor"
    print(f"Worker {a.name}: {NAMESPACE} is bound, APPS is {'set' if 'APPS' in bindings else 'NOT set'}, MODE is {mode}")
    named = apps_named((bindings.get("APPS") or {}).get("text") or "")
    if named is None:
        print("::warning::APPS is not JSON: the Worker checks nothing. setup.py writes it (README.md).")
    else:
        hosts = {str(h).lower(): str(app) for h, app in json.loads(bindings["APPS"]["text"]).items()} if named else {}
        mine = routes(a.name)
        if mine is None:
            print("its routes: not looked at (this token does not read the zone's Workers routes)")
        for host, path in sorted(mine or [], key=lambda r: (hosts.get(r[0], ""), r[1])):
            if host in hosts:
                print(f"route {path} on the host of {hosts[host]}")
            else:
                # the Worker checks /dav* of a host it has no app for too, finds no password and, enforcing, answers 401
                print(f"::warning::A route ({path}) is on a host that APPS does not name: the Worker has no app to look its app "
                      f"passwords up for and, enforcing, turns every device there away. Add the host to APPS with its app "
                      f"(setup.py --host <host>=<app>), or remove the route.")
        known = suite_apps()
        print("APPS names " + (", ".join(f"{app} ({n} host{'s' if n > 1 else ''})" for app, n in sorted(named.items())) or "no host"))
        for app in sorted(set(named) - known):
            # the keys the suite publishes are <app>:<prefix> with the app's own name, so under another name the
            # Worker finds no password and turns every request of that host away
            print(f"::warning::APPS names {app!r}, which is no app of the suite ({', '.join(sorted(known))}): the Worker finds no "
                  f"app password for that host and, enforcing, turns its devices away. Name the host's app in APPS (README.md).")

    if a.dry_run:
        print(f"would send {MAIN} ({len(script)} bytes, {mark})")
        return
    body, content_type = form(script)
    status, sent = call("PUT", scripts + "/content", body, content_type)
    if status != 200:
        sys.exit(f"Sending {MAIN}: HTTP {status} {sent}")
    print(f"sent {MAIN} ({len(script)} bytes, {mark})" + (f", Cloudflare has it as of {sent['modified_on']}" if isinstance(sent, dict) and sent.get("modified_on") else ""))

    status, back = call("GET", scripts + "/content/v2", raw=True)
    if status != 200:
        print(f"::warning::{MAIN} was sent, but reading it back to compare gave HTTP {status} {back}")
    elif script.strip() not in back:
        sys.exit(f"{MAIN} was sent, but what Cloudflare gives back for {a.name} ({len(back)} bytes) does not hold it")
    else:
        print("read back: Cloudflare runs what is in this folder")
    status, after = call("GET", scripts + "/settings")
    kept = status == 200 and {b.get("name") for b in (after or {}).get("bindings", [])} >= set(bindings)
    if not kept:
        sys.exit(f"The Worker's namespace or variables are not as they were before sending: look at {a.name} in the dashboard")
    print("its namespace and variables are as they were")


if __name__ == "__main__":
    main()
