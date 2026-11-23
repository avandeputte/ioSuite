"""Which parts of the Tests workflow a change needs: `python3 tools/parts.py BASE` prints `parts=[...]` (the shared
library's tests and the apps' whose folders changed) and `iopix=true|false` (its browser tests), for GITHUB_OUTPUT.

A change inside one app's folder needs that app's tests only: no app imports another. Anything else of the program
(the shared library, the demo data, pyproject.toml, the installer, the checks themselves) needs them all, as does a
change this cannot read (no BASE, or one git does not have)."""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = sorted(p.parent.name for p in ROOT.glob("*/app.json"))
ORDER = ["iosuite_shared", "iostart", "iocalendar", "iotask", "iocontact", "ionote", "iorecipe", "iothings", "iomoney",
         "iodocs", "iohealth", "iodns", "iobackup", "iopix"]
NOT_THE_PROGRAM = ("docs/", "devices/", "cloudflare/", "proxmox/")  # each has checks of its own, or none to run


def changed(base: str) -> list | None:
    """The files that differ from `base`; None when that cannot be told."""
    if not base or not base.strip("0"):
        return None
    got = subprocess.run(["git", "diff", "--name-only", base, "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return got.stdout.split() if got.returncode == 0 else None


def parts(files: list | None) -> list:
    everything = ORDER + [a for a in APPS if a not in ORDER]
    if files is None:
        return everything
    want = set()
    for f in files:
        first = f.split("/", 1)[0]
        if f.endswith(".md") or f.startswith(NOT_THE_PROGRAM):
            continue
        if first in APPS and "/" in f:
            want.add(first)
        else:
            return everything
    return [p for p in everything if p in want]


if __name__ == "__main__":
    out = parts(changed(sys.argv[1] if len(sys.argv) > 1 else ""))
    print("parts=" + json.dumps(out))
    print("iopix=" + ("true" if "iopix" in out else "false"))
