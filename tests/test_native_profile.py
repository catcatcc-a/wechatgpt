import json
from pathlib import Path
import plistlib
import shutil
import struct

import pytest

from native_profile import load_profile, verify_binary_profile


def test_unverified_build_requires_exact_explicit_opt_in(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / 'native', tmp_path / 'native')
    app = tmp_path / 'WeChat.app'
    (app / 'Contents').mkdir(parents=True)
    info = app / 'Contents/Info.plist'
    info.write_bytes(plistlib.dumps({'CFBundleShortVersionString': '4.1.15', 'CFBundleVersion': '270134'}))
    manifest = tmp_path / 'native/wechat-4.1.15.54.json'
    candidate = json.loads(manifest.read_text())
    candidate['runtime_verified'] = False
    manifest.write_text(json.dumps(candidate))
    monkeypatch.delenv('WECHAT_ALLOW_EXPERIMENTAL', raising=False)
    with pytest.raises(ValueError, match='awaiting'):
        load_profile(app, tmp_path)
    monkeypatch.setenv('WECHAT_ALLOW_EXPERIMENTAL', '269109')
    with pytest.raises(ValueError, match='awaiting'):
        load_profile(app, tmp_path)
    monkeypatch.setenv('WECHAT_ALLOW_EXPERIMENTAL', '270134')
    assert load_profile(app, tmp_path)[0]['module_uuid'] == candidate['module_uuid']
    info.write_bytes(plistlib.dumps({'CFBundleShortVersionString': '4.1.15', 'CFBundleVersion': '270135'}))
    with pytest.raises(ValueError, match='no native ABI'):
        load_profile(app, tmp_path)


@pytest.mark.parametrize('fat64', [False, True])
def test_module_uuid_and_instructions_must_both_match(tmp_path, fat64):
    uuid = bytes(range(16))
    commands = struct.pack('<II', 0x1b, 24) + uuid
    commands += struct.pack('<II16sQQQQiiII', 0x19, 72, b'__TEXT', 0, 4096, 0, 4096, 5, 5, 0, 0)
    thin = bytearray(4096)
    thin[:32] = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 6, 2, len(commands), 0, 0)
    thin[32:32+len(commands)] = commands
    thin[512:516] = b'abcd'
    prefix = bytearray(4096) if fat64 else bytearray()
    if fat64:
        prefix[:8] = struct.pack('>II', 0xcafebabf, 1)
        prefix[8:40] = struct.pack('>IIQQII', 0x100000c, 0, 4096, len(thin), 12, 0)
    path = tmp_path / 'module.dylib'
    path.write_bytes(prefix + thin)
    profile = {'module_uuid': uuid.hex(), 'offsets': {'entry': '0x200'}, 'fingerprints': {'entry': b'abcd'.hex()}}
    verify_binary_profile(path, profile)
    profile['module_uuid'] = 'wrong'
    with pytest.raises(ValueError, match='UUID'):
        verify_binary_profile(path, profile)
    profile['module_uuid'] = uuid.hex()
    profile['fingerprints']['entry'] = b'wxyz'.hex()
    with pytest.raises(ValueError, match='fingerprint'):
        verify_binary_profile(path, profile)
