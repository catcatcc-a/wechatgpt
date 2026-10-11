#!/usr/bin/env python3
"""Prepare a version-checked, signed Gadget app copy; never launch or replace WeChat."""
from pathlib import Path
import hashlib,json,os,plistlib,shutil,subprocess
from gadget_auth import ensure_token, write_config
ROOT=Path(__file__).resolve().parents[1]
DMG=ROOT/'downloads/xWeChatMac_universal_4.1.11.53_41748.dmg'
APP=ROOT/'runtime/WeChat.app'
MOUNT=ROOT/'runtime/installer-mount'
GADGET=ROOT/'downloads/frida-gadget-17.8.0-macos-universal.dylib'

def run(*args):
 return subprocess.run([str(a) for a in args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
def sha(path):
 with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

if APP.exists(): raise SystemExit('Stage already exists; inspect it instead of overwriting.')
os.umask(0o077)
token=ensure_token(ROOT/'data/gadget.token')
assert sha(DMG)=='ea80413fca0ea09eb4241e333a8f09862d33c6c967e6ab66244fd474e6ab4115'
assert sha(GADGET)=='fa67242fa0cee16e80a803703991e81381cd05f7823a4151515460339c942f9f'
MOUNT.mkdir(parents=True,exist_ok=True)
mounted=False
try:
 run('/usr/bin/hdiutil','attach','-readonly','-nobrowse','-noautoopen','-mountpoint',MOUNT,DMG)
 mounted=True
 source=MOUNT/'WeChat.app'
 info=plistlib.loads((source/'Contents/Info.plist').read_bytes())
 assert info['WeChatBundleVersion']=='4.1.11.53' and info['CFBundleVersion']=='269109'
 run('/usr/bin/ditto',source,APP)
finally:
 if mounted: run('/usr/bin/hdiutil','detach',MOUNT)
assert sha(APP/'Contents/MacOS/WeChat')=='b583a21419f798ff55e3a53560c508bde507365898db12a33028a8718f9f5352'
frameworks=APP/'Contents/Frameworks'
shutil.copy2(GADGET,frameworks/'FridaGadget.dylib')
(frameworks/'FridaGadget.dylib').chmod(0o755)
write_config(APP, token)
(frameworks/'FridaGadget.config').symlink_to('../Resources/FridaGadget.config')
run('/usr/bin/python3',ROOT/'scripts/inject_load_dylib.py',APP/'Contents/MacOS/WeChat','@executable_path/../Frameworks/FridaGadget.dylib')
# Use plain ad-hoc signing, as the matching classic project does on macOS 26.
# Do not add restricted debug/JIT entitlements or alter SIP.
suffixes=('.framework','.dylib','.bundle','.xpc','.appex','.app')
code=[p for p in (APP/'Contents').rglob('*') if not p.is_symlink() and ((p.is_file() and p.name.endswith('.dylib')) or (p.is_dir() and p.name.endswith(suffixes)))]
for path in sorted(code,key=lambda p:len(p.parts),reverse=True):
 run('/usr/bin/codesign','-f','-s','-','--timestamp=none',path)
run('/usr/bin/codesign','-f','-s','-','--timestamp=none',APP)
run('/usr/bin/codesign','--verify','--deep','--strict',APP)
loads=run('/usr/bin/otool','-L',APP/'Contents/MacOS/WeChat').stdout.decode()
assert '@executable_path/../Frameworks/FridaGadget.dylib' in loads
report={'app':str(APP),'version':'4.1.11.53','build':'269109','gadget':'17.8.0','signature':'ad-hoc verified','launched':False,'installed':False,'main_sha256':sha(APP/'Contents/MacOS/WeChat')}
(ROOT/'artifacts/activation').mkdir(parents=True,exist_ok=True)
(ROOT/'artifacts/activation/stage.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
