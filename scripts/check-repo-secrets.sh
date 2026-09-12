#!/usr/bin/env sh
set -eu

echo "Checking tracked source tree for common secret patterns..."

if grep -RInE \
  --exclude-dir=.git \
  --exclude='.env.example' \
  --exclude='check-repo-secrets.sh' \
  'mem_live_[A-Za-z0-9_-]+|CLOUDFLARE_TUNNEL_TOKEN=ey[A-Za-z0-9._-]+|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|AKIA[0-9A-Z]{16}' \
  .; then
  echo "Potential secret detected."
  exit 1
fi

echo "No common secret patterns detected."
