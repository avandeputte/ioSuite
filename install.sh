#!/usr/bin/env bash
# ioSuite on this server: install it, and run this again at any time to change the apps it runs.
#
#   curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --add iotask,ionote
#
# The first time, on a server without ioSuite: fetches the program into its folder (/opt/iosuite as root, else
# ~/iosuite; --into DIR for another), makes its Python environment, then asks what a new machine is asked: the
# database server, the apps, the first admin. Every other time it shows the apps that run here, to tick and untick.
# ioSuite is one program: every app's code is in the folder, and the machine's file (config.env) says which of them
# this machine runs.
#
#   --into DIR              the program folder (IOSUITE_BASE)
#   --fetch                 only fetch the program and make its Python environment; set nothing up
#   --apps APP,APP | all    exactly these apps      --add APP,APP    run these too      --remove APP,APP   stop running them
#   --list                  what this machine runs
#   --copy NAME --apps iopix   a second copy of the program on this machine, with ports of its own (--remove-copy NAME)
#   --db HOST[:PORT]  --db-name NAME  --db-user USER      the MariaDB server, the Shared ioSuite database, the suite's login
#   --db-admin USER         a MariaDB administrator who creates the databases and the login
#   --mariadb               install MariaDB on this machine first when it has no database server
#   --admin NAME            the first admin         --address URL    the suite's address (https://home.example.com)
#   --host ADDR  --port N  --sync-port N  --mcp-port N    where it listens (every address; 80, 8443, 8444)
#   --set APP.NAME=VALUE    a setting to store (iopix.PHOTOS_ROOT=/srv/photos); repeatable
#   --extras iopix-ai,iorecipe-ai   optional sets of Python packages
#   --user USER  --service | --no-service  --yes          the service's account; a systemd service or not; no questions
#
# Passwords come in through the environment, never on a command line a process list shows:
#   IOSUITE_DB_PASSWORD (the suite's login), DB_ADMIN_PASSWORD (the MariaDB administrator), ADMIN_PASSWORD (the first admin).
# An install without questions, on a blank Debian or Ubuntu server:
#   ... | ADMIN_PASSWORD=… bash -s -- --yes --mariadb --admin alex
set -euo pipefail
REPO="${IOSUITE_REPO:-avandeputte/iosuite}"
BRANCH="${IOSUITE_BRANCH:-main}"
say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

main() {
  local base="${IOSUITE_BASE:-}" rest=() fetch=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --into) base="$2"; shift 2;;
      --fetch) fetch=1; shift;;
      -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]:-/dev/null}" 2>/dev/null | sed 's/^# \{0,1\}//' || true
                 [ -n "${BASH_SOURCE[0]:-}" ] || echo "see the top of https://github.com/$REPO/blob/$BRANCH/install.sh"; exit 0;;
      *) rest+=("$1"); shift;;
    esac
  done
  if [ -z "$base" ]; then if [ "$(id -u)" = 0 ]; then base=/opt/iosuite; else base="$HOME/iosuite"; fi; fi

  # piped from curl, the keyboard is not on standard input: the questions read the terminal
  if [ ! -t 0 ] && [ -t 1 ] && (exec </dev/tty) 2>/dev/null; then exec </dev/tty; fi

  # ioSuite is here already: the program itself shows the list and makes the changes
  if [ -x "$base/.venv/bin/iosuite" ] && [ -f "$base/pyproject.toml" ]; then
    if [ "$fetch" = 1 ]; then say "ioSuite is in $base already"; exit 0; fi
    exec "$base/.venv/bin/iosuite" install ${rest[@]+"${rest[@]}"}
  fi

  # ---- a new server: Python, the program, its environment
  local apt=0; command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ] && apt=1
  pyok() { command -v python3 >/dev/null 2>&1 && python3 -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; }
  if ! pyok; then
    say "Installing Python"
    if [ "$apt" = 1 ]; then
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 python3-venv python3-pip ca-certificates >/dev/null
    elif command -v dnf >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then dnf install -y -q python3 python3-pip
    fi
    pyok || die "ioSuite needs Python 3.10 or newer with venv (Debian, Ubuntu: apt install python3 python3-venv), then run this again"
  fi

  say "Fetching ioSuite from github.com/$REPO"
  local tmp; tmp="$(mktemp -d)"; trap "rm -rf '$tmp'" EXIT
  local sha
  sha="$(python3 - "$REPO" "$BRANCH" <<'PYEOF'
import re, sys, urllib.request
repo, ref = sys.argv[1:3]
if re.fullmatch(r"[0-9a-f]{40}", ref):
    print(ref); sys.exit()
req = urllib.request.Request(f"https://github.com/{repo}.git/info/refs?service=git-upload-pack", headers={"User-Agent": "iosuite-install"})
refs = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
m = re.search(r"([0-9a-f]{40}) refs/(?:heads|tags)/" + re.escape(ref) + r"(?=[\x00\n])", refs)
print(m.group(1) if m else "")
PYEOF
)" || sha=""
  [ -n "$sha" ] || die "could not find the branch $BRANCH of github.com/$REPO (is this server online?)"
  python3 - "https://github.com/$REPO/archive/$sha.tar.gz" "$tmp/src.tgz" <<'PYEOF' || die "the download failed"
import sys, urllib.request
req = urllib.request.Request(sys.argv[1], headers={"User-Agent": "iosuite-install"})
with urllib.request.urlopen(req, timeout=120) as r, open(sys.argv[2], "wb") as f:
    while True:
        b = r.read(1 << 20)
        if not b:
            break
        f.write(b)
PYEOF
  mkdir "$tmp/src" && tar xzf "$tmp/src.tgz" -C "$tmp/src"
  local top; top="$(ls -d "$tmp"/src/*/ | head -1)"; top="${top%/}"
  [ -f "$top/pyproject.toml" ] && [ -d "$top/iosuite_shared" ] || die "github.com/$REPO does not look like ioSuite (no pyproject.toml or no iosuite_shared/)"
  mkdir -p "$base"
  # the code only: a machine's file, data or environment that is here already (an install that stopped half-way) stays
  local item files=""
  for item in $(cd "$top" && ls -A); do
    case "$item" in config.env|data|copies|.venv|.github|.gitignore|.dockerignore|docs|devices|proxmox) continue;; esac
    rm -rf "${base:?}/${item:?}"; cp -R "$top/$item" "$base/$item"; files="$files$item
"
  done
  printf '%s' "$files" > "$base/FILES"
  echo "$sha" > "$base/COMMIT"
  chmod 755 "$base/install.sh" "$base/update.sh" 2>/dev/null || true

  say "Making the Python environment in $base/.venv"
  [ -x "$base/.venv/bin/python" ] || python3 -m venv "$base/.venv"
  "$base/.venv/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip >/dev/null 2>&1 || true
  # the suite's own packages now; each app's are installed once the apps of this machine are chosen
  "$base/.venv/bin/python" -m pip install -q --disable-pip-version-check -e "$base" || die "installing the Python packages failed (see above)"
  [ "$(id -u)" != 0 ] || ln -sf "$base/.venv/bin/iosuite" /usr/local/bin/iosuite 2>/dev/null || true

  if [ "$fetch" = 1 ]; then
    say "ioSuite is in $base; nothing is set up yet"
    echo "Set this machine up with: $base/.venv/bin/iosuite install"
    exit 0
  fi
  IOSUITE_REPO="$REPO" exec "$base/.venv/bin/iosuite" install ${rest[@]+"${rest[@]}"}
}
main "$@"
