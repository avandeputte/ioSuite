"""The frame the apps' pages share (static/frame.js): served by every app beside ui.js, and every name a page's
script takes from the suite's modules, or from a module of its own, is one that module gives. The pages have no
build step and no tests of their own in JavaScript, so a name that is not there would only show as a blank page."""
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import catalog
from iosuite_shared.fastapi import Auth

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "iosuite_shared" / "static"
FRAME = ("iostart", "iocalendar", "iotask", "iorecipe", "iothings", "iomoney", "iodocs", "iocontact", "iodns", "iobackup")


def _exports(file: Path) -> set:
    s = file.read_text(encoding="utf-8")
    out = set(re.findall(r"^export (?:async )?(?:function\*?|const|let|class) ([\w$]+)", s, re.M))
    for m in re.finditer(r"^export \{([^}]*)\}", s, re.M):
        out |= {x.split(" as ")[-1].strip() for x in m.group(1).split(",") if x.strip()}
    return out


def _scripts(app: str) -> list:
    static = ROOT / app / "static"
    return [f for f in [static / "app.js", *sorted((static / "js").glob("*.js"))] if f.exists()]


def _target(file: Path, spec: str):
    if spec.endswith("/api/auth/ui.js") or (file.parent == SHARED and spec.endswith("/ui.js")):
        return SHARED / "account-panel.js"
    if spec.endswith("/api/auth/frame.js"):
        return SHARED / "frame.js"
    return (file.parent / spec).resolve() if spec.startswith(".") else None


def test_the_frame_is_served_by_every_app_to_anyone_as_a_script():
    auth = Auth("iotask")
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_paths=("/",)))
    app.include_router(auth.router())
    c = TestClient(app, base_url="http://tasks.example.com")
    assert c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"}).status_code == 200
    r = TestClient(app, base_url="http://tasks.example.com").get("/api/auth/frame.js")   # the sign-in screen is in it
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    assert r.headers["cache-control"] == "no-cache" and "export function signInScreen" in r.text


def test_every_name_a_page_imports_is_exported_where_it_is_imported_from():
    missing, seen = [], 0
    files = [f for app in catalog.APPS for f in _scripts(app)] + sorted(SHARED.glob("*.js"))
    for f in files:
        for m in re.finditer(r"^import \{([^}]*)\} from '([^']+)';", f.read_text(encoding="utf-8"), re.M):
            target = _target(f, m.group(2))
            if target is None:
                continue
            assert target.exists(), f"{f.relative_to(ROOT)} imports {m.group(2)}, which is not there"
            gives = _exports(target)
            for name in (x.split(" as ")[0].strip() for x in m.group(1).split(",") if x.strip()):
                seen += 1
                if name not in gives:
                    missing.append(f"{f.relative_to(ROOT)}: {name} from {target.relative_to(ROOT)}")
    assert seen > 500, "the imports were not found: nothing was checked"
    assert not missing, "imported and not exported:\n" + "\n".join(missing)


def test_the_apps_take_the_frame_from_the_suite_and_keep_no_copy_of_it():
    """What frame.js holds was in every one of these pages in the same words; a copy that comes back would drift again."""
    own = re.compile(r"^(?:export )?(?:async )?function (toggleSuite|closeSuite|appTile|popMenu|closeMenu|openNav|closeNav|confirmDialog)\(", re.M)
    for app in FRAME:
        text = "\n".join(f.read_text(encoding="utf-8") for f in _scripts(app))
        assert "/api/auth/frame.js'" in text, f"{app}'s page does not use the shared frame"
        assert not own.findall(text), f"{app}'s page has its own {own.findall(text)} beside the frame's"
        assert "const ICONS = {" not in text, f"{app}: its icons are added to the frame's (addIcons), not kept beside them"


def test_what_frame_uses_of_the_account_panels_is_there():
    used = re.search(r"^import \{([^}]*)\} from './ui.js';", (SHARED / "frame.js").read_text(encoding="utf-8"), re.M).group(1)
    assert {x.strip() for x in used.split(",")} <= _exports(SHARED / "account-panel.js")
