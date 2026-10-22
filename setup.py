#!/usr/bin/env python3
"""Initialize private configuration without overwriting existing files."""
import hashlib,json,os,shutil,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parent
os.umask(0o077)
(root/'private').mkdir(mode=0o700,exist_ok=True)
os.chmod(root/'private',0o700)
for source,target in [('settings.example.json','settings.json'),('credentials.example.json','private/credentials.json'),('notification.example.json','private/notification.json')]:
 p=root/target
 if not p.exists():shutil.copyfile(root/source,p)
 os.chmod(p,0o600)
meta=json.loads((root/'vendor/smcrypt.source.json').read_text())
p=root/'vendor/smcrypt.js'
if not p.exists():
 with urllib.request.urlopen(meta['source'],timeout=30) as r:raw=r.read(1000000)
 if hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise SystemExit('Encryption dependency changed; review before installing')
 p.write_bytes(raw)
print('Configuration initialized; fill private credentials and notification settings locally.')
