"""The front-end's hand-kept lists stay true to the files. No module declares a local name that hides one of its own
imports: v1.89.0 shared an upload helper `send` from core.js while Import and folder uploads kept local functions called
send: each then called itself instead of uploading, and Import failed with "Cannot read properties of undefined (reading
'token')". No module imports a name it never uses. sw.js's shell list names every module, and the page holds no inline
script (the appearance comes from the suite's api/auth/theme.js), so its content security policy needs no hash."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
JS = STATIC / "js"
# known and harmless: the local is the one meant everywhere in its scope, and the import is not used there
ALLOWED = {("pages.js", "date"), ("map.js", "go")}


def test_no_local_hides_an_import():
    found = []
    for f in sorted(JS.glob("*.js")):
        s = f.read_text()
        imported = set()
        for m in re.finditer(r"import \{([^}]*)\} from", s):
            imported |= {x.strip().split(" as ")[-1] for x in m.group(1).split(",") if x.strip()}
        for m in re.finditer(r"\b(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)\b", s):
            if m.group(1) in imported and (f.name, m.group(1)) not in ALLOWED:
                found.append(f"{f.name}:{s[:m.start()].count(chr(10)) + 1} {m.group(1)}")
    assert not found, "local names hiding imports: " + ", ".join(found)


def test_no_import_goes_unused():
    found = []
    for f in sorted(JS.glob("*.js")):
        s = f.read_text()
        body = re.sub(r"^import .*$", "", s, flags=re.M).replace("...", " ")  # a spread is not a property access
        for m in re.finditer(r"^import \{([^}]*)\} from", s, re.M):
            for n in [x.strip().split(" as ")[-1] for x in m.group(1).split(",") if x.strip()]:
                if not re.search(r"(?<![\w$.])%s(?![\w$])" % re.escape(n), body):
                    found.append(f"{f.name} {n}")
    assert not found, "imported but never used: " + ", ".join(found)


def test_service_worker_lists_every_module():
    sw = (STATIC / "sw.js").read_text()
    listed = set(re.search(r"const JS = \[([^\]]*)\]", sw).group(1).replace("'", "").replace(" ", "").split(","))
    assert listed == {f.stem for f in JS.glob("*.js")}


def test_the_page_has_no_inline_script():
    """Nothing inline, so the content security policy needs no hash: the appearance is applied by the suite's own
    api/auth/theme.js, and the service worker is registered from app.js."""
    html = (STATIC / "index.html").read_text()
    assert "<script>" not in html and "sha256-" not in html
    assert '<script src="api/auth/theme.js"></script>' in html
