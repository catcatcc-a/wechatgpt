#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
exec "$project_dir/.venv/bin/python" -m wechat_local_mcp.server webhook --config "${WECHAT_MCP_CONFIG:-$project_dir/config.toml}"
