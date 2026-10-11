#!/usr/bin/env python3
"""Install/update the background runtime in macOS Application Support.

Source and backups remain in Desktop/Program. launchd cannot open Desktop log
files under macOS privacy rules, so service files use the standard runtime path.
Does not launch, quit, or otherwise operate the WeChat UI.
"""
import json
import os
from pathlib import Path
import plistlib
import shutil
import sqlite3
import subprocess
import time
import secrets
from gadget_auth import read_token, validate_app
from native_profile import load_profile, verify_binary_profile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path.home() / "Library/Application Support/WeChatLocalMCP"
AGENTS = Path.home() / "Library/LaunchAgents"
APP = Path('/Applications/WeChat.app')


def check_profile():
    profile, _ = load_profile(APP, ROOT)
    verify_binary_profile(APP / 'Contents/Resources/wechat.dylib', profile)


def bootstrap_agent(path):
    # bootout can return before launchd finishes releasing the old service.
    # Retry its transient bootstrap EIO without stopping a running WeChat.
    for delay in (0, 0.2, 0.5, 1, 2):
        if delay:
            time.sleep(delay)
        result = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)],
                                capture_output=True)
        if result.returncode == 0:
            return
        if result.returncode != 5:
            break
    result.check_returncode()


def main():
    os.umask(0o077)
    # Fail before stopping working services if the app/client credentials differ.
    gadget_token = read_token(ROOT / 'data/gadget.token')
    validate_app(APP, gadget_token)
    check_profile()
    for path in (RUNTIME / 'data/gadget.token', RUNTIME / 'data/onebot.token'):
        if path.is_symlink():
            raise RuntimeError('Refusing a symlink at a runtime credential destination')
    # An existing runtime venv is preserved; refuse an incomplete upgrade before
    # stopping any services. setup.sh installs the pinned Frida dependency.
    for python in (ROOT / '.venv/bin/python', RUNTIME / '.venv/bin/python'):
        if python.exists():
            check = subprocess.run([str(python), '-c', 'import frida; assert frida.__version__ == "17.8.0"'], capture_output=True)
            if check.returncode:
                raise RuntimeError(f'Install frida==17.8.0 into {python} before deploying native sending')
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    RUNTIME.chmod(0o700)
    AGENTS.mkdir(parents=True, exist_ok=True)
    for name in ("onebot", "webhook"):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/local.wechat-mcp.{name}"], capture_output=True)
    # Upgrade only service-owned files; preserve the live cache and token.
    for relative in ("src/wechat_local_mcp", "scripts", "native"):
        shutil.copytree(ROOT / relative, RUNTIME / relative, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    if not (RUNTIME / ".venv").exists():
        subprocess.run(["/bin/cp", "-cRp", str(ROOT / ".venv"), str(RUNTIME / ".venv")], check=True)
    # Replace the editable import path: no Desktop access needed by launchd.
    for file in (RUNTIME / ".venv/lib").glob("python*/site-packages/*wechat*.pth"):
        file.write_text(str(RUNTIME / "src") + "\n")
    for relative in ("vendor/wechat_chatter/onebot/onebot", "vendor/wechat_chatter/onebot/script.js",
                     "vendor/wechat_chatter/wechat_version/4_1_11_53_mac.json"):
        destination = RUNTIME / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    data = RUNTIME / "data"
    data.mkdir(exist_ok=True, mode=0o700)
    data.chmod(0o700)
    (data / "logs").mkdir(exist_ok=True, mode=0o700)
    (data / "logs").chmod(0o700)
    gadget_destination = data / 'gadget.token'
    gadget_destination.touch(mode=0o600, exist_ok=True)
    gadget_destination.chmod(0o600)
    gadget_destination.write_text(gadget_token + '\n')
    if not (data / "onebot.token").exists():
        source_token = ROOT / "data/onebot.token"
        if source_token.is_file():
            shutil.copy2(source_token, data / "onebot.token")
        else:
            token = secrets.token_urlsafe(32) + secrets.token_urlsafe(32)
            (data / "onebot.token").write_text(token + "\n")
    (data / "onebot.token").chmod(0o600)
    if not (data / "messages.sqlite3").exists() and (ROOT / "data/messages.sqlite3").is_file():
        with sqlite3.connect(ROOT / "data/messages.sqlite3") as source, sqlite3.connect(data / "messages.sqlite3") as target:
            source.backup(target)
    config = f'''backend = "onebot"
data_dir = {json.dumps(str(data))}
[onebot]
url = "http://127.0.0.1:58080"
token_file = {json.dumps(str(data / "onebot.token"))}
timeout = 20
[native]
enabled = true
command = [{json.dumps(str(RUNTIME / '.venv/bin/python'))}, {json.dumps(str(RUNTIME / 'scripts/native-send.py'))}]
[webhook]
host = "127.0.0.1"
port = 36060
[gui]
enabled = false
'''
    (ROOT / "config.toml").write_text(config)
    (RUNTIME / "config.toml").write_text(config)
    for name, argv in {
        "webhook": [str(RUNTIME / ".venv/bin/python"), "-m", "wechat_local_mcp.server", "webhook", "--config", str(RUNTIME / "config.toml")],
        "onebot": [str(RUNTIME / ".venv/bin/python"), str(RUNTIME / "scripts/start-onebot.py"), "--start"],
    }.items():
        log = data / "logs" / f"{name}.log"
        log.touch(mode=0o600, exist_ok=True)
        log.chmod(0o600)
        plist = {
            "Label": f"local.wechat-mcp.{name}", "ProgramArguments": argv,
            "WorkingDirectory": str(RUNTIME), "RunAtLoad": True,
            "KeepAlive": True, "ThrottleInterval": 15, "ProcessType": "Background",
            "StandardOutPath": str(log), "StandardErrorPath": str(log),
            "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
                                     "PYTHONPATH": str(RUNTIME / "src"), "PYTHONUNBUFFERED": "1"},
        }
        path = AGENTS / f"local.wechat-mcp.{name}.plist"
        path.write_bytes(plistlib.dumps(plist))
        bootstrap_agent(path)
    time.sleep(2)
    print(json.dumps({"runtime": str(RUNTIME), "services": ["local.wechat-mcp.webhook", "local.wechat-mcp.onebot"]}))


if __name__ == "__main__":
    main()
