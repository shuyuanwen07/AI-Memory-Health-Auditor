"""Verify isolated full-app source snapshots against a recorded runtime signature.

No snapshot is created here and package versions cannot by themselves prove an
identical installed runtime; independently inspect and pin actual distributions.
"""
import hashlib
import io
import re
import json
from pathlib import PurePosixPath
import zipfile


def formal_signature(archive):
    digest=hashlib.sha256(); entries={}
    raw=PureBytes(archive)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):
            raise ValueError('Duplicate archive paths.')
        for info in z.infolist():
            p=PurePosixPath(info.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in info.filename or info.file_size>10_000_000:
                raise ValueError('Unsafe archive path or oversized file.')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Archive symlinks are forbidden.')
            if info.filename.startswith('app/') and info.filename.endswith('.py') and not info.is_dir():
                entries[info.filename[4:]]=z.read(info)
        if not entries or 'evaluator/rule_based.py' not in entries:
            raise ValueError('Snapshot must contain the complete app source and evaluator.')
        if 'requirements.txt' not in names or 'dependencies.lock.json' not in names:
            raise ValueError('Requirements and an explicit environment lock are required.')
        lock=json.loads(z.read('dependencies.lock.json'))
        if (not isinstance(lock.get('python_version'),str) or not lock['python_version'] or
                not isinstance(lock.get('distributions'),list) or not lock['distributions'] or
                any(not isinstance(x,dict) or not all(isinstance(x.get(k),str) and x[k] for k in ('name','version','installed_files_sha256')) for x in lock['distributions']) or
                any(re.fullmatch(r'[0-9a-f]{64}',x['installed_files_sha256']) is None for x in lock['distributions'])):
            raise ValueError('Environment lock must list Python and exact distributions with artifact digests.')
        for key in sorted(entries):
            name=key.encode();data=entries[key]
            digest.update(len(name).to_bytes(8,'big'));digest.update(name);digest.update(len(data).to_bytes(8,'big'));digest.update(data)
        return {'app_source_sha256':digest.hexdigest(), 'archive_sha256':hashlib.sha256(raw).hexdigest(),
                'requirements_sha256':hashlib.sha256(z.read('requirements.txt')).hexdigest(),
                'dependencies_lock_sha256':hashlib.sha256(z.read('dependencies.lock.json')).hexdigest(),
                'source_files':len(entries), 'lock_installation_verified':False}


def PureBytes(archive):
    """Read a local file or byte sequence, without extraction."""
    from pathlib import Path
    return bytes(archive) if isinstance(archive,(bytes,bytearray)) else Path(archive).read_bytes()


def verify_snapshot(path, expected_app_sha256, expected_archive_sha256, expected_lock_sha256):
    info=formal_signature(path)
    if (info['app_source_sha256']!=expected_app_sha256 or info['archive_sha256']!=expected_archive_sha256 or
            info['dependencies_lock_sha256']!=expected_lock_sha256):
        raise ValueError('Snapshot source, archive, or environment-lock hash differs from preregistered evidence.')
    return info
