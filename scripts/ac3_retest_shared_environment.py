"""Fingerprint the shared installed Python environment, without network access.

Run this same script in each isolated evaluator process before importing app.
The manifest includes Python executable, stdlib source/extensions, and installed
site-package content. Hashes pin installed bytes, not historical wheel files or
external shared libraries; the deployment/container image must be pinned too.
"""
import hashlib
import importlib.metadata as metadata
import json
import platform
import re
import sys
import sysconfig
from pathlib import Path


def _mix(h, name, data):
    n=name.encode(); h.update(len(n).to_bytes(8,'big'));h.update(n);h.update(len(data).to_bytes(8,'big'));h.update(data)


def capture():
    executable=Path(sys.executable).resolve(strict=True)
    stdlib=Path(sysconfig.get_path('stdlib')).resolve(strict=True)
    site_roots={Path(sysconfig.get_path(k)).resolve() for k in ('purelib','platlib') if sysconfig.get_path(k)}
    stdlib_hash=hashlib.sha256();count=0
    for path in sorted(stdlib.rglob('*')):
        if not path.is_file() or path.is_symlink() or any(path.is_relative_to(root) for root in site_roots): continue
        if '__pycache__' in path.parts or path.suffix not in ('.py','.so','.pyd','.dylib'): continue
        _mix(stdlib_hash,path.relative_to(stdlib).as_posix(),path.read_bytes());count+=1
    if not count: raise ValueError('Python stdlib files are unavailable.')
    distributions=[];seen=set()
    for dist in metadata.distributions():
        name=dist.metadata.get('Name'); version=dist.version
        if not name or not version: raise ValueError('Installed distribution lacks a name or version.')
        norm=re.sub(r'[-_.]+','-',name).lower()
        if norm in seen: raise ValueError('Duplicate installed distribution names make import resolution ambiguous.')
        seen.add(norm); files=dist.files
        if not files: raise ValueError(f'Cannot inspect installed files for {name}.')
        digest=hashlib.sha256();members=[]
        for item in files:
            path=Path(dist.locate_file(item))
            if path.suffix=='.pyc' or '__pycache__' in path.parts: continue
            resolved=path.resolve()
            if not any(resolved.is_relative_to(root) for root in site_roots): continue
            if not path.is_file() or path.is_symlink(): raise ValueError(f'Installed package member is missing or symlinked: {name}/{item}')
            members.append((str(item),path.read_bytes()))
        if not members: raise ValueError(f'No inspectable installed files for {name}.')
        for rel,data in sorted(members):_mix(digest,rel,data)
        distributions.append({'name':norm,'version':version,'installed_files_sha256':digest.hexdigest()})
    return {'format':'ac3-retest-shared-environment-v1','python_version':platform.python_version(),
            'python_implementation':platform.python_implementation(),
            'python_executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
            'stdlib_sha256':stdlib_hash.hexdigest(), 'distributions':sorted(distributions,key=lambda x:x['name']),
            'limitations':['External dynamic libraries and the OS image are not hashed; pin the execution image separately.',
                           'This fingerprint is of the current environment, not proof of the prior experiment environment.']}


def verify(expected):
    actual=capture()
    if actual != expected: raise ValueError('Shared evaluator environment has changed.')
    return True


if __name__ == '__main__':
    print(json.dumps(capture(),ensure_ascii=False,sort_keys=True,indent=2))
