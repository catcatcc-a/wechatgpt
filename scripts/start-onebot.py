#!/usr/bin/env python3
"""Check compatibility before launching the prepared OneBot binary.

The default is check-only. --start explicitly launches the engine, after checking
the exact supported app build. This script never modifies or restarts WeChat.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import sys
from gadget_auth import read_token, validate_app
from native_profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {("4.1.11", "269109"): "4_1_11_53_mac.json"}


def preflight(app: Path, root: Path = ROOT) -> dict:
    try:
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        return {"can_launch": False, "reason": f"Cannot inspect WeChat: {exc}"}
    version = str(info.get("CFBundleShortVersionString", ""))
    build = str(info.get("CFBundleVersion", ""))
    family = ".".join(version.split(".")[:3])
    matched = SUPPORTED.get((family, build))
    binary = root / "vendor/wechat_chatter/onebot/onebot"
    config = root / "vendor/wechat_chatter/wechat_version" / (matched or "unsupported.json")
    receive_only = False
    if not matched:
        try:
            profile, candidate = load_profile(app, root)
            if profile.get('receive_only') and (root / 'native/wechat_receive.js').is_file():
                config, matched, receive_only = candidate, candidate.name, True
        except (OSError, ValueError):
            pass
    return {"wechat_version": version, "wechat_build": build,
            "version_matches": bool(matched), "binary_present": binary.is_file(),
            "config_present": config.is_file(),
            "can_launch": bool(matched and binary.is_file() and config.is_file()),
            "version_config": str(config) if matched else None,
            "receive_only": receive_only,
            "runtime_verified": False,
            "reason": "Static preflight only; Gadget must already be installed and running" if matched
                      else "Installed WeChat build is unsupported; no attach attempted"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", action="store_true", help="Explicitly start the engine after successful preflight")
    parser.add_argument("--app", type=Path, default=Path("/Applications/WeChat.app"))
    parser.add_argument("--token-file", type=Path, default=ROOT / "data/onebot.token")
    args = parser.parse_args()
    result = preflight(args.app)
    print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr if args.start else sys.stdout)
    if not args.start:
        return 0
    if args.app.resolve() != Path("/Applications/WeChat.app"):
        print("--start only supports the installed /Applications/WeChat.app; mounted candidates are inspection-only.", file=sys.stderr)
        return 2
    if not result["can_launch"]:
        return 2
    try:
        validate_app(args.app, read_token(ROOT / 'data/gadget.token'))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    token = os.environ.get("WECHAT_ONEBOT_TOKEN", "")
    if not token:
        try:
            token = args.token_file.read_text().strip()
        except OSError:
            print("A private OneBot token file or WECHAT_ONEBOT_TOKEN is required.", file=sys.stderr)
            return 2
    if not token:
        print("OneBot token must not be empty.", file=sys.stderr)
        return 2
    directory = ROOT / "vendor/wechat_chatter/onebot"
    environment = dict(os.environ, WECHAT_ONEBOT_TOKEN=token,
                       WECHAT_GADGET_TOKEN_FILE=str(ROOT / 'data/gadget.token'))
    os.chdir(directory)
    extra = ['-receive_only', f'-hook_script={ROOT / "native/wechat_receive.js"}'] if result['receive_only'] else []
    os.execve(str(directory / "onebot"), [str(directory / "onebot"), "-type=gadget",
        "-gadget_addr=127.0.0.1:27042", f"-wechat_conf={result['version_config']}",
        "-receive_host=127.0.0.1:58080", "-send_url=http://127.0.0.1:36060/onebot", "-conn_type=http", *extra], environment)


if __name__ == "__main__":
    raise SystemExit(main())
