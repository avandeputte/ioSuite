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


def test_the_page_is_the_shell_every_app_shares(): 
    """The nine apps with a sidebar keep no page of their own: it is built from the shell and their manifest
    (app.json's `page`), so a change to the page reaches them all."""
    from iosuite_shared import pages
    for app in FRAME:
        if app == "iostart":
            continue
        own = ROOT / app / "static" / "index.html"
        assert not own.exists(), f"{app} keeps a page of its own: the shell is iosuite_shared/static/page.html"
        m = catalog.APPS[app]
        html = pages.shell(m)
        assert f"<title>{m['name']}</title>" in html and m["color"] in html
        assert 'src="api/auth/theme.js"' in html and 'href="api/auth/base.css"' in html, app
        said = m.get("page") or {}
        assert ('id="q"' in html) is bool(said.get("search")), app
        assert ('id="newbtn"' in html) is bool(said.get("new")), app
        if said.get("search"):
            assert said["search"] in html and f'aria-label="{said.get("searchLabel") or "Search"}"' in html, app
        if said.get("new"):
            assert f'title="{said["new"]}"' in html and f'<span>{said.get("newLabel") or "New"}</span>' in html, app
            newbtn = [ln for ln in html.splitlines() if 'id="newbtn"' in ln][0]
            assert ("hidden>" in newbtn) is bool(said.get("newHidden")), app  # ioDNS shows it only where it may be used
    assert '<div class="grow"></div>' in pages.shell(catalog.APPS["iobackup"]), "no search box, no New button: the bar stretches"


def test_the_sidebar_is_made_of_the_parts_every_app_shares():
    """Each app's drawNav says only its own rows: the head, the rows, the headings and the More button are the
    frame's (navParts), so none of them drifts."""
    own = re.compile(r"class: 'navhead'|class: 'navmore'|class: `?navsec|class: 'navgap'")
    for app in FRAME:
        if app == "iostart":  # its own page, with no sidebar
            continue
        text = "\n".join(f.read_text(encoding="utf-8") for f in _scripts(app))
        assert "frame.navParts(store, {" in text, f"{app}'s sidebar does not use the shared parts"
        left = own.findall(text)
        assert not left, f"{app} draws its own {left} beside the frame's"



def _arguments(text: str, at: int) -> list:
    """The top-level arguments of the call whose opening bracket ends at `at`."""
    out, start, depth, quote, i = [], at, 0, None, at
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            elif quote == "`" and text.startswith("${", i):   # an expression inside a template: over it, brackets and all
                inner, i = 1, i + 2
                while i < len(text) and inner:
                    inner += {"{": 1, "}": -1}.get(text[i], 0)
                    i += 1
                continue
        elif c in "'\"`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return out + [text[start:i]]
            depth -= 1
        elif c == "," and depth == 0:
            out.append(text[start:i])
            start = i + 1
        i += 1
    return out


def test_nothing_that_may_be_null_is_handed_to_the_browsers_own_append():
    """el.append(x ? node : null) and el.replaceChildren(..., null) write the word "null" on the page (the weather row
    of the start page did, with no warning in force). fill() and put() of the frame leave such a part out, as h() does."""
    found, seen = [], 0
    for f in [f for app in catalog.APPS for f in _scripts(app)] + sorted(SHARED.glob("*.js")):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"\.(replaceChildren|append|prepend|before|after|replaceWith)\(", text):
            seen += 1
            for arg in _arguments(text, m.end()):
                if re.search(r":\s*(null|false|undefined)\s*$", arg) and not arg.lstrip().startswith("..."):
                    found.append(f"{f.relative_to(ROOT)}:{text.count(chr(10), 0, m.start()) + 1}: .{m.group(1)}(… {' '.join(arg.split())[:80]}")
    assert seen > 300, "the calls were not found: nothing was checked"
    assert not found, "use fill(el, ...) or put(el, ...) of the frame here:\n" + "\n".join(found)
