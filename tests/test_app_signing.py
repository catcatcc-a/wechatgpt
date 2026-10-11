"""Only helpers that inherit the removed host sandbox need signature repair."""
from pathlib import Path
import plistlib
from types import SimpleNamespace

import app_signing


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
