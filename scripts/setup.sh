#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2; exit 1; }
uv sync --locked
mkdir -p bin
swiftc -O native/wechat_gui.swift -o bin/wechat-gui
if [ ! -f config.toml ]; then cp config.example.toml config.toml; fi
printf '%s\n' 'Installed. GUI automation is disabled by default. Run scripts/doctor.py for compatibility status.'
