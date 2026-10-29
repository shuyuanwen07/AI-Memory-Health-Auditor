"""Build a local assessed-source archive without live secrets or development data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'README.md', '.env.example', '.gitignore', 'docker-compose.yml',
              'docker-compose.ci.yml', '.dockerignore', '.nvmrc', 'pyproject.toml', 'LICENSE'}
SOURCE_DIRS = {'backend', 'frontend', 'scripts', 'docs', '.github', 'reference_target', 'mem0_target'}
BLOCKED_PARTS = {'.git', '.env', '.engineering-smoke', 'node_modules', 'dist', '__pycache__', '.pytest_cache',
                 '.ruff_cache', '.venv', 'output', 'private', 'experiments', 'artifacts'}
SYNTHETIC_DATA_DIRS = {
    'annotation', 'benchmarks', 'paper-artifacts', 'assessment-candidates-v1',
    'demo', 'smoke', 'templates', 'phase3-engineering-v1', 'phase4-candidate-v1',
}
STUDY_FIXTURES = {'independent-repair-v1', 'qwen-repair-v4', 'repair-pilot-v1'}
SHARED_HANDOFF_DIRS = {'owner-a', 'owner-b', 'owner-c'}
TEXT_DATA_SUFFIXES = {'.csv', '.ini', '.json', '.md', '.py', '.sh', '.toml', '.tsv', '.txt', '.yaml', '.yml'}


def _assert_no_symlink_path(root: Path, path: Path) -> None:
    """Reject a root or any ancestor that would let a package walk escape its tree."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f'Package input path escapes repository root: {path}') from exc
    current = root
    if current.is_symlink():
        raise ValueError(f'Refusing a symlinked package root: {current}')
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f'Refusing a symlinked package source/data directory: {current.relative_to(root)}')


def _walk_files(root: Path, base: Path, *, blocked_dirs: set[str], prune_frontend_reports: bool = False):
    """Walk one allowlisted tree without traversing symlinked directories."""
    _assert_no_symlink_path(root, base)
    if not base.is_dir():
        return
    for current, dirs, files in os.walk(base, followlinks=False):
        current_path = Path(current)
        retained_dirs = []
        for name in dirs:
            if name in blocked_dirs:
                continue
            child = current_path / name
            if (prune_frontend_reports and current_path.relative_to(root).parts == ('frontend', 'public')
                    and name == 'reports'):
                continue
            if child.is_symlink():
                raise ValueError(f'Refusing a symlinked package source/data directory: {child.relative_to(root)}')
            retained_dirs.append(name)
        dirs[:] = retained_dirs
        for name in files:
            path = current_path / name
            if not path.is_symlink():
                yield path


def candidate_files(root: Path):
    """Yield only source roots and explicitly approved synthetic fixture roots.

    Avoid walking generated experiment archives, node_modules, and local smoke
    outputs merely to filter them after a whole-repository recursive scan.
    """
    root = Path(root)
    if root.is_symlink():
        raise ValueError('Refusing a symlinked package root.')
    root = root.resolve()

    for name in ROOT_FILES:
        path = root / name
        if path.is_file() and not path.is_symlink():
            yield path

    for directory in SOURCE_DIRS:
        base = root / directory
        yield from _walk_files(root, base, blocked_dirs=BLOCKED_PARTS,
                               prune_frontend_reports=True)

    for directory in SHARED_HANDOFF_DIRS:
        base = root / 'handoff' / directory
        yield from _walk_files(root, base, blocked_dirs=BLOCKED_PARTS)

    dataset_roots = [
        root / 'datasets' / name for name in SYNTHETIC_DATA_DIRS
        if name not in {'annotation', 'benchmarks'}
    ]
    dataset_roots.extend((
        root / 'datasets/annotation/v1',
        root / 'datasets/annotation/pilot-v1',
        root / 'datasets/benchmarks/longmemeval-compatible-v1',
        *(root / 'datasets/studies' / name for name in STUDY_FIXTURES),
    ))
    for base in dataset_roots:
        yield from _walk_files(root, base, blocked_dirs=BLOCKED_PARTS)


def allowed(relative: Path) -> bool:
    parts = relative.parts
    if not parts or any(part in BLOCKED_PARTS for part in parts):
        return False
    if any(part.startswith('.env') and part != '.env.example' for part in parts):
        return False
    if relative.is_absolute() or '..' in parts:
        return False
    if relative.suffix.lower() in {'.pyc', '.sqlite', '.sqlite3', '.db', '.log', '.tsbuildinfo'}:
        return False
    if parts[0] in ROOT_FILES and len(parts) == 1:
        return True
    if parts[0] == 'datasets':
        if len(parts) < 3:
            return False
        if relative.suffix.lower() not in TEXT_DATA_SUFFIXES:
            return False
        if parts[1] == 'annotation' and parts[2] not in {'v1', 'pilot-v1'}:
            return False
        if parts[1] == 'benchmarks':
            return parts[2] == 'longmemeval-compatible-v1'
        return parts[1] in SYNTHETIC_DATA_DIRS or (parts[1] == 'studies' and parts[2] in STUDY_FIXTURES)
    if parts[0] == 'handoff':
        return (len(parts) > 2 and parts[1] in SHARED_HANDOFF_DIRS
                and relative.suffix.lower() in TEXT_DATA_SUFFIXES)
    if parts[0] not in SOURCE_DIRS:
        return False
    if parts[:3] == ('frontend', 'public', 'reports'):
        return False
    # Only code/config/docs extensions; never package arbitrary binary exports.
    if relative == Path('scripts/phase4_review_form.js'):
        return True
    return relative.suffix.lower() in {'.py', '.tsx', '.ts', '.css', '.html', '.json', '.md', '.txt',
                                      '.toml', '.ini', '.yml', '.yaml', '.sh', '.svg'} or relative.name in {'Dockerfile', '.dockerignore'}


def package(root: Path, destination: Path) -> dict:
    root = Path(root)
    if root.is_symlink():
        raise ValueError('Refusing a symlinked package root.')
    root = root.resolve()
    selected = [path for path in candidate_files(root) if path.is_file() and not path.is_symlink()
                and allowed(path.relative_to(root))]
    selected.sort(key=lambda path: path.relative_to(root).as_posix())
    if not selected:
        raise ValueError('No source files selected.')
    contents = {path.relative_to(root).as_posix(): path.read_bytes() for path in selected}
    files = {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}
    base_revision = None
    working_tree_status = 'unknown'
    try:
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=False)
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True, check=False)
        if revision.returncode == 0:
            base_revision = revision.stdout.strip() or None
        if status.returncode == 0:
            working_tree_status = 'modified' if status.stdout.strip() else 'clean'
    except FileNotFoundError:
        # Source distributions and minimal containers may not include Git.
        # Content hashes still identify the snapshot; do not claim a clean tree.
        pass
    manifest = {'format': 'assessed-source-v1', 'base_revision': base_revision,
                'working_tree_status': working_tree_status,
                'file_count': len(files), 'files': files,
                'notice': 'Local source snapshot, not a final report or proof of independent validation. File hashes identify included contents; an older CI run does not certify this snapshot.',
                'included_scope': ['application source and tests', 'allowlisted synthetic fixtures',
                                   'shared owner-a, owner-b, and owner-c handoff records'],
                'review_notes': ['Owner A handoff labels are explicitly AI-assisted; they are not independent human gold.',
                                 'Owner C handoff contains summary metrics; its raw private review archive is excluded.',
                                 'A manifest hash does not establish third-party licence, consent, or reviewer provenance.',
                                 'No credential-pattern scan is performed; path and file-type allowlists do not detect secrets embedded in included text files.'],
                'excluded': ['credentials and environment', 'databases', 'Git history', 'participant/private data',
                             'local experiment/output archives and public frontend report exports',
                             'owner-a custodian package and user-supplied reviewer files',
                             'unapproved benchmark sources', 'dependency/build caches',
                             'unreviewed arbitrary binary files']}
    # File selection is complete before writing; output cannot recursively include itself.
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / 'AI-Memory-Health-Auditor-source.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in selected:
            info = zipfile.ZipInfo(path.relative_to(root).as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IMODE(path.stat().st_mode) | stat.S_IFREG) << 16
            bundle.writestr(info, contents[path.relative_to(root).as_posix()])
        bundle.writestr('ASSESSMENT_SOURCE_MANIFEST.json', json.dumps(manifest, indent=2))
    manifest['archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (destination / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/assessment-release-v1')
    args = parser.parse_args()
    result = package(ROOT, args.output)
    print(json.dumps({'files': result['file_count'], 'archive_sha256': result['archive_sha256'],
                      'working_tree_status': result['working_tree_status']}))
