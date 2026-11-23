#!/usr/bin/env python3
"""Hold what the site says about the suite to the suite's own code.

    python3 tools/check-facts.py

The pages here are written by hand, so this is what keeps them true. The program is the folder above docs/ in this
repository. It reads docs/, landing/ and the READMEs (the repository's and each app's) and fails on:

  - a link to a file in this repository (raw.githubusercontent.com/.../iosuite/main/x,
    github.com/.../iosuite/blob|tree/main/x) that is not there;
  - a link into the first repository's files (github.com/.../iosuite-old/...), or an image of a single app
    (ghcr.io/.../<app>): the suite is one program in one repository, with one image;
  - a port of the time each app was a program of its own (8600 to 8720) next to an app's name;
  - a setting written as a command (`iosuite set APP NAME`, `--set APP.NAME=`) that no app declares;
  - the three ports (the pages, devices, MCP) said otherwise than the program's defaults;
  - the Proxmox container's size in docs/start/proxmox.md that is not the script's default;
  - an app missing from the Docker Compose builder's list (landing/compose/compose.js) or from the guide's list
    (docs/index.md), or one there with a name, a folder or paths for devices that are not its manifest's.

build.sh runs it before the site is built.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
SRC = HERE.parent
OWNER = "avandeputte"
REPO = "iosuite"
FIRST = "iosuite-old"  # the first repository, archived: an app was a program of its own there
# the apps, from their manifests (<app>/app.json), in their order
APPS = sorted((json.loads(p.read_text()) for p in SRC.glob("io*/app.json")), key=lambda m: m.get("order", 0))
LABELS = {m["name"]: m["key"] for m in APPS}
KEYS = {m["key"]: m for m in APPS}

problems = []


def pages():
    for p in sorted((HERE / "docs").rglob("*.md")) + sorted((HERE / "landing").rglob("*.html")) + sorted((HERE / "landing").rglob("*.js")) \
            + sorted((HERE / "landing").rglob("*.toml")) + [SRC / "README.md"] + sorted(SRC.glob("io*/README.md")):
        yield p, p.read_text()


def where(p) -> str:
    return str(p.relative_to(SRC))


def declared() -> dict:
    """{app key or 'suite': the names of its settings}: what every app has and the whole suite's (iosuite_shared/config.py),
    and each app's own (its manifest)."""
    text = (SRC / "iosuite_shared" / "config.py").read_text()
    a, b = text.index("\nCOMMON = ["), text.index("\nSUITE = [")
    every = set(re.findall(r'\{"name": "(\w+)"', text[a:b]))
    suite = set(re.findall(r'\{"name": "(\w+)"', text[b:text.index("\n]\n", b)]))
    out = {"suite": suite}
    for m in APPS:
        out[m["key"]] = every | {s["name"] for s in m.get("settings", [])}
    return out


def main():
    checked = 0

    # 1. links into the repository, and what still points at the first one
    link = re.compile(r"https://(?:raw\.githubusercontent\.com/%s/([\w.-]+)/main/|github\.com/%s/([\w.-]+)/(?:blob|tree)/main/)([^\s\"')<>`#?]+)" % (OWNER, OWNER))
    for p, text in pages():
        for m in link.finditer(text):
            repo, path = m.group(1) or m.group(2), m.group(3).rstrip(".,")
            if repo == FIRST:
                problems.append(f"{where(p)}: a link into the first repository ({path}); the suite is in {REPO}")
            if repo != REPO:
                continue
            checked += 1
            if not (SRC / path).exists():
                problems.append(f"{where(p)}: {path} is not in the repository")
        for m in re.finditer(r"ghcr\.io/%s/([\w-]+)(/[\w-]+)?" % OWNER, text):
            checked += 1
            if m.group(1) != REPO or m.group(2):
                problems.append(f"{where(p)}: {m.group(0)} is not the suite's image (ghcr.io/{OWNER}/{REPO})")

    # 2. a port of its own next to an app's name
    near = re.compile(r"\b(" + "|".join(LABELS) + r")\b(?:[^\n\d]{0,14}?)\b(8[67]\d0)\b")
    for p, text in pages():
        for m in near.finditer(text):
            problems.append(f"{where(p)}: {m.group(1)} on port {m.group(2)}: an app has no port of its own, it is in a folder of the suite's address")
    checked += 1

    # 3. settings written as commands
    known = declared()
    asked = re.compile(r"(?:iosuite set (\w+) ([A-Z][A-Z0-9_]+)\b|--set[= ](\w+)\.([A-Z][A-Z0-9_]+)=)")
    for p, text in pages():
        for m in asked.finditer(text):
            app, name = (m.group(1) or m.group(3)).lower(), m.group(2) or m.group(4)
            if app == "app":  # the pattern itself: --set APP.NAME=VALUE
                continue
            checked += 1
            if app not in known:
                problems.append(f"{where(p)}: {m.group(0)}: {app} is not an app of the suite")
            elif name not in known[app]:
                problems.append(f"{where(p)}: {m.group(0)}: {app} has no setting {name}")

    # 4. the three ports
    cfg = (SRC / "iosuite_shared" / "config.py").read_text()
    m = re.search(r'_port\("PORT", (\d+)\), _port\("SYNC_PORT", (\d+)\), _port\("MCP_PORT", (\d+)\)', cfg)
    ports = dict(zip(("web", "sync", "mcp"), m.groups())) if m else {}
    builder = (HERE / "landing" / "compose" / "compose.js").read_text()
    m = re.search(r'var DOORS = \{web: "(\d+)", sync: "(\d+)", mcp: "(\d+)"\}', builder)
    checked += 1
    if not ports or not m or dict(zip(("web", "sync", "mcp"), m.groups())) != ports:
        problems.append(f"landing/compose/compose.js: the three ports are not the program's defaults ({ports})")
    page = (HERE / "docs" / "reference" / "configuration.md").read_text()
    for name, key in (("PORT", "web"), ("SYNC_PORT", "sync"), ("MCP_PORT", "mcp")):
        checked += 1
        if ports and not re.search(r"\| `%s` \(%s\) \|" % (name, ports[key]), page):
            problems.append(f"docs/reference/configuration.md: {name} is {ports[key]} by default")

    # 5. the Docker Compose builder's list of apps, and the guide's
    row = re.compile(r'\{key:"(\w+)", name:"(\w+)", folder:"(\w*)", sub:"([\w-]+)", what:"([^"]*)"(?:, sync:(\[[^\]]*\]))?(, tool:true)?\}')
    listed = {m.group(1): m for m in row.finditer(builder)}
    for key, man in KEYS.items():
        checked += 1
        got = listed.get(key)
        if not got:
            problems.append(f"landing/compose/compose.js: {key} is not in the builder's list of apps")
            continue
        want = (man["name"], man.get("folder") or "", (man.get("compose") or {}).get("name"), (man.get("compose") or {}).get("what"),
                man.get("sync") or [], bool(man.get("adminTool")))
        have = (got.group(2), got.group(3), got.group(4), got.group(5), json.loads(got.group(6) or "[]"), bool(got.group(7)))
        if want != have:
            problems.append(f"landing/compose/compose.js: {key} is {have}, its manifest says {want}")
    for key in listed:
        if key not in KEYS:
            problems.append(f"landing/compose/compose.js: {key} is not an app of the suite")
    if [m.group(1) for m in row.finditer(builder)] != list(KEYS):
        problems.append("landing/compose/compose.js: the apps are not in their manifests' order")
    index = (HERE / "docs" / "index.md").read_text()
    for key, man in KEYS.items():
        checked += 1
        folder = "/" + (man["folder"] + "/" if man.get("folder") else "")
        if not re.search(r"^\| \[%s\]\(apps/%s\.md\) \|.*\| `%s` \|" % (man["name"], key, re.escape(folder)), index, re.M):
            problems.append(f"docs/index.md: {man['name']} is not in the list with its folder {folder}")

    # 6. the Proxmox container's size
    ct = (SRC / "proxmox" / "ct" / "iosuite.sh").read_text()
    var = {k: int(re.search(r'var_%s="\$\{var_%s:-(\d+)\}"' % (k, k), ct).group(1)) for k in ("cpu", "ram", "disk")}
    text = (HERE / "docs" / "start" / "proxmox.md").read_text()
    said = re.search(r"\((\d+) CPUs, (\d+) GB of memory and (\d+) GB of disk", text)
    checked += 1
    if not said or (int(said.group(1)), int(said.group(2)) * 1024, int(said.group(3))) != (var["cpu"], var["ram"], var["disk"]):
        problems.append(f"docs/start/proxmox.md: the container's size; the script says {var['cpu']} CPUs, {var['ram']} MB, {var['disk']} GB")

    print(f"checked {checked} claims about the suite against its code")
    if problems:
        print(f"\n{len(problems)} wrong:")
        for x in dict.fromkeys(problems):
            print("  - " + x)
        sys.exit(1)
    print("every checked claim holds")


if __name__ == "__main__":
    main()
