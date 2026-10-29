"""Resolve immutable review evidence across the configured host/container.

Manifests keep their original bytes and host paths. In strict container mode,
only paths below the configured host project's output directory (or the
corresponding /output mount) are allowed. Every component is checked for
symlinks; callers still verify the stored file digest after resolution.
"""
import os
import copy
from pathlib import Path


def _under(path, base):
    try: return path.relative_to(base)
    except ValueError: return None


def _no_symlinks(path, base):
    if base.is_symlink(): raise ValueError('Evidence mount may not be a symlink')
    relative = _under(path,base)
    if relative is None: raise ValueError('Evidence is outside the allowed mount')
    current=base
    for part in relative.parts:
        current=current/part
        if current.is_symlink(): raise ValueError('Evidence paths may not traverse symlinks')
    return path


def resolve_evidence_path(value):
    if not isinstance(value,(str,Path)) or not str(value): raise ValueError('Evidence path is required')
    path=Path(value)
    if '..' in path.parts: raise ValueError('Evidence path cannot contain parent traversal')
    configured=os.environ.get('AC3_HOST_PROJECT_ROOT')
    if not configured:
        return path
    host_root=Path(configured)
    output_root=Path(os.environ.get('AC3_OUTPUT_ROOT','/output'))
    if not host_root.is_absolute() or '..' in host_root.parts or not output_root.is_absolute() or '..' in output_root.parts:
        raise ValueError('Configured evidence roots must be absolute')
    if not path.is_absolute(): raise ValueError('Manifest evidence paths must be absolute')
    relative=_under(path,host_root/'output')
    if relative is None: relative=_under(path,output_root)
    if relative is None: raise ValueError('Manifest evidence is outside the configured project output')
    return _no_symlinks(output_root/relative,output_root)


def resolve_frozen_source(value, root):
    """Resolve a bound output file or a read-only project script dependency."""
    path=Path(value)
    if '..' in path.parts: raise ValueError('Frozen paths cannot contain parent traversal')
    configured=os.environ.get('AC3_HOST_PROJECT_ROOT')
    if not configured:
        return path if path.is_absolute() else Path(root)/path
    if not path.is_absolute():
        path=Path(root)/path
    host_root=Path(configured); scripts_root=Path(root)/'scripts'
    relative=_under(path,host_root/'scripts')
    if relative is None: relative=_under(path,scripts_root)
    if relative is not None:
        return _no_symlinks(scripts_root/relative,scripts_root)
    public_root=Path(root)/'frontend/public'
    relative=_under(path,host_root/'frontend/public')
    if relative is None: relative=_under(path,public_root)
    if relative is not None and relative == Path('reports/phase4-c-four-strategy-v7.json'):
        return _no_symlinks(public_root/relative,public_root)
    return resolve_evidence_path(path)


def pilot_audits_equivalent(saved, recomputed):
    """Compare pilot reports while preserving original logical host paths."""
    if not isinstance(saved,dict) or not isinstance(recomputed,dict): return False
    left,right=copy.deepcopy(saved),copy.deepcopy(recomputed)
    a,b=left.pop('sources',None),right.pop('sources',None)
    if left!=right or not isinstance(a,dict) or not isinstance(b,dict) or set(a)!=set(b): return False
    for name in a:
        if not isinstance(a[name],dict) or not isinstance(b[name],dict): return False
        first,second=dict(a[name]),dict(b[name])
        try:
            root=Path(__file__).resolve().parents[1]
            if resolve_frozen_source(first.pop('path'),root) != resolve_frozen_source(second.pop('path'),root): return False
        except (KeyError, ValueError): return False
        if first!=second: return False
    return True
