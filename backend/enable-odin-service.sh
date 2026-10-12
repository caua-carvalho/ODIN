#!/usr/bin/env bash
#
# DEPRECATED. This script used to write a systemd unit that called a
# non-existent `/usr/bin/odin serve` binary, so it never worked.
#
# Installing Odin as a service is now handled by scripts/install-service.sh,
# which renders deploy/odin.service with the correct paths. See
# README.deploy.md.
#
# This shim forwards to it so existing muscle memory keeps working.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[odin] enable-odin-service.sh foi movido para scripts/install-service.sh" >&2
exec "$ROOT_DIR/scripts/install-service.sh" "$@"
