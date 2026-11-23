#!/bin/sh
# Update an installed ioSuite in place: the program folder this script is in (an installed copy such as /opt/iosuite,
# or a git checkout). Docker users pull the image instead.
#
#   ./update.sh            fetch the latest code, refresh the packages, restart the service(s)
#   ./update.sh --check    only say whether something newer exists (IOSUITE_REF is honoured)
#   ./update.sh --force    reinstall and restart even when the installed commit is already the latest
#   IOSUITE_REF=<sha|branch> ./update.sh   install that commit instead of the tip of the branch
#     (right after a push GitHub may still report the previous commit; naming the sha avoids that)
#   IOSUITE_REPO, IOSUITE_BRANCH   what is followed (avandeputte/iosuite, main; the machine's file may say so too)
#   IOSUITE_RESULT=<file>  write the outcome ("ok: ..." or "error: ...") there before the restart, so the web app
#     can show it afterwards (its own child process dies in the restart)
#   IOSUITE_RUNNING=<version>  the version the running program is (the web app says it): when the code here is newer
#     already (another copy on this machine updated the folder), the packages are refreshed and it is restarted all the same
#
# The program folder holds the code of every app, one Python environment (.venv), the machine's file (config.env), the
# data folder and, for more copies on one machine, copies/<name>/config.env. Only the code is replaced: settings,
# data and the environment are never touched. The order protects the install: the Python packages the new version
# asks for (its pyproject.toml) are installed first, and the code moves only once that succeeded, so a failed package
# install leaves the installed version running as it was; a failed swap puts the previous files back.
# Settings › Servers › Updates runs this same script from the web app.
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
# what is never replaced: the machine's own
KEEP=" config.env data copies .venv COMMIT FILES EXTRAS SERVICES .update-stage .git "

# the machine's file may name the repository and the branch (development); the environment wins
conf() { [ -f "$APP/config.env" ] && sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$APP/config.env" | tail -1 | sed "s/^[\"']//; s/[\"']\$//"; }
REPO="${IOSUITE_REPO:-$(conf IOSUITE_REPO)}"; REPO="${REPO:-avandeputte/iosuite}"
BRANCH="${IOSUITE_BRANCH:-$(conf IOSUITE_BRANCH)}"; BRANCH="${BRANCH:-main}"
REF="${IOSUITE_REF:-$BRANCH}"
RESULT="${IOSUITE_RESULT:-}"
RUNNING="${IOSUITE_RUNNING:-}"
case "$REPO" in */*) ;; *) printf 'error: bad repository: %s (owner/name)\n' "$REPO" >&2; exit 1;; esac
case "$REF" in -*|*..*|*/*/*) printf 'error: bad ref: %s\n' "$REF" >&2; exit 1;; esac  # a commit id or a branch, never an option or a path
FORCE=0; CHECK=0
for a in "$@"; do case "$a" in --force) FORCE=1;; --check) CHECK=1;; *) printf 'error: unknown option %s (--check, --force)\n' "$a" >&2; exit 2;; esac; done
TMP=""; NOTED=0; STAGE=""
# on a failure the result file gets die's own words; the generic line is for failures that never reached die (set -e)
cleanup() { rc=$?; [ -n "$TMP" ] && rm -rf "${TMP:?}"; [ $rc -ne 0 ] && [ "$NOTED" = 0 ] && [ -n "$RESULT" ] && printf 'error: update.sh failed (exit %s); see the log\n' "$rc" > "$RESULT" 2>/dev/null; true; }
trap cleanup EXIT
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
note() { [ -n "$RESULT" ] && printf '%s\n' "$*" > "$RESULT" 2>/dev/null || true; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; note "error: $*"; NOTED=1; exit 1; }
# a checkout is pulled; an installed copy records its commit in COMMIT and is replaced from GitHub's archive of a commit
GIT=0; [ -e "$APP/.git" ] && GIT=1
local_commit() { if [ "$GIT" = 1 ]; then git -C "$APP" rev-parse HEAD 2>/dev/null; elif [ -f COMMIT ]; then cat COMMIT; else echo unknown; fi; }
version_of() { sed -n 's/^__version__ = "\([^"]*\)".*/\1/p' "$1/iosuite_shared/__init__.py" 2>/dev/null; }
# network access through the program's own Python (no curl needed inside a container)
PYF="$(ls -d .venv/bin/python 2>/dev/null || command -v python3)"
fetch() { "$PYF" -c 'import sys, urllib.request
req = urllib.request.Request(sys.argv[1], headers={"User-Agent": "iosuite-update", "Accept": "application/vnd.github+json"})
with urllib.request.urlopen(req, timeout=120) as r, open(sys.argv[2], "wb") as f:
    while True:
        b = r.read(1 << 20)
        if not b:
            break
        f.write(b)' "$1" "$2"; }
# the commit a branch (or tag) is at: from GitHub's git address, as git itself asks it, which has no hourly limit;
# api.github.com allows a server 60 unsigned calls an hour. Prints the commit id, or "error: <why>"
remote_commit() { "$PYF" - "$REPO" "${1:-$BRANCH}" <<'PYEOF'
import json, re, sys, urllib.error, urllib.request
repo, ref = sys.argv[1:3]
if re.fullmatch(r"[0-9a-f]{40}", ref):
    print(ref); sys.exit()
why = []
def get(url, accept):
    req = urllib.request.Request(url, headers={"User-Agent": "iosuite-update", "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()
try:
    refs = get(f"https://github.com/{repo}.git/info/refs?service=git-upload-pack", "*/*").decode("utf-8", "replace")
    m = re.search(r"([0-9a-f]{40}) refs/(?:heads|tags)/" + re.escape(ref) + r"(?=[\x00\n])", refs)
    if m:
        print(m.group(1)); sys.exit()
    why.append(f"github.com has no branch or tag {ref}")
except Exception as e:  # noqa: BLE001
    why.append(f"github.com: {e}")
try:  # a short commit id, or github.com could not be reached
    print(json.loads(get(f"https://api.github.com/repos/{repo}/commits/{ref}", "application/vnd.github+json"))["sha"]); sys.exit()
except urllib.error.HTTPError as e:
    why.append(f"api.github.com: HTTP {e.code} " + ("(its hourly limit is used up; it resets within the hour)" if e.code in (403, 429) else e.reason))
except Exception as e:  # noqa: BLE001
    why.append(f"api.github.com: {e}")
print("error: " + "; ".join(why))
PYEOF
}
if [ "$CHECK" = 1 ]; then
  L="$(local_commit)"; R="$(remote_commit "$REF")" || R=""  # a failed lookup must reach die, not set -e
  case "$R" in ""|error*) die "could not look up $REF on GitHub: ${R#error: }";; esac
  if [ "$L" = "$R" ]; then echo "up to date ($(echo "$L" | cut -c1-7))"; else echo "update available: $(echo "$R" | cut -c1-7) (installed $(echo "$L" | cut -c1-7))"; fi
  exit 0
fi

VPY="$APP/.venv/bin/python"
[ -x "$VPY" ] || die "no .venv here; install with install.sh first"
TMP="$(mktemp -d)"
# the program is up to date on disk, yet what runs is older: another copy on this machine updated the folder
stale() { [ -n "$RUNNING" ] && [ "$RUNNING" != "$(version_of "$APP")" ]; }

say "Fetching the latest code"
if [ "$GIT" = 1 ]; then
  git -C "$APP" fetch -q origin "$REF" || die "git fetch failed (could not reach GitHub?)"
  if [ "$FORCE" = 0 ] && [ "$(git -C "$APP" rev-parse HEAD)" = "$(git -C "$APP" rev-parse FETCH_HEAD)" ]; then
    if ! stale; then say "Already up to date ($(local_commit | cut -c1-7)); nothing to do"; note "ok: already up to date ($(local_commit | cut -c1-7))"; exit 0; fi
    say "The code here is already v$(version_of "$APP"); what runs is v$RUNNING: restarting on the new code"
  fi
  # what would make the merge fail is checked now, before any package is touched
  git -C "$APP" merge-base --is-ancestor HEAD FETCH_HEAD || die "this checkout has commits that are not on $REF (not a fast-forward); update it by hand"
  git -C "$APP" diff --name-only HEAD -- | while IFS= read -r f; do
    [ -n "$f" ] && ! git -C "$APP" diff --quiet HEAD FETCH_HEAD -- "$f" && { printf '  locally changed and also changed by the update: %s\n' "$f" >&2; exit 1; }
    :
  done || die "local changes to files the update also changes (git stash them first)"
  git -C "$APP" show "FETCH_HEAD:pyproject.toml" > "$TMP/pyproject.toml" 2>/dev/null || die "the fetched commit has no pyproject.toml"
else
  # the archive is fetched by commit id, so the code and the recorded COMMIT always match
  R="$(remote_commit "$REF")" || R=""
  case "$R" in ""|error*) die "could not look up $REF on GitHub: ${R#error: }";; esac
  if [ "$FORCE" = 0 ] && [ "$R" = "$(local_commit)" ]; then
    if ! stale; then say "Already up to date ($(echo "$R" | cut -c1-7)); nothing to do"; note "ok: already up to date ($(echo "$R" | cut -c1-7))"; exit 0; fi
    say "The code here is already v$(version_of "$APP"); what runs is v$RUNNING: restarting on the new code"
  fi
  fetch "https://github.com/$REPO/archive/$R.tar.gz" "$TMP/src.tgz" || die "download failed"
  mkdir "$TMP/src" && tar xzf "$TMP/src.tgz" -C "$TMP/src" || die "the downloaded archive could not be read"
  TOP="$(ls -d "$TMP"/src/*/ | head -1)"; TOP="${TOP%/}"
  [ -f "$TOP/pyproject.toml" ] && [ -d "$TOP/iosuite_shared" ] && [ -f "$TOP/update.sh" ] || die "the downloaded archive has no pyproject.toml or no iosuite_shared/ (is $REPO the suite's repository?)"
  # stage everything first; the swap comes after the packages are in
  STAGE="$APP/.update-stage"; rm -rf "${STAGE:?}"; mkdir -p "$STAGE"
  ( cd "$TOP" && ls -A ) | while IFS= read -r item; do
    case "$KEEP" in *" $item "*) continue;; esac
    case "$item" in .github|.gitignore|.dockerignore|docs|devices|proxmox) continue;; esac  # what no server runs
    cp -R "$TOP/$item" "$STAGE/$item"
  done
  cp "$STAGE/pyproject.toml" "$TMP/pyproject.toml"
fi

say "Refreshing the Python packages (the new version's, before the code moves)"
# the extras installed here (EXTRAS, written by the installer: the apps of this machine and what was chosen beside
# them, such as iopix-ai); none recorded: every app's
G="$(cat EXTRAS 2>/dev/null | tr -d ' \n')"; G="${G:-all}"
"$VPY" - "$TMP/pyproject.toml" "$G" > "$TMP/requirements.txt" <<'PYEOF' || die "could not read the fetched pyproject.toml"
import re, sys
path, groups = sys.argv[1], [g for g in sys.argv[2].split(",") if g]
try:
    import tomllib
except ImportError:  # Python 3.10: a plain reading of the array shape pyproject.toml uses
    tomllib = None
deps = []
if tomllib:
    with open(path, "rb") as f:
        proj = tomllib.load(f).get("project", {})
    deps += proj.get("dependencies", [])
    for g in groups:
        deps += proj.get("optional-dependencies", {}).get(g, [])
else:
    text = open(path, encoding="utf-8").read()
    def arr(key):
        m = re.search(r"^\s*" + re.escape(key) + r'\s*=\s*\[((?:[^\]"]|"[^"]*")*)\]', text, re.M)
        return re.findall(r'"([^"]+)"', m.group(1)) if m else []
    deps += arr("dependencies")
    for g in groups:
        deps += arr(g)
print("\n".join(dict.fromkeys(deps)))
PYEOF
pipi() { if command -v uv >/dev/null 2>&1; then uv pip install -q -p "$VPY" "$@"; else "$VPY" -m pip install -q --disable-pip-version-check "$@"; fi; }
pipi -r "$TMP/requirements.txt" || { [ -n "$STAGE" ] && rm -rf "${STAGE:?}"; die "installing the Python packages failed; the installed version is unchanged (code and packages)"; }

say "Installing the new code"
if [ "$GIT" = 1 ]; then
  git -C "$APP" merge -q --ff-only FETCH_HEAD || die "git merge failed (local changes?); the packages were refreshed, the code is unchanged"
else
  MOVED=""
  swap_back() { for item in $MOVED; do rm -rf "${APP:?}/${item:?}"; [ -e "$APP/$item.old" ] && mv "$APP/$item.old" "$APP/$item"; done; rm -rf "${STAGE:?}"; }
  NEW="$(cd "$STAGE" && ls -A)"
  for item in $NEW; do
    rm -rf "${APP:?}/${item:?}.old"
    if [ -e "$APP/$item" ]; then mv "$APP/$item" "$APP/$item.old" || { swap_back; die "could not set $item aside; the previous files are back in place"; }; fi
    MOVED="$MOVED $item"
    mv "$STAGE/$item" "$APP/$item" || { swap_back; die "could not install $item; the previous files are back in place"; }
  done
  for item in $MOVED; do rm -rf "${APP:?}/${item:?}.old"; done
  # what the version before had and this one no longer has (an app that left the suite) goes
  if [ -f FILES ]; then
    while IFS= read -r item; do
      [ -n "$item" ] || continue
      case "$KEEP" in *" $item "*) continue;; esac
      case "$item" in */*|.|..) continue;; esac
      case " $(echo $NEW) " in *" $item "*) ;; *) rm -rf "${APP:?}/${item:?}";; esac
    done < FILES
  fi
  printf '%s\n' $NEW > FILES
  rm -rf "${STAGE:?}"
  echo "$R" > COMMIT
  # run by hand as root in a folder the service's user owns: the new files are that user's too
  if [ "$(id -u)" = 0 ]; then
    OWNER="$(stat -c '%U:%G' "$APP" 2>/dev/null || true)"
    case "$OWNER" in ""|root:*|UNKNOWN*) ;; *) for item in $NEW COMMIT FILES; do chown -R "$OWNER" "$APP/$item" 2>/dev/null || true; done;; esac
  fi
fi
chmod 755 install.sh update.sh 2>/dev/null || true
# the editable install's metadata follows the new pyproject.toml (its import path already points here and the packages
# are in place, so this is bookkeeping: the program runs either way)
pipi --no-deps -e . 2>/dev/null || echo "  note: the package metadata could not be refreshed (pip install -e .); ioSuite runs regardless"
# the system packages the apps of this machine ask for (their app.json: "system"), which a new version may have added:
# installed as root or through sudo when it is allowed without a password. None is needed to start, so one that
# cannot be installed is a note, never a failure
MISSING="$("$VPY" -m iosuite_shared.install missing-system 2>/dev/null || true)"
if [ -n "$MISSING" ] && command -v apt-get >/dev/null 2>&1; then
  if [ "$(id -u)" = 0 ]; then SUDO=""; elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then SUDO="sudo -n"; else SUDO="-"; fi
  if [ "$SUDO" = "-" ]; then echo "  note: the system packages $MISSING are missing; as root: apt-get install -y $MISSING"
  else
    echo "  installing the system packages $MISSING"
    # shellcheck disable=SC2086
    $SUDO apt-get install -y -qq $MISSING >/dev/null 2>&1 || { $SUDO apt-get update -qq >/dev/null 2>&1 && $SUDO apt-get install -y -qq $MISSING >/dev/null 2>&1; } \
      || echo "  note: the system packages $MISSING could not be installed; as root: apt-get install -y $MISSING"
  fi
fi

NEWV="$(version_of "$APP")"
# the outcome goes to the result file now: the restart below also ends this script when the web app started it
note "ok: updated to v$NEWV on $(date '+%Y-%m-%d %H:%M')"

say "Restarting"
# started by the web app, the program ends itself and the service manager starts it again on the new code; every other
# copy on this machine does the same when it is asked (IOSUITE_RUNNING). By hand, the services the installer wrote
# down (SERVICES) are restarted here
if [ -n "$RESULT" ]; then
  echo "  the program restarts itself (the service manager starts it again)"
elif command -v systemctl >/dev/null 2>&1 && [ -s SERVICES ]; then
  while IFS= read -r unit; do
    [ -n "$unit" ] || continue
    systemctl is-active --quiet "$unit" 2>/dev/null || continue
    if [ "$(id -u)" = 0 ]; then systemctl restart "$unit" && echo "  systemd: restarted $unit"
    elif command -v sudo >/dev/null 2>&1 && sudo -n systemctl restart "$unit" 2>/dev/null; then echo "  systemd: restarted $unit"
    else echo "  could not restart $unit from here; run: sudo systemctl restart $unit"; fi
  done < SERVICES
else
  echo "  no service found; restart ioSuite yourself (iosuite serve)"
fi
say "ioSuite is at v$NEWV ($(local_commit | cut -c1-7))"
