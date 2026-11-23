#!/usr/bin/env bash
# ioSuite LXC for Proxmox VE, in the community-scripts (ProxmoxVE) framework layout: this is the ct/ script;
# proxmox/install/iosuite-install.sh runs inside the container.
#
# After the framework's own questions (resources, network) it asks two things only the host knows: a folder of photos
# on this host to hand to ioPix (bind-mounted; empty: none), and the folder with digiKam's digikam4.db (empty: none).
# It creates the container, then runs the suite's own installer inside it (install.sh), on this terminal: that asks what
# a new machine is asked (the apps, the database server, the first admin) and starts the service.
#
# Until the scripts are merged upstream, the framework is pointed at this repository for the install script
# (COMMUNITY_SCRIPTS_URL below; the core engine still comes from community-scripts). Run on the Proxmox host as root:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite2/main/proxmox/ct/iosuite.sh)"
#
# Without questions: IOSUITE_INSTALL="--yes --mariadb --admin alex --apps iostart,iocalendar" holds the installer's
# options (see the top of install.sh), IOSUITE_PHOTOS=/mnt/photos and IOSUITE_DIGIKAM=/mnt/digikamDB the two folders
# ("" for none), and the passwords come from ADMIN_PASSWORD, IOSUITE_DB_PASSWORD and DB_ADMIN_PASSWORD in the
# environment: they go into the container in a file only root reads, removed once read, never as arguments.
export COMMUNITY_SCRIPTS_URL="${COMMUNITY_SCRIPTS_URL:-https://raw.githubusercontent.com/avandeputte/iosuite2/main/proxmox}"
_cs_boot="${COMMUNITY_SCRIPTS_CORE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../../core}/core/build.func"
source "$_cs_boot" 2>/dev/null || source <(curl -fsSL "${COMMUNITY_SCRIPTS_CORE_URL:-https://raw.githubusercontent.com/community-scripts/core/main}/core/build.func")
# Copyright (c) 2026 Alex Van de Putte
# License: GPL-3.0-or-later
# Source: https://github.com/avandeputte/iosuite2

APP="iosuite"
var_tags="${var_tags:-family;self-hosted}"
var_cpu="${var_cpu:-2}"
var_ram="${var_ram:-2048}"
var_disk="${var_disk:-12}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_arm64="${var_arm64:-yes}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

REPO="${IOSUITE_REPO:-avandeputte/iosuite2}"
BRANCH="${IOSUITE_BRANCH:-main}"

# ---- what only this host knows (whiptail; IOSUITE_PHOTOS and IOSUITE_DIGIKAM in the environment skip the questions)
ask_host_folders() {
  local bt="ioSuite"
  if [[ -z "${IOSUITE_PHOTOS+x}" ]]; then
    IOSUITE_PHOTOS=$(whiptail --backtitle "$bt" --inputbox "ioPix: a folder on this Proxmox host with your photos, bind-mounted into the container (empty: none, or you do not install ioPix)" 11 76 "" 3>&1 1>&2 2>&3) || exit 1
  fi
  [[ -z "$IOSUITE_PHOTOS" || -d "$IOSUITE_PHOTOS" ]] || { msg_error "Folder not found on this host: $IOSUITE_PHOTOS"; exit 1; }
  if [[ -n "$IOSUITE_PHOTOS" && -z "${IOSUITE_DIGIKAM+x}" ]]; then
    IOSUITE_DIGIKAM=$(whiptail --backtitle "$bt" --inputbox "ioPix: the folder on this host with digiKam's digikam4.db (empty: no digiKam, or its database is on a MySQL server: set that in Settings afterwards)" 11 76 "" 3>&1 1>&2 2>&3) || exit 1
  fi
  IOSUITE_DIGIKAM="${IOSUITE_DIGIKAM:-}"
  [[ -z "$IOSUITE_DIGIKAM" || -f "$IOSUITE_DIGIKAM/digikam4.db" ]] || { msg_error "digikam4.db not found in $IOSUITE_DIGIKAM"; exit 1; }
  if [[ -n "$IOSUITE_PHOTOS" ]]; then  # ioPix reads a whole library: room for its thumbnails and models
    (( var_cpu < 4 )) && var_cpu=4; (( var_ram < 4096 )) && var_ram=4096; (( var_disk < 24 )) && var_disk=24
  fi
}

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  if [[ ! -f /opt/iosuite/update.sh ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi
  msg_info "Updating ${APP}"
  # the one program and every copy of it on this machine: latest code, same settings and data, the services restarted
  if sh /opt/iosuite/update.sh; then msg_ok "Updated successfully!"; else msg_error "update.sh failed; see the lines above"; exit 1; fi
  exit
}

if command -v pveversion >/dev/null 2>&1; then ask_host_folders; fi  # on the Proxmox host; inside the container `update` needs no answers
start
build_container
description

SET=""
if [[ -n "$IOSUITE_PHOTOS" ]]; then
  msg_info "Handing the photos to the container"
  pct set "$CTID" -mp0 "$IOSUITE_PHOTOS,mp=/mnt/photos" >/dev/null
  SET+=" --set iopix.PHOTOS_ROOT=/mnt/photos"
  if [[ -n "$IOSUITE_DIGIKAM" ]]; then
    pct set "$CTID" -mp1 "$IOSUITE_DIGIKAM,mp=/mnt/digikamDB" >/dev/null
    SET+=" --set iopix.DIGIKAM_DB_DIR=/mnt/digikamDB --set iopix.DIGIKAM_DB_TYPE=sqlite"
  fi
  pct reboot "$CTID" >/dev/null  # the mounts appear at the next start
  for _ in $(seq 1 30); do pct exec "$CTID" -- test -d /mnt/photos 2>/dev/null && break; sleep 1; done
  msg_ok "Photos at /mnt/photos in the container"
fi

# the passwords given in the environment go in as a root-only file (pushed, read into the installer's environment, removed)
SECRETS=""
for v in ADMIN_PASSWORD IOSUITE_DB_PASSWORD DB_ADMIN_PASSWORD; do
  [[ -n "${!v:-}" ]] && SECRETS+="$v=$(printf '%q' "${!v}")"$'\n'
done
SECF="$(mktemp)"; chmod 600 "$SECF"; printf '%s' "$SECRETS" > "$SECF"
pct push "$CTID" "$SECF" /root/iosuite-install.env --perms 0600 --user 0 --group 0
rm -f "$SECF"

INSTALL="set -a; . /root/iosuite-install.env; set +a; rm -f /root/iosuite-install.env; export IOSUITE_REPO='$REPO' IOSUITE_BRANCH='$BRANCH'; curl -fsSL 'https://raw.githubusercontent.com/$REPO/$BRANCH/install.sh' -o /root/install.sh && bash /root/install.sh --service $SET ${IOSUITE_INSTALL:-}"
echo -e "\n${INFO}${YW}The suite's installer, inside the container:${CL}"
# lxc-attach keeps this terminal, so the installer asks its questions here; pct exec has none
if ! lxc-attach -n "$CTID" -- bash -c "$INSTALL"; then
  msg_error "The installer stopped inside the container. Fix the cause (often: the MariaDB server refuses the container's address), then run it again there:"
  echo "  pct enter $CTID"
  echo "  bash /root/install.sh --service$SET"
  exit 1
fi
msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Open it at:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}/${CL}"
echo -e "${INFO}${YW}Add or remove apps later: pct enter $CTID, then: iosuite install${CL}"
