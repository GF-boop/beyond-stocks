#!/usr/bin/env bash
# Alias for the canonical full replication pipeline.
set -euo pipefail
exec bash "$(dirname "$0")/rebuild_all.sh" "$@"
