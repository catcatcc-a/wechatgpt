#!/usr/bin/env python3
"""Create offline APFS clone backups; this does not replace the installed app."""
from pathlib import Path
import datetime,hashlib,json,os,stat,subprocess
ROOT=Path(__file__).resolve().parents[1]
if subprocess.run(['/usr/bin/pgrep','-x','WeChat'],capture_output=True).returncode==0:
 raise SystemExit('WeChat is still running. Refusing to create an inconsistent backup.')
STAMP=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
TARGET=ROOT/'backups'/STAMP
TARGET.mkdir(mode=0o700,parents=True)
sources=[('application',Path('/Applications/WeChat.app')),('container',Path.home()/'Library/Containers/com.tencent.xinWeChat'),('group_container',Path.home()/'Library/Group Containers/5A4RE8SF68.com.tencent.xinWeChat'),('preferences',Path.home()/'Library/Preferences/com.tencent.xinWeChat.plist')]

def inventory(root):
 paths=[root]
 if root.is_dir():
  for directory,dirs,files in os.walk(root,followlinks=False):
   paths.extend(Path(directory)/name for name in dirs+files)
 rows=[]
 for path in sorted(set(paths)):
  info=path.lstat()
  kind='symlink' if path.is_symlink() else 'directory' if path.is_dir() else 'file'
  rows.append([str(path.relative_to(root)),kind,info.st_size if kind=='file' else None,info.st_mtime_ns,os.readlink(path) if kind=='symlink' else None])
 return rows

entries=[]
for label,source in sources:
 if not source.exists(): continue
 target=TARGET/label/source.name
 target.parent.mkdir(mode=0o700)
 before=inventory(source)
 subprocess.run(['/bin/cp','-cRp',str(source),str(target)],check=True)
 after=inventory(source)
 copied=inventory(target)
 if before!=after or after!=copied:
  raise SystemExit(f'Backup metadata comparison failed for {label}; no app replacement performed.')
 digest=hashlib.sha256(json.dumps(copied,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 entries.append({'label':label,'source':str(source),'backup':str(target),'entry_count':len(copied),'bytes':sum(row[2] or 0 for row in copied),'inventory_sha256':digest,'verified':True})
 print(json.dumps({'backed_up':label,'entry_count':len(copied),'verified':True}),flush=True)
manifest={'created_at':datetime.datetime.now().isoformat(),'method':'APFS clonefile via cp -cRp; source stable and every path/type/size/mtime/symlink compared','backup_root':str(TARGET),'entries':entries}
(TARGET/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(TARGET/'manifest.json').chmod(0o600)
report=ROOT/'artifacts/activation/backup.json'
report.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
report.write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'complete':True,'backup_root':str(TARGET)}))
