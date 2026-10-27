"""Package the authorised 27 October engineering/research evidence, without API calls."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'research/evidence-20261027'
SOURCES = [
    'artifacts/local/phase12-20261027',
    'artifacts/local/phase3-20261027',
    'artifacts/local/phase4-20261027',
    'artifacts/local/phase4-followup-20261027',
    'artifacts/local/phase4-formal-review-20261027',
    'output/engineering-verification',
]
BLOCKED = {'.env', '.DS_Store', '__pycache__', '.pytest_cache', '.git', 'node_modules'}


def secret_values() -> list[bytes]:
    values = []
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            name, value = line.split('=', 1)
            value = value.strip().strip('\"\'')
            if any(x in name.upper() for x in ('API_KEY', 'API_TOKEN', 'SECRET')) and len(value) >= 12:
                values.append(value.encode())
    return values


def scan(name: str, content: bytes, secrets: list[bytes], depth: int = 0) -> None:
    path = Path(name)
    if any(part in BLOCKED for part in path.parts) or path.suffix in {'.db', '.sqlite', '.sqlite3'}:
        raise ValueError('Forbidden evidence path: ' + name)
    if any(value in content for value in secrets) or re.search(
        rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-or-v1-[a-f0-9]{40,}', content
    ):
        raise ValueError('Credential marker detected in ' + name + '; value not printed')
    if depth > 4:
        raise ValueError('Unexpected archive nesting in ' + name)
    if name.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    scan(info.filename, archive.read(info), secrets, depth + 1)
    elif name.endswith('.tar.gz'):
        with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as archive:
            for member in archive:
                if member.isfile():
                    stream = archive.extractfile(member)
                    assert stream is not None
                    scan(member.name, stream.read(), secrets, depth + 1)


def main() -> None:
    files = sorted(
        path for source in SOURCES for path in (ROOT / source).rglob('*')
        if path.is_file() and not path.is_symlink()
        and not any(part in BLOCKED for part in path.relative_to(ROOT).parts)
    )
    secrets = secret_values()
    payload = {}
    for path in files:
        name = path.relative_to(ROOT).as_posix()
        content = path.read_bytes()
        scan(name, content, secrets)
        payload[name] = content
    manifest = {
        'format': 'authorised-project-evidence-20261027-v1',
        'packaging_source_commit': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'scope': 'Engineering snapshots, real A/B/C collections and retrospective review; not formal validation certification.',
        'original_layout': 'Extract at repository root in a fresh checkout; original artifact paths are preserved.',
        'sources': SOURCES,
        'excluded': 'Credentials, databases, caches, unrelated private materials and Final Report/presentation files.',
        'review_boundary': 'Includes outcome/identity binding keys and user-reported provenance corrections; unsuitable for distributing new blind review.',
        'file_count': len(payload),
        'uncompressed_bytes': sum(map(len, payload.values())),
        'files': {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()},
        'credential_scan': 'Configured provider-secret values and high-confidence key markers checked, including nested archives; not a universal privacy audit.',
    }
    DEST.mkdir(parents=True, exist_ok=True)
    archive_path = DEST / 'experiment-evidence.zip'
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in payload.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content, compresslevel=9)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(payload)
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    manifest['archive_sha256'] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    manifest['archive_bytes'] = archive_path.stat().st_size
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({key: manifest[key] for key in ('file_count', 'uncompressed_bytes', 'archive_bytes', 'archive_sha256')}))


if __name__ == '__main__':
    main()
