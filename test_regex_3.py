import re
from pathlib import Path
import zipfile

def scan_all(apps_dir):
    files = [f for f in Path(apps_dir).iterdir() if f.suffix in ['.apk', '.apkm', '.xapk']]
    strict = rb'(?<![\w-])AIza[0-9A-Za-z_-]{35}(?![\w-])'
    loose = rb'AIza[0-9A-Za-z_-]{35}'
    
    strict_count = 0
    loose_count = 0
    
    for f in files:
        s_found = False
        l_found = False
        try:
            with zipfile.ZipFile(f) as z:
                for name in z.namelist():
                    data = z.read(name)
                    if not s_found and re.search(strict, data):
                        s_found = True
                        strict_count += 1
                    if not l_found and re.search(loose, data):
                        l_found = True
                        loose_count += 1
                    if s_found and l_found: break
        except: pass
    
    print(f"Out of {len(files)} apps:")
    print(f"Strict regex found keys in: {strict_count}")
    print(f"Loose regex found keys in:  {loose_count}")

scan_all('apps')
