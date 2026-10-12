#!/usr/bin/env python3
"""Atomically swap the backed-up app with the prepared compatible copy. No launch."""
from pathlib import Path
import json,os,plistlib,subprocess
from app_signing import verify_helper_sandbox
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'artifacts/activation/backup.json').read_text())
assert all(e['verified'] for e in manifest['entries'])
assert {e['label'] for e in manifest['entries']} >= {'application','container','group_container'}
if subprocess.run(['/usr/bin/pgrep','-x','WeChat'],capture_output=True).returncode==0:
 raise SystemExit('WeChat restarted; refusing installation while running.')
app=Path('/Applications/WeChat.app')
info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
assert info['WeChatBundleVersion']=='4.1.15.54' and info['CFBundleVersion']=='270134'
stage=ROOT/'runtime/WeChat.app'
assert plistlib.loads((stage/'Contents/Info.plist').read_bytes())['CFBundleVersion']=='269109'
verify_helper_sandbox(stage)
temp=Path('/Applications/.WeChat-mcp-staged.app')
assert not temp.exists()
subprocess.run(['/bin/cp','-cRp',str(stage),str(temp)],check=True)
subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(temp)],check=True)
verify_helper_sandbox(temp)
original=Path(manifest['backup_root'])/'installed-original-WeChat.app'
assert not original.exists()
os.rename(app,original)
try:
 os.rename(temp,app)
except BaseException:
 os.rename(original,app)
 raise
result={'installed_build':'269109','installed_version':'4.1.11.53','original_app':str(original),'backup_manifest':str(Path(manifest['backup_root'])/'manifest.json'),'launched':False}
(ROOT/'artifacts/activation/install.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
