#!/usr/bin/env bash

# Copyright (c) 2026 Alex Van de Putte
# License: GPL-3.0-or-later
# Source: https://github.com/avandeputte/iosuite
# ioSuite: runs inside the LXC, driven by proxmox/ct/iosuite.sh (community-scripts framework).
# This only installs what the suite's installer needs to start; the ct script then runs install.sh inside the
# container, which fetches the program, makes its environment, asks for the apps and the database, and starts the service.

source /dev/stdin <<<"$FUNCTIONS_FILE_PATH"
color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

msg_info "Installing Dependencies"
$STD apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  ca-certificates \
  mariadb-client \
  curl
msg_ok "Installed Dependencies"

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"
