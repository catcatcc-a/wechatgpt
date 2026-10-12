"""Keep nested helper signing consistent with an ad-hoc, unsandboxed host.

Some official helpers inherit the parent's App Sandbox. After the host loses
that entitlement during ad-hoc signing, those helpers abort in libsecinit.
Only inherited helpers and enclosing signed bundles are re-signed; independent
sandboxed extensions and the WeChat core library are left unchanged.
"""
from pathlib import Path
import plistlib
import subprocess


def read_entitlements(bundle: Path) -> dict:
    result = subprocess.run(['/usr/bin/codesign', '-d', '--entitlements', ':-', str(bundle)],
                            check=True, capture_output=True)
    return plistlib.loads(result.stdout) if result.stdout.strip() else {}


def inherited_helpers(app: Path) -> list[Path]:
    helpers = []
    for info_path in app.rglob('Info.plist'):
        if info_path.is_symlink() or info_path.parent.name != 'Contents':
            continue
        bundle = info_path.parent.parent
        if bundle == app or bundle.suffix not in {'.app', '.xpc', '.appex'}:
            continue
        entitlements = read_entitlements(bundle)
        if entitlements.get('com.apple.security.inherit') is not True:
            continue
        # An independent sandboxed ancestor still supplies a valid sandbox.
        for parent in bundle.parents:
            if parent == app:
                break
            if parent.suffix in {'.app', '.xpc', '.appex'}:
                parent_entitlements = read_entitlements(parent)
                if (parent_entitlements.get('com.apple.security.app-sandbox') is True
                        and parent_entitlements.get('com.apple.security.inherit') is not True):
                    break
        else:
            continue
        if parent == app:
            helpers.append(bundle)
    return sorted(helpers)


def verify_helper_sandbox(app: Path) -> None:
    """A valid code signature alone does not prove that helpers can start."""
    if read_entitlements(app).get('com.apple.security.app-sandbox') is True:
        return
    helpers = inherited_helpers(app)
    if helpers:
        names = ', '.join(str(path.relative_to(app)) for path in helpers)
        raise ValueError('Unsandboxed host has sandbox-inheriting helpers: ' + names)


def resign_inherited_helpers(app: Path) -> list[str]:
    targets = set()
    helpers = inherited_helpers(app)
    for bundle in helpers:
        targets.add(bundle)
        for parent in bundle.parents:
            if parent == app:
                break
            if parent.suffix in {'.app', '.framework', '.xpc', '.appex', '.bundle'}:
                targets.add(parent)
    for bundle in sorted(targets, key=lambda p: len(p.parts), reverse=True):
        subprocess.run(['/usr/bin/codesign', '-f', '-s', '-', '--timestamp=none', str(bundle)],
                       check=True, capture_output=True)
    return [str(bundle.relative_to(app)) for bundle in helpers]
