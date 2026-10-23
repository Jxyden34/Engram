#!/usr/bin/env bash
set -euo pipefail
# This entry point is intended for a fresh Ubuntu/Debian host.
if [ "$(id -u)" -ne 0 ]; then echo 'Run this command with sudo.' >&2; exit 1; fi
if [ ! -r /dev/tty ]; then echo 'Run from an interactive terminal.' >&2; exit 1; fi
# shellcheck source=/dev/null
. /etc/os-release
: "${ID:?}" "${VERSION_CODENAME:?}"
case "$ID" in ubuntu|debian) ;; *) echo 'Supported hosts: Ubuntu or Debian.' >&2; exit 1;; esac
printf '\nEngram host setup\nThis installs prerequisites and opens the deployment wizard.\nContinue? [y/N] '
read -r consent </dev/tty
case "$consent" in y|Y|yes|YES) ;; *) exit 0;; esac
apt-get update
apt-get install -y ca-certificates curl python3 tar
if ! command -v docker >/dev/null; then
  # Refuse to replace another container runtime or distribution Docker installation.
  for package in docker.io podman-docker containerd runc; do
    if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
      echo "Existing $package detected. Configure Docker Engine and Compose before rerunning." >&2; exit 1
    fi
  done
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  codename="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
  printf 'Types: deb\nURIs: https://download.docker.com/linux/%s\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' "$ID" "$codename" "$(dpkg --print-architecture)" > /etc/apt/sources.list.d/docker.sources
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version >/dev/null || { echo 'Docker Compose plugin is required; install it and rerun.' >&2; exit 1; }
systemctl start docker
stage="$(mktemp -d /tmp/engram-installer.XXXXXXXX)"
trap 'rm -rf -- "$stage"' EXIT
ref="${ENGRAM_INSTALL_REF:-codex/v3-commercial-licensing}"
curl -fsSL "https://codeload.github.com/Jxyden34/Engram/tar.gz/$ref" -o "$stage/source.tar.gz"
mkdir "$stage/source"
tar -xzf "$stage/source.tar.gz" -C "$stage/source" --strip-components=1 --no-same-owner --no-same-permissions
python3 "$stage/source/install.py" </dev/tty
