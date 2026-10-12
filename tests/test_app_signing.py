"""Only helpers that inherit the removed host sandbox need signature repair."""
from pathlib import Path
import plistlib
from types import SimpleNamespace

import app_signing
import pytest


def test_inherited_helpers_and_enclosing_bundles_only(tmp_path, monkeypatch):
    app = tmp_path / 'WeChat.app'
    framework = app / 'Contents/Frameworks/Engine.framework'
    child = framework / 'Versions/A/Helpers/Worker.app'
    extension = app / 'Contents/PlugIns/Share.appex'
    for bundle in (app, child, extension):
        (bundle / 'Contents').mkdir(parents=True)
        (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps({}))
    calls = []

    def run(argv, **kwargs):
        path = Path(argv[-1])
        if '-d' in argv:
            entitlements = {'com.apple.security.app-sandbox': True}
            if path == child:
                entitlements['com.apple.security.inherit'] = True
            return SimpleNamespace(stdout=plistlib.dumps(entitlements))
        calls.append(path)
        return SimpleNamespace(stdout=b'')

    monkeypatch.setattr(app_signing.subprocess, 'run', run)
    assert app_signing.resign_inherited_helpers(app) == [str(child.relative_to(app))]
    assert calls == [child, framework]
    assert extension not in calls and app not in calls


def test_unsandboxed_host_rejects_unrepaired_player(tmp_path, monkeypatch):
    app = tmp_path / 'WeChat.app'
    player = app / 'Contents/MacOS/XPlayer.app'
    (player / 'Contents').mkdir(parents=True)
    (player / 'Contents/Info.plist').write_bytes(plistlib.dumps({}))
    entitlements = {app: {}, player: {'com.apple.security.app-sandbox': True,
                                    'com.apple.security.inherit': True}}

    def run(argv, **kwargs):
        bundle = Path(argv[-1])
        if '-d' not in argv:
            entitlements[bundle] = {}
        return SimpleNamespace(stdout=plistlib.dumps(entitlements[bundle]))

    monkeypatch.setattr(app_signing.subprocess, 'run', run)
    with pytest.raises(ValueError, match='XPlayer.app'):
        app_signing.verify_helper_sandbox(app)
    assert app_signing.resign_inherited_helpers(app) == ['Contents/MacOS/XPlayer.app']
    app_signing.verify_helper_sandbox(app)


def test_official_sandboxed_host_is_compatible(tmp_path, monkeypatch):
    monkeypatch.setattr(app_signing, 'read_entitlements',
                        lambda _: {'com.apple.security.app-sandbox': True})
    app_signing.verify_helper_sandbox(tmp_path / 'WeChat.app')


def test_independent_sandbox_and_its_inheriting_children_are_preserved(tmp_path, monkeypatch):
    app = tmp_path / 'WeChat.app'
    extension = app / 'Contents/PlugIns/Share.appex'
    child = extension / 'Contents/Helpers/Worker.app'
    for bundle in (extension, child):
        (bundle / 'Contents').mkdir(parents=True)
        (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps({}))
    values = {app: {}, extension: {'com.apple.security.app-sandbox': True},
              child: {'com.apple.security.app-sandbox': True, 'com.apple.security.inherit': True}}
    monkeypatch.setattr(app_signing, 'read_entitlements', lambda bundle: values[bundle])
    app_signing.verify_helper_sandbox(app)
    assert app_signing.resign_inherited_helpers(app) == []


def test_unreadable_entitlements_fail_closed(tmp_path, monkeypatch):
    def fail(_):
        raise app_signing.subprocess.CalledProcessError(1, 'codesign')
    monkeypatch.setattr(app_signing, 'read_entitlements', fail)
    with pytest.raises(app_signing.subprocess.CalledProcessError):
        app_signing.verify_helper_sandbox(tmp_path / 'WeChat.app')
