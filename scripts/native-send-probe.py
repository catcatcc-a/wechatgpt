#!/usr/bin/env python3
"""Validate native queue/parameter construction without sending a message."""
import frida
import json
import plistlib
import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--send-test')
options=parser.parse_args()
info=plistlib.loads(Path('/Applications/WeChat.app/Contents/Info.plist').read_bytes())
assert info['CFBundleShortVersionString']=='4.1.11' or info['CFBundleShortVersionString']=='4.1.11.53', info['CFBundleShortVersionString']
assert str(info['CFBundleVersion'])=='269109', info['CFBundleVersion']
s=frida.get_device_manager().add_remote_device('127.0.0.1:27042').attach('Gadget')
manifest=json.loads((ROOT/'native/wechat-4.1.11.53.json').read_text())
p=s.create_script('const EXPECTED_MODULE_UUID='+json.dumps(manifest['module_uuid'])+';\n'+(ROOT/'native/wechat_send.js').read_text())
p.on('message',lambda m,d:print(json.dumps(m),flush=True))
try:
    p.load()
    print(json.dumps(p.exports_sync.probe()),flush=True)
    print(json.dumps(p.exports_sync.prepare('LECHO-PREPARE-ONLY'),ensure_ascii=False),flush=True)
    if options.send_test:
        result=p.exports_sync.send_text('filehelper',options.send_test)
        (ROOT/'artifacts/local-echo/native-send-result.json').write_text(json.dumps(result))
        print(json.dumps(result,ensure_ascii=False),flush=True)
        time.sleep(5)
finally:
    p.exports_sync.drain()
    p.unload()
    s.detach()
