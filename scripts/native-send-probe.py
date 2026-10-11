#!/usr/bin/env python3
"""Validate native queue/parameter construction without sending a message."""
import frida
from gadget_auth import connect
from native_profile import load_profile, sender_code
import json
import plistlib
import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--send-test')
options=parser.parse_args()
manifest,_=load_profile()
s=connect(frida).attach('Gadget')
p=s.create_script(sender_code(manifest))
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
