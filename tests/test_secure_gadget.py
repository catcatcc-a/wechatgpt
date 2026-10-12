"""Old signed stages must not reinstall the helper startup regression."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import app_signing
import pytest


def test_activation_rejects_old_stage_before_copy_or_backup(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        'secure_gadget', Path(__file__).parents[1] / 'scripts/secure-gadget.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stage = tmp_path / 'stage/WeChat.app'
    player = stage / 'Contents/MacOS/XPlayer.app'
    (player / 'Contents').mkdir(parents=True)
    (player / 'Contents/Info.plist').write_text('')
    report = tmp_path / 'stage.json'
    report.write_text(json.dumps({'original': {}, 'prepared': {}, 'activated': False}))
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'STAGE', stage)
    monkeypatch.setattr(module, 'REPORT', report)
    monkeypatch.setattr(module, 'inspect', lambda _: {})
    monkeypatch.setattr(module, 'read_token', lambda _: 'synthetic-token')
    monkeypatch.setattr(module, 'validate_app', lambda *args: None)
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kw: SimpleNamespace(returncode=1))
    monkeypatch.setattr(app_signing, 'read_entitlements', lambda bundle: {} if bundle == stage else {
        'com.apple.security.app-sandbox': True, 'com.apple.security.inherit': True})

    def unexpected_mutation(*args):
        raise AssertionError('Invalid stage must be rejected before copying or installation')

    monkeypatch.setattr(module, 'run', unexpected_mutation)
    with pytest.raises(ValueError, match='XPlayer.app'):
        module.activate()
    assert not (tmp_path / 'backups').exists()
    assert not json.loads(report.read_text())['activated']
