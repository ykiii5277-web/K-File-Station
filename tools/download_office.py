"""Fetch the official MSI from a TDF mirror and verify against the publisher's hash."""
from pathlib import Path
import hashlib
import re
import requests
import time

root = Path(__file__).resolve().parents[1]
url = 'https://mirrors.nju.edu.cn/tdf/libreoffice/stable/26.2.7/win/x86_64/LibreOffice_26.2.7_Win_x86-64.msi'
official = 'https://download.documentfoundation.org/libreoffice/stable/26.2.7/win/x86_64/LibreOffice_26.2.7_Win_x86-64.msi.sha256'
target = root / 'engines/LibreOffice.msi'
size = target.stat().st_size if target.exists() else 0
with requests.get(url, stream=True, timeout=(20, 90)) as r:
    r.raise_for_status()
    if r.status_code != 206:
        size = 0
    total = size + int(r.headers.get('Content-Length', 0))
    last = time.monotonic()
    with target.open('ab' if size else 'wb') as f:
        for chunk in r.iter_content(1024 * 512):
            f.write(chunk)
            size += len(chunk)
            if time.monotonic() - last > 20:
                print(f'LibreOffice: {size/1024**2:.1f} / {total/1024**2:.1f} MB', flush=True)
                last = time.monotonic()
digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
print('SHA256', digest, flush=True)
checksum = requests.get(official, timeout=45)
checksum.raise_for_status()
expected = re.search(r'\b[0-9a-fA-F]{64}\b', checksum.text).group(0).lower()
if digest != expected:
    raise RuntimeError('Official LibreOffice checksum mismatch')
(root / 'engines/VERIFIED-LIBREOFFICE.txt').write_text(f'LibreOffice 26.2.7\nSHA256 {digest}\n{official}\n', 'utf-8')
print('Official checksum verified', flush=True)
