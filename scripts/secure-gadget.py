#!/usr/bin/env python3
"""Prepare an authenticated copy of the installed supported Gadget app.

Default: copy/configure/sign in runtime/security without changing the live app.
--activate: swap only while WeChat is fully closed; keep the old app for rollback.
This script never quits or launches WeChat and never changes chat data.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import time

from gadget_auth import ensure_token, read_token, validate_app, write_config
from native_profile import load_profile, verify_binary_profile
from app_signing import resign_inherited_helpers, verify_helper_sandbox

ROOT = Path(__file__).resolve().parents[1]
APP = Path('/Applications/WeChat.app')
STAGE = ROOT / 'runtime/security/WeChat.app'
REPORT = ROOT / 'artifacts/security-upgrade/stage.json'
GADGET_SHA = 'fa67242fa0cee16e80a803703991e81381cd05f7823a4151515460339c942f9f'
# Same pinned dylib after the staging script's ad-hoc signature.
GADGET_SIGNED_SHA = 'd2a3453e3d011dd40fa0603638c557bd70d1d20c32f244bb2b840e6b59c0ea5e'


def run(*args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect(app):
    profile, _ = load_profile(app)
    verify_binary_profile(app / 'Contents/Resources/wechat.dylib', profile)
    gadget = app / 'Contents/Frameworks/FridaGadget.dylib'
    if gadget.exists() and sha(gadget) not in {GADGET_SHA, GADGET_SIGNED_SHA}:
        raise ValueError('Installed Gadget does not match pinned Frida 17.8.0')
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
    config = app / 'Contents/Resources/FridaGadget.config'
    return {'main_sha256': sha(app / 'Contents/MacOS/WeChat'),
            'core_sha256': sha(app / 'Contents/Resources/wechat.dylib'),
            'build': profile['build'],
            'config_sha256': sha(config) if config.exists() else None}


def prepare(source=APP):
    if STAGE.exists():
        raise ValueError('Security stage already exists; inspect it before preparing again')
    original = inspect(source)
    token = ensure_token(ROOT / 'data/gadget.token')
    STAGE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    STAGE.parent.chmod(0o700)
    run('/bin/cp', '-cRp', source, STAGE)
    gadget = STAGE / 'Contents/Frameworks/FridaGadget.dylib'
    if not gadget.exists():
        downloaded = ROOT / 'downloads/frida-gadget-17.8.0-macos-universal.dylib'
        if sha(downloaded) != GADGET_SHA:
            raise ValueError('Downloaded Gadget digest does not match the pinned release')
        run('/bin/cp', '-p', downloaded, gadget)
        run('/usr/bin/python3', ROOT / 'scripts/inject_load_dylib.py',
            STAGE / 'Contents/MacOS/WeChat', '@executable_path/../Frameworks/FridaGadget.dylib')
        (STAGE / 'Contents/Frameworks/FridaGadget.config').symlink_to('../Resources/FridaGadget.config')
        run('/usr/bin/codesign', '-f', '-s', '-', '--timestamp=none', gadget)
    write_config(STAGE, token)
    validate_app(STAGE, token)
    helpers = resign_inherited_helpers(STAGE)
    run('/usr/bin/codesign', '-f', '-s', '-', '--timestamp=none', STAGE)
    verify_helper_sandbox(STAGE)
    prepared = inspect(STAGE)
    if prepared['core_sha256'] != original['core_sha256']:
        raise ValueError('Core library changed while preparing the app copy')
    REPORT.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    REPORT.write_text(json.dumps({'original': original, 'prepared': prepared,
                                 'prepared_at': time.time(), 'activated': False,
                                 'resigned_inherited_helpers': helpers}, indent=2) + '\n')
    print('Authenticated app copy prepared and signature verified. Live app unchanged.')


def activate():
    report = json.loads(REPORT.read_text())
    if report.get('activated'):
        raise ValueError('This prepared upgrade has already been activated')
    if subprocess.run(['/usr/bin/pgrep', '-x', 'WeChat'], capture_output=True).returncode == 0:
        raise ValueError('Quit WeChat during an idle maintenance window before activation')
    if inspect(APP) != report['original'] or inspect(STAGE) != report['prepared']:
        raise ValueError('Application changed since preparation; refusing to replace it')
    validate_app(STAGE, read_token(ROOT / 'data/gadget.token'))
    # Older stages can pass codesign while their media helpers crash at startup.
    verify_helper_sandbox(STAGE)
    backup = ROOT / 'backups' / ('security-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700)
    candidate = APP.parent / '.WeChat-mcp-security.app'
    if candidate.exists():
        raise ValueError('Existing installation candidate requires review')
    run('/bin/cp', '-cRp', STAGE, candidate)
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', candidate)
    verify_helper_sandbox(candidate)
    validate_app(candidate, read_token(ROOT / 'data/gadget.token'))
    # Recheck immediately before the swap; never rename a running application.
    if subprocess.run(['/usr/bin/pgrep', '-x', 'WeChat'], capture_output=True).returncode == 0:
        raise ValueError('WeChat restarted; installation cancelled')
    original = backup / 'WeChat.app'
    os.rename(APP, original)
    try:
        os.rename(candidate, APP)
    except BaseException:
        os.rename(original, APP)
        raise
    report.update(activated=True, backup_app=str(original), activated_at=time.time())
    REPORT.write_text(json.dumps(report, indent=2) + '\n')
    print('Authenticated app installed; original app preserved. Launch WeChat, then install-services.py.')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--source', type=Path, default=APP, help='Supported Gadget app copy to prepare; never installed automatically')
    args = parser.parse_args()
    activate() if args.activate else prepare(args.source)


if __name__ == '__main__':
    main()
