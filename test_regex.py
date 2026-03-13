import re
from pathlib import Path
import zipfile
import io

GOOGLE_KEY_REGEX = rb'AIza[0-9A-Za-z_-]{35}'

def extract_keys(path: Path):
    keys = set()
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            try:
                data = z.read(name)
                for m in re.finditer(GOOGLE_KEY_REGEX, data):
                    k = m.group(0).decode('utf-8', errors='ignore')
                    if len(k) == 39: keys.add(k)
            except: pass
    return sorted(keys)

print("Simplified Regex:", extract_keys(Path('apps/com.vishal.mymapactivity.apk')))
