"""Keep nested helper signing consistent with an ad-hoc, unsandboxed host.

Some official helpers inherit the parent's App Sandbox. After the host loses
that entitlement during ad-hoc signing, those helpers abort in libsecinit.
Only inherited helpers and enclosing signed bundles are re-signed; independent
sandboxed extensions and the WeChat core library are left unchanged.
"""
from pathlib import Path
import plistlib
import subprocess


def resign_inherited_helpers(app: Path) -> list[str]:
    targets = set()
    helpers = []
    for info_path in app.rglob('Info.plist'):
        if info_path.is_symlink() or info_path.parent.name != 'Contents':
            continue
        bundle = info_path.parent.parent
        if bundle == app or bundle.suffix not in {'.app', '.xpc', '.appex'}:
            continue
        result = subprocess.run(['/usr/bin/codesign', '-d', '--entitlements', ':-', str(bundle)],
                                check=True, capture_output=True)
        entitlements = plistlib.loads(result.stdout) if result.stdout.strip() else {}
        if entitlements.get('com.apple.security.inherit') is not True:
            continue
        helpers.append(str(bundle.relative_to(app)))
        targets.add(bundle)
        for parent in bundle.parents:
            if parent == app:
                break
            if parent.suffix in {'.app', '.framework', '.xpc', '.appex', '.bundle'}:
                targets.add(parent)
    for bundle in sorted(targets, key=lambda p: len(p.parts), reverse=True):
        subprocess.run(['/usr/bin/codesign', '-f', '-s', '-', '--timestamp=none', str(bundle)],
                       check=True, capture_output=True)
    return sorted(helpers)
