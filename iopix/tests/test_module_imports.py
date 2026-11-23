"""Every import in the app and the tests resolves: top-level ones, and the ones inside functions that only run
when a feature is used (a broken one there passes every other test and fails in front of the user)."""
import ast
import importlib
import importlib.util
import re
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent   # the iopix package
ROOT = PKG.parent                              # the program folder: module names are counted from here
FILES = sorted(p for p in PKG.rglob("*.py") if "tests" not in p.relative_to(PKG).parts) + sorted((PKG / "tests").glob("*.py"))


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve(node: ast.ImportFrom, mod: str, is_pkg: bool) -> str:
    if not node.level:
        return node.module or ""
    base = mod.split(".") if is_pkg else mod.split(".")[:-1]
    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
    return ".".join(base + ([node.module] if node.module else []))


def test_every_import_resolves():
    problems = []
    for path in FILES:
        mod = _module_name(path)
        tree = ast.parse(path.read_text(), str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = _resolve(node, mod, path.name == "__init__.py")
                if not target.startswith("iopix"):
                    continue
                try:
                    m = importlib.import_module(target)
                except Exception as e:
                    problems.append(f"{path.relative_to(ROOT)}:{node.lineno}: cannot import {target} ({e})")
                    continue
                for a in node.names:
                    if a.name == "*" or hasattr(m, a.name) or importlib.util.find_spec(f"{target}.{a.name}") is not None:
                        continue
                    problems.append(f"{path.relative_to(ROOT)}:{node.lineno}: {target} has no {a.name}")
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("iopix") and importlib.util.find_spec(a.name) is None:
                        problems.append(f"{path.relative_to(ROOT)}:{node.lineno}: no module {a.name}")
        # module paths written as strings: __import__("iopix.x"), "-m", "iopix.x"
        for m in re.finditer(r"""["'](iopix(?:\\.[a-z_]+)+)["']""", path.read_text()):
            name = m.group(1)
            if name.endswith((".js", ".css")) or ":" in name:
                continue
            if importlib.util.find_spec(name) is None:
                problems.append(f"{path.relative_to(ROOT)}: string module path {name} does not exist")
    assert not problems, "\n".join(problems)


def test_module_paths_in_scripts_and_docs_exist():
    """`python -m iopix.x` in the installers, the updater, the Dockerfile and the README must name real modules."""
    files = [ROOT / n for n in ("install.sh", "update.sh", "README.md", "Dockerfile", "docker-compose.yml")] + [PKG / "README.md"] + \
        [p for p in PKG.rglob("*.py") if "tests" not in p.relative_to(PKG).parts]
    missing = []
    for f in files:
        if not f.exists():
            continue
        text = f.read_text()
        for m in re.finditer(r"-m (iopix(?:\.[a-z_]+)+)", text):
            if importlib.util.find_spec(m.group(1)) is None:
                missing.append(f"{f.relative_to(ROOT)}: {m.group(1)}")
        if f.suffix == ".sh":  # python -c "from iopix.x import y" inside the shell scripts (setup.sh creates the admin and tests the database this way)
            for m in re.finditer(r"from (iopix(?:\.[a-z_]+)*) import ([a-zA-Z_, ]+)", text):
                mod = m.group(1)
                if importlib.util.find_spec(mod) is None:
                    missing.append(f"{f.relative_to(ROOT)}: {mod}"); continue
                for name in (n.strip() for n in m.group(2).split(",") if n.strip()):
                    if importlib.util.find_spec(f"{mod}.{name}") is None and not hasattr(importlib.import_module(mod), name):
                        missing.append(f"{f.relative_to(ROOT)}: {mod}.{name}")
    assert not missing, missing
