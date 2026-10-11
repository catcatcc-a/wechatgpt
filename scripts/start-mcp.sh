#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
if [ ! -x "$project_dir/.venv/bin/python" ]; then
  echo 'Run scripts/setup.sh first.' >&2
  exit 1
fi
exec "$project_dir/.venv/bin/python" -m wechat_local_mcp.server serve --config "$project_dir/config.toml"
