#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:10000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "${SCRIPT_DIR}/smoke_remote.py" "$BASE_URL"
