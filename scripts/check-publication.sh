#!/bin/sh
# Local hooks compare credential files without placing their values in argv.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
python="$project_dir/.venv/bin/python"
if [ ! -x "$python" ]; then python=python3; fi
set -- --all-objects
for credential in data/gadget.token data/onebot.token; do
  if [ -f "$credential" ]; then set -- "$@" --secret-file "$credential"; fi
done
exec "$python" scripts/check_public_tree.py "$@"
