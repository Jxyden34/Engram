#!/usr/bin/env bash
set -euo pipefail
# Moved from PR #85. Bootstrap a released, prebuilt v3 installer; never a draft branch.
if [ "$(id -u)" -ne 0 ]; then echo 'Run this installer with sudo.' >&2; exit 1; fi
if [ ! -r /dev/tty ]; then echo 'Use an interactive terminal.' >&2; exit 1; fi
# shellcheck source=/dev/null
. /etc/os-release
: "${ID:?}" "${VERSION_CODENAME:?}" "${VERSION_ID:?}"
case "$ID" in ubuntu|debian) ;; *) echo 'Supported hosts: Ubuntu or Debian.' >&2; exit 1;; esac
if { [ "$ID" = ubuntu ] && [ "${VERSION_ID%%.*}" -lt 22 ]; } || { [ "$ID" = debian ] && [ "${VERSION_ID%%.*}" -lt 12 ]; }; then
  echo 'Ubuntu 22.04+ or Debian 12+ is required for the compiled Linux installer.' >&2; exit 1
fi
case "$(uname -m)" in x86_64) architecture=amd64;; aarch64|arm64) architecture=arm64;; *) echo 'Unsupported architecture.' >&2; exit 1;; esac
version="${ENGRAM_INSTALL_VERSION:-}"
if [ -z "$version" ]; then
  version=$(curl -fsSL https://api.github.com/repos/Jxyden34/Engram/releases/latest | sed -n 's/.*"tag_name": "\([^"]*\)".*/\1/p')
fi
if [[ ! "$version" =~ ^v3\.[0-9]+\.[0-9]+([.-][a-zA-Z0-9.-]+)?$ ]]; then
  echo 'No published v3 installer release is available. Stable v2.8 is unchanged.' >&2; exit 1
fi
asset="engram-$version-linux-$architecture.tar.gz"
stage=$(mktemp -d /tmp/engram-installer.XXXXXXXX)
trap 'rm -rf -- "$stage"' EXIT
base="https://github.com/Jxyden34/Engram/releases/download/$version"
curl -fsSL "$base/$asset" -o "$stage/$asset"
curl -fsSL "$base/$asset.sha256" -o "$stage/checksum"
expected=$(cut -d ' ' -f 1 "$stage/checksum")
[[ "$expected" =~ ^[a-f0-9]{64}$ ]] || { echo 'Invalid checksum file.' >&2; exit 1; }
actual=$(sha256sum "$stage/$asset" | cut -d ' ' -f 1)
[ "$expected" = "$actual" ] || { echo 'Installer checksum mismatch.' >&2; exit 1; }
printf '\nEngram host setup installs prerequisites, then opens the setup wizard. Continue? [y/N] '
read -r consent </dev/tty
case "$consent" in y|Y|yes|YES) ;; *) exit 0;; esac
apt-get update
apt-get install -y ca-certificates curl tar
if ! command -v docker >/dev/null; then
  for package in docker.io podman-docker containerd runc; do
    if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
      echo "Existing $package detected. Configure Docker and Compose before rerunning." >&2; exit 1
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
docker compose version >/dev/null
systemctl start docker
mkdir "$stage/unpacked"
tar --same-permissions --no-same-owner -xzf "$stage/$asset" -C "$stage/unpacked"
"$stage/unpacked/EngramInstaller/EngramInstaller" </dev/tty
