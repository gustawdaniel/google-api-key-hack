import re
from pathlib import Path
import zipfile
import io

def test_extract(path: Path, regex):
    keys = set()
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            try:
                data = z.read(name)
                for m in re.finditer(regex, data):
                    k = m.group(0).decode('utf-8', errors='ignore')
                    if len(k) == 39: keys.add(k)
            except: pass
    return sorted(keys)

apk = Path("apps/com.vishal.mymapactivity.apk")
print("Strict Regex:", test_extract(apk, rb'(?<![\w-])AIza[0-9A-Za-z_-]{35}(?![\w-])'))
print("Loose Regex:", test_extract(apk, rb'AIza[0-9A-Za-z_-]{35}'))
